# Configure Cloudinary before using the uploader
from app.utils.cloudinary_config import *

import cloudinary.uploader

from app.utils.logger import logger



def delete_resume_from_cloudinary(resume_doc):
    """
    Deletes a single resume file from Cloudinary.

    This function is intentionally independent from MongoDB.
    It only knows how to delete one uploaded file.
    """

    # -------------------------
    # Build Cloudinary Public ID
    # -------------------------
    folder = resume_doc.get("folder", "resumes")
    filename = resume_doc.get("filename")

    if not filename:
        logger.warning("Resume filename missing. Skipping Cloudinary deletion.")
        return

    public_id = f"{folder}/{filename}"

    try:
        result = cloudinary.uploader.destroy(
            public_id,
        )

        logger.info(
            f"Cloudinary: [{public_id}] -> {result.get('result')}"
        )

    except Exception as e:
        logger.exception(
            f"Failed to delete '{public_id}' from Cloudinary: {e}"
        )
        raise