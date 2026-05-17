from celery import Celery
import os
from dotenv import load_dotenv
load_dotenv()

celery = Celery(
    "seek",
    broker=os.getenv("REDIS_URL"),
    backend=os.getenv("REDIS_URL"),
    include=["tasker"]
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_time_limit=60,          # kill task if it runs longer than 60s
    worker_concurrency=1,        # 5 tasks processed simultaneously
    worker_pool = "solo",
)