from bson import ObjectId

from app.services.cloudinary_service import delete_resume_from_cloudinary
from app.utils.logger import logger
from app.utils.mongo import (
    batches,
    job_descriptions_collection,
    resume_processings_collection,
    resumes_collection,
)


def cleanup_job(job_id: str):
    """
    Executes the complete cleanup workflow for a deleted job.

    Cleanup Order:
        1. Delete uploaded resumes from Cloudinary
        2. Delete ResumeProcessing documents
        3. Delete Resume documents
        4. Delete Batch documents
        5. Delete Job document

    NOTE:
    The Job document is always deleted last to ensure all dependent
    resources are cleaned up first.
    """

    logger.info("=" * 70)
    logger.info(f"Starting cleanup for Job: {job_id}")

    # -------------------------------------------------
    # Build cleanup context
    # -------------------------------------------------
    context = build_cleanup_context(job_id)

    logger.info(
        f"""
Cleanup Context
----------------------------
Job ID              : {job_id}
Resume Processings  : {len(context["processings"])}
Resume Documents    : {len(context["resumes"])}
Batch Documents     : {len(context["batches"])}
----------------------------
"""
    )

    # -------------------------------------------------
    # Step 1 : Remove uploaded resume files
    # -------------------------------------------------
    delete_cloudinary_files(context)

    # -------------------------------------------------
    # Step 2 : Remove ResumeProcessing documents
    # -------------------------------------------------
    delete_resume_processings(context)

    # -------------------------------------------------
    # Step 3 : Remove Resume metadata documents
    # -------------------------------------------------
    delete_resume_documents(context)

    # -------------------------------------------------
    # Step 4 : Remove Batch documents
    # -------------------------------------------------
    delete_batches(context)

    # -------------------------------------------------
    # Step 5 : Remove Job document
    # (Always executed last)
    # -------------------------------------------------
    delete_job_document(context)

    logger.info(
        f"""
Cleanup Summary
----------------------------
Job ID              : {job_id}
Resume Processings  : {len(context["processings"])}
Resume Documents    : {len(context["resumes"])}
Batch Documents     : {len(context["batches"])}
Status              : SUCCESS
----------------------------
"""
    )

    logger.info("=" * 70)


def build_cleanup_context(job_id: str):
    """
    Builds an in-memory snapshot of every resource associated with a job.

    The cleanup process uses this snapshot to avoid performing
    repeated database queries during each cleanup step.
    """

    bson_job_id = ObjectId(job_id)

    # -------------------------------------------------
    # Load Job
    # -------------------------------------------------
    job = job_descriptions_collection.find_one(
        {"_id": bson_job_id}
    )

    if not job:
        raise Exception("Job not found.")

    # -------------------------------------------------
    # Load ResumeProcessing documents
    # -------------------------------------------------
    processings = list(
        resume_processings_collection.find(
            {"jobDescriptionId": bson_job_id}
        )
    )

    # -------------------------------------------------
    # Collect unique Resume IDs
    # -------------------------------------------------
    resume_ids = set()

    for processing in processings:

        resume_object_id = processing.get("resumeObjectId")

        if resume_object_id:
            resume_ids.add(ObjectId(resume_object_id))

    # -------------------------------------------------
    # Load Resume documents
    # -------------------------------------------------
    resumes = []

    if resume_ids:
        resumes = list(
            resumes_collection.find(
                {
                    "_id": {
                        "$in": list(resume_ids)
                    }
                }
            )
        )

    # -------------------------------------------------
    # Load Batch documents
    # -------------------------------------------------
    batches_list = list(
        batches.find(
            {
                "jobDescriptionId": job_id
            }
        )
    )

    return {
        "job": job,
        "processings": processings,
        "resumes": resumes,
        "batches": batches_list,
    }


def delete_cloudinary_files(context):
    """
    Deletes all uploaded resume files from Cloudinary.
    """

    resumes = context["resumes"]

    logger.info(
        f"Starting Cloudinary cleanup ({len(resumes)} files)"
    )

    for index, resume in enumerate(resumes, start=1):

        logger.info(
            f"[{index}/{len(resumes)}] Deleting '{resume['filename']}'"
        )

        delete_resume_from_cloudinary(resume)

    logger.info("Cloudinary cleanup completed.")


def delete_resume_processings(context):
    """
    Deletes all ResumeProcessing documents
    associated with the job.
    """

    processings = context["processings"]

    if not processings:
        logger.info("No ResumeProcessing documents found.")
        return

    job_id = context["job"]["_id"]

    result = resume_processings_collection.delete_many(
        {
            "jobDescriptionId": job_id
        }
    )

    logger.info(
        f"Deleted {result.deleted_count} ResumeProcessing documents."
    )


def delete_resume_documents(context):
    """
    Deletes Resume metadata documents.
    """

    resumes = context["resumes"]

    if not resumes:
        logger.info("No Resume documents found.")
        return

    resume_ids = [
        resume["_id"]
        for resume in resumes
    ]

    result = resumes_collection.delete_many(
        {
            "_id": {
                "$in": resume_ids
            }
        }
    )

    logger.info(
        f"Deleted {result.deleted_count} Resume documents."
    )


def delete_batches(context):
    """
    Deletes all Batch documents
    associated with the job.
    """

    job_id = str(context["job"]["_id"])

    result = batches.delete_many(
        {
            "jobDescriptionId": job_id
        }
    )

    logger.info(
        f"Deleted {result.deleted_count} Batch documents."
    )


def delete_job_document(context):
    """
    Deletes the Job document.

    This must always be the final cleanup step.
    """

    job_id = context["job"]["_id"]

    result = job_descriptions_collection.delete_one(
        {
            "_id": job_id
        }
    )

    logger.info(
        f"Deleted Job document ({result.deleted_count})."
    )