import os
from app.services.file_loader import download_resume
from app.services.text_extractor import extract_raw_text
from app.utils.logger import logger
# from app.utils.log_context import set_log_context
from app.services.normalize import normalize_text
from app.services.hashing import sha256_hash
from app.services.dedup import find_duplicate, mark_as_duplicate
from app.utils.mongo import resume_processings_collection, job_descriptions_collection
from bson.objectid import ObjectId
from app.embeddings.text_builder import build_embedding_texts
from app.embeddings.service import generate_embedding
from app.embeddings.similarity import cosine_similarity
from app.embeddings.prefilter import prefilter_resume
from app.embeddings.ranking import rank_resumes_in_batch
from app.embeddings.experience import extract_experience_years,compute_experience_match_ratio
from app.embeddings.skill_match import compute_skill_match_ratio
from app.explanation.skills_mapping import build_skill_explanation
from app.explanation.decision_builder import build_decision_explanation
from app.explanation.score_breakdown import build_score_breakdown
from app.utils.exceptions import JobDeletedError

def process_resume(job_payload):
    """
    Phase 3 - Step 1:
    Download resume + extract raw text
    """
    file_path = None


    # logger.info(f"Starting resume processing for {external_resume_id}")

    try:
        resume_url = job_payload["resumeUrl"]
        resume_processing_id = job_payload["resumeProcessingId"]
        external_resume_id = job_payload["externalResumeId"]
        job_description_id = job_payload["jobDescriptionId"]
        bson_job_description_id = ObjectId(job_description_id)

        # 1. Download
        logger.info("Downloading resume\n")
        file_path, mime = download_resume(resume_url)

        # 2. Extract text
        logger.info("Extracting text\n")
        raw_text = extract_raw_text(file_path, mime)

        job_doc = job_descriptions_collection.find_one({
            "_id": bson_job_description_id
        })

    

        if not job_doc or job_doc.get("status") != "active":
            
            logger.warning("Job deleted during extraction. Aborting.")
            raise JobDeletedError("Job deleted mid-processing")
        
        logger.info("Text extraction completed\n")

        if not raw_text.strip():
            raise Exception("Extracted text is empty")
        
        # 3. Normalizing text
        logger.info("Normalizing text\n")
        normalized_resume_text = normalize_text(raw_text)

        logger.info(
            f"Normalized resume text length={len(normalized_resume_text)}\n"
        )

        # 4. ---- HASHING ----
        resume_hash = sha256_hash(normalized_resume_text)


        # Job text should already be stored in DB or payload

        # Check Job exists or not
        job_doc = job_descriptions_collection.find_one({
            "_id": bson_job_description_id
        })


        if not job_doc or job_doc.get("status") != "active":
            
            logger.warning("Job deleted during extraction. Aborting.")            
            logger.warning("Job deleted mid-processing. Aborting safely.")
            raise JobDeletedError("Job deleted mid-processing")
                
        job_doc = job_descriptions_collection.find_one(
            {"_id": bson_job_description_id},
            {
                "title": 1,
                "company": 1,
                "location": 1,
                "required_skills": 1,
                "preferred_skills": 1,
                "experience_level": 1,
                "min_experience_years": 1,
                "description": 1,
                "status": 1,
            }
        )


        if not job_doc or job_doc.get("status") != "active":
            
            raise JobDeletedError("Job is deleted or inactive")

        job_text_parts = [
            job_doc.get("title", ""),
            job_doc.get("company", ""),
            job_doc.get("location", ""),
            " ".join(job_doc.get("required_skills", [])),
            " ".join(job_doc.get("preferred_skills", [])),
            job_doc.get("experience_level", ""),
            str(job_doc.get("min_experience_years", "")),
            job_doc.get("description", ""),
        ]

        

        job_text = " ".join(job_text_parts)
        normalized_job_text = normalize_text(job_text)
        job_hash = sha256_hash(normalized_job_text)

        logger.info("Hashes computed successfully\n")  

        # 5. ------------- dedup --------------------

        logger.info("Phase-3 Step-3: Checking for duplicates\n")

        duplicate = find_duplicate(resume_hash, job_hash)

        if duplicate:
            logger.info(
                f"Duplicate found. Reusing results from ResumeProcessing={duplicate['_id']}\n"
            )

            mark_as_duplicate(
                current_processing_id=resume_processing_id,
                source_processing_doc=duplicate
            )

            return {
                "resumeProcessingId": resume_processing_id,
                "status": "completed",
                "result": "cache",
                "duplicateOf": str(duplicate["_id"])
            }

        # No duplicate → store hashes and continue pipeline
        resume_processings_collection.update_one(
            {"_id": ObjectId(resume_processing_id)},
            {
                "$set": {
                    "resumeHash": resume_hash,
                    "jobHash": job_hash,
                    "normalizedResumeText": normalized_resume_text
                }
            }
        )

        logger.info("No duplicate found, moving to Phase-4\n")

        # ----  Build embedding texts ----
        logger.info("Embedding starts!")
        resume_embedding_text, job_embedding_text = build_embedding_texts(
            normalized_resume_text,
            normalized_job_text
        )

        # ----  Generate embeddings ----
        resume_embedding, model_name = generate_embedding(resume_embedding_text)
        job_embedding, _ = generate_embedding(job_embedding_text)
        job_doc = job_descriptions_collection.find_one({
            "_id": bson_job_description_id
        })
        if not job_doc or job_doc.get("status") != "active":
            logger.warning("Job deleted during embeddings. Aborting.")
            raise JobDeletedError("Job deleted mid-processing")


        resume_processings_collection.update_one(
            {"_id": ObjectId(resume_processing_id)},
            {
                "$set": {
                    "resumeEmbedding": resume_embedding,
                    "jobEmbedding": job_embedding,
                    "embeddingModel": model_name,
                    "embeddingStatus": "completed",
                }
            }
        )

        logger.info("Phase 4.2 embeddings generated and stored\n")

        # ---- Pre-filtering ----
        similarity_score = cosine_similarity(
            resume_embedding,
            job_embedding
        )

        prefilter_result = prefilter_resume(
            similarity_score=similarity_score,
            normalized_resume_text=normalized_resume_text,
            required_skills=job_doc.get("required_skills", [])
        )


        resume_processings_collection.update_one(
            {"_id": ObjectId(resume_processing_id)},
            {
            "$set": {
                "preFilter": prefilter_result,
                "passFail": "passed" if prefilter_result.get("passed") else "failed"
            }
            }
        )

        logger.info(
            f"Phase 4.3 pre-filter completed | "
            f"passed={prefilter_result['passed']} | "
            f"similarity={prefilter_result['similarityScore']}\n"
        )

        extracted_experience_years = extract_experience_years(normalized_resume_text)


        # --- ranking -------
        logger.info("Ranking starts")
        rank_resumes_in_batch(
            batch_id=job_payload["batchId"],
            job_description_id=job_description_id,
            required_skills=job_doc.get("required_skills", []),
            preferred_skills=job_doc.get("preferred_skills", []),
            min_experience_years=job_doc.get("min_experience_years", 0),
        )        

        logger.info("Ranking ends!")

        # --- Explanation ------
        logger.info("Building explanation!")
        logger.info("- Building skill explanation...")
        skills_explanation = build_skill_explanation(
            required_skills=job_doc["required_skills"],
            preferred_skills=job_doc.get("preferred_skills", []),
            normalized_resume_text=normalized_resume_text,)
        

        resume_processings_collection.update_one(
            {
                "_id": ObjectId(resume_processing_id),
            },
            {
                "$set": {
                    "explanation.skills": skills_explanation
                }
            }
        )

        logger.info("Building decision explanation...")
        decision_explanation = build_decision_explanation(
            prefilter=prefilter_result,
            skills_explanation=skills_explanation,
            experience_info={
                "requiredYears": job_doc.get("min_experience_years", 0),
                "candidateYears": extracted_experience_years,
                "meetsRequirement": extracted_experience_years
                >= job_doc.get("min_experience_years", 0),
            },
        )

        resume_processings_collection.update_one(
            {
                "_id": ObjectId(resume_processing_id),
            },
            {
                "$set": {
                    "explanation.decision": decision_explanation
                }
            }
        )


        if prefilter_result["passed"]:
            logger.info("Building score breakdown...")

            score_breakdown = build_score_breakdown(
                semantic_similarity=prefilter_result["similarityScore"],
                required_skill_ratio=compute_skill_match_ratio(
                    normalized_resume_text,
                    job_doc.get("required_skills", [])
                ),
                preferred_skill_ratio=compute_skill_match_ratio(
                    normalized_resume_text,
                    job_doc.get("preferred_skills", [])
                ),
                experience_ratio=compute_experience_match_ratio(
                    extracted_years=extracted_experience_years,
                    required_years=job_doc.get("min_experience_years", 0),
                ),
            )

            resume_processings_collection.update_one(
                { "_id": ObjectId(resume_processing_id) },
                {
                    "$set": {
                        "explanation.scoreBreakdown": score_breakdown,
                        "explanation.experience": {
                            "requiredYears": job_doc.get("min_experience_years", 0),
                            "candidateYears": extracted_experience_years,
                            "meetsRequirement": extracted_experience_years
                            >= job_doc.get("min_experience_years", 0),
                        },
                    }
                }
            )

        if not prefilter_result["passed"]:
            resume_processings_collection.update_one(
                { "_id": ObjectId(resume_processing_id) },
                {
                    "$set": {
                        "rankingStatus": "skipped"
                    }
                }
            )



        # More steps to go

        return {
            "result": "completed",
            "resumeProcessingId": resume_processing_id,
            "isDuplicate": False
        }           


    except Exception as e:
        logger.exception(f"process_resume failed: {e}\n")
        raise

    finally:
        # 🧹 cleanup temp file
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
