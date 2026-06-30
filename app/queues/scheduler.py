import time
import os
import redis
from dotenv import load_dotenv

# -----------------------------
# ENV CONFIG
# -----------------------------
load_dotenv()
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379")
POLL_INTERVAL = float(os.getenv("RETRY_SCHED_POLL_INTERVAL", "1"))  # seconds

# Queue → Retry ZSET mapping
RETRY_CONFIGS = [
    {
        "queue": os.getenv("BATCH_QUEUE_NAME", "batch-processing"),
        "retry_set": os.getenv("BATCH_RETRY_SET", "rq:retry"),
    },
    {
        "queue": os.getenv("ANALYSIS_QUEUE_NAME", "analysis-processing"),
        "retry_set": os.getenv("ANALYSIS_RETRY_SET", "rq:analysis-retry"),
    },
    {
        'queue': os.getenv("DELETE_QUEUE_NAME", 'job-cleanup'),
        "retry_set": os.getenv("DELETE_RETRY_SET","rq:delete-retry"),
    }

]

# -----------------------------
# REDIS CONNECTION
# -----------------------------
r = redis.from_url(REDIS_URL)


def move_due_jobs(queue_name: str, retry_set: str) -> int:
    """Moves due retry jobs back into their processing queue."""
    now = int(time.time())

    job_ids = r.zrangebyscore(retry_set, 0, now)
    if not job_ids:
        return 0

    pipeline = r.pipeline()
    for job_id in job_ids:
        pipeline.lpush(f"rq:queue:{queue_name}", job_id)
        pipeline.zrem(retry_set, job_id)
    pipeline.execute()

    print(
        f"↪ Re-queued {len(job_ids)} job(s) "
        f"into '{queue_name}' from '{retry_set}' at {now}"
    )
    return len(job_ids)


if __name__ == "__main__":
    print("⏳ Retry Scheduler Started")
    for cfg in RETRY_CONFIGS:
        print(
            f"Watching retry-set '{cfg['retry_set']}' "
            f"→ queue '{cfg['queue']}'"
        )

    while True:
        try:
            for cfg in RETRY_CONFIGS:
                move_due_jobs(cfg["queue"], cfg["retry_set"])
        except Exception as e:
            print(f"⚠ Scheduler error: {e}")

        time.sleep(POLL_INTERVAL)
