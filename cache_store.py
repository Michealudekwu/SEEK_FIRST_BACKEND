import redis
import hashlib
import os
from dotenv import load_dotenv
load_dotenv()

cache = redis.Redis.from_url(
    os.getenv("REDIS_URL", "redis://localhost:6379/2"), ssl_cert_reqs=None
)

def generate_cache_key(symptoms: str) -> str:
    return "seek:"+hashlib.md5(symptoms.lower().strip().encode()).hexdigest()