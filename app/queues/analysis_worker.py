import json
import os
from bson import ObjectId
from datetime import datetime, timezone
from rq import Worker, Queue, job
from redis import Redis
import time
from bson import ObjectId
from app.utils.settings import ANALYSIS_MAX_RETRIES, ANALYSIS_BASE_DELAY

from app.utils.mongo import resume_processings_collection, job_descriptions_collection
from app.analysis.prompt import build_prompt
from app.analysis.runner import run_llm
from app.analysis.validator import validate_analysis_output
from app.utils.logger import logger
from dotenv import load_dotenv

load_dotenv()

ANALYSIS_QUEUE = "analysis-processing"
ANALYSIS_RETRY_SET = os.getenv("ANALYSIS_RETRY_SET", 'rq:analysis-retry')
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379")
redis_conn = Redis.from_url(REDIS_URL)
queue = Queue(ANALYSIS_QUEUE, connection=redis_conn)


class JSONWorker(Worker):

    def execute_job(self, job: job, queue):
        """Executes a single resume-analysis job with retry + safe callbacks."""

        logger.info("===============================================================")
        payload = json.loads(job.data)
        resume_processing_id = payload["resumeProcessingId"]

        rp = resume_processings_collection.find_one({"_id": ObjectId(resume_processing_id)})
        logger.info(f"Analysis started for Resume: {rp.get('externalResumeId')}")
        if not rp:
            logger.info(f"resume processing not found for {resume_processing_id}")
            return

        # Idempotency guard
        if rp.get("analysisStatus") == "completed":
            logger.info("Analysis is already completed!")
            return

        # Mark processing
        resume_processings_collection.update_one(
            {"_id": ObjectId(resume_processing_id)},
            {"$set": {"analysisStatus": "processing"}}
        )
        logger.info("Analysis status is marked as processing.")

        try:
            job_doc = job_descriptions_collection.find_one({"_id": rp["jobDescriptionId"]})

            prompt = build_prompt(
                resume_text=rp["normalizedResumeText"],
                job_text=job_doc["description"],
                explanation=rp.get("explanation", {})
            )

            logger.info("Calling LLM for analysis...")
            llm_response = run_llm(prompt)

            analysis_output = json.loads(llm_response)

            logger.info("Validating response...")
            validate_analysis_output(analysis_output)

            logger.info("Writing updates to database...")

            resume_processings_collection.update_one(
                {"_id": ObjectId(resume_processing_id)},
                {
                    "$set": {
                        "analysis": analysis_output,
                        "analysisStatus": "completed",
                        "analysisCompletedAt": datetime.now(timezone.utc),
                    }
                }
            )
            logger.info("Analysis completed!")

        except Exception as e:
            logger.exception("❌ Phase 5B analysis job failed")

            job_redis_key = f"rq:job:{job.id}"

            # ------------------------------
            # STEP 1 — increment attempts
            # ------------------------------
            attempts = redis_conn.hincrby(job_redis_key, "attempts", 1)

            if attempts <= ANALYSIS_MAX_RETRIES:
                delay = ANALYSIS_BASE_DELAY * (2 ** (attempts - 1))
                next_time = int(time.time()) + delay

                # Schedule retry
                redis_conn.zadd(ANALYSIS_RETRY_SET, {job.id: next_time})

                logger.warning(
                    f"↻ Phase 5B retry scheduled "
                    f"(attempt {attempts}/{ANALYSIS_MAX_RETRIES}) "
                    f"after {delay}s | resumeProcessing={resume_processing_id}"
                )

                # IMPORTANT:
                # Do NOT mark analysis as failed yet
                return True

            # ------------------------------
            # STEP 2 — permanent failure
            # ------------------------------
            resume_processings_collection.update_one(
                {"_id": ObjectId(resume_processing_id)},
                {
                    "$set": {
                        "analysisStatus": "failed",
                        "analysisError": str(e),
                    }
                }
            )

            redis_conn.zrem(ANALYSIS_RETRY_SET, job.id)
            redis_conn.delete(job_redis_key)

            logger.error(
                f"✖ Phase 5B analysis permanently failed "
                f"resumeProcessing={resume_processing_id}"
            )

            return True

if __name__ == "__main__":
    logger.info(f"👷 Analysis Worker started — queue: {ANALYSIS_QUEUE}")
    worker = JSONWorker([queue], connection=redis_conn)
    worker.work()