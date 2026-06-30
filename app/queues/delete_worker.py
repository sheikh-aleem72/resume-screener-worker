from dotenv import load_dotenv
import json
import os

import redis
from rq import Queue, Worker, job

from app.services.cleanup import cleanup_job
from app.utils.logger import logger

# ---------------------------------------------------------
# Load environment variables
# ---------------------------------------------------------
load_dotenv()

# ---------------------------------------------------------
# Worker Configuration
# ---------------------------------------------------------
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379")
QUEUE_NAME = os.getenv("DELETE_QUEUE_NAME", "job-cleanup")

# ---------------------------------------------------------
# Redis Connection
# ---------------------------------------------------------
redis_conn = redis.from_url(REDIS_URL)
queue = Queue(QUEUE_NAME, connection=redis_conn)


class JSONWorker(Worker):
    """
    Custom RQ worker responsible for consuming
    job-cleanup tasks from Redis.
    """

    def execute_job(self, job: job, queue):
        """
        Entry point for every cleanup task.

        Payload Example:
        {
            "jobId": "<Mongo Job Id>"
        }
        """

        payload = json.loads(job.data)
        job_id = payload["jobId"]

        logger.info(f"Starting cleanup for Job: {job_id}")

        cleanup_job(job_id)


if __name__ == "__main__":
    logger.info(f"Delete Worker started — queue: {QUEUE_NAME}")

    worker = JSONWorker(
        [queue],
        connection=redis_conn,
    )

    worker.work()