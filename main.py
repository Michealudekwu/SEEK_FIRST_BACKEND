from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from schema import DoctorsReportRequest, StartRequest, CompleteRequest
from cache_store import generate_cache_key, cache
from celery.result import AsyncResult
from tasker import run_start_pipeline, run_complete_pipeline, run_doctors_report_pipeline
import json
import asyncio
import os
from dotenv import load_dotenv
load_dotenv()

app = FastAPI()

origins = os.getenv("CORS_ALLOWED_ORIGINS", []).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins = origins,
    allow_credentials = True,
    allow_methods = ['*'],
    allow_headers = ['*'],
)

# @app.on_event("startup")
# def check_redis():
#     try:
#         print(f"redis server is... {"connected" if cache.ping else "Not connected"}")
#     except Exception as e:
#         print("Redis connection failed:", e)

async def wait_for_result(task_id: str, timeout: int =60):
    for _ in range(timeout *2):
        task_result = AsyncResult(task_id)

        if task_result.ready():
            if task_result.successful():
                return task_result.result
            else:
                return {
                    "error" : "Pipline failed",
                    "status_code" : 504
                }

        await asyncio.sleep(0.5)

    return {
        "error" : "request timed out",
        "status_code" : 504
    }

@app.post("/api/start")
async def start_session(request: StartRequest):
    symps = request.symptoms

    if not symps:
        return {
            "Error" : "Failed to get user symptoms"
        }, 400
    
    cache_key = generate_cache_key(symps)
    cached_response = cache.get(cache_key)

    if cached_response:
        # print("Cache hit for key:", cache_key)
        return json.loads(cached_response)

    task = run_start_pipeline.delay(symps)

    result = await wait_for_result(task_id=task.id)

    if "error" in result:
        return{
            "error": result["error"],
            "status_code": result.get("status_code", 500)
        }

    cache.setex(cache_key, 3600, json.dumps(result))
    return result

@app.post("/api/complete")
async def complete_session(request: CompleteRequest):
    symptoms = request.structured_symptoms
    questions = request.questions
    answer = request.answers

    task = run_complete_pipeline.delay(symptoms, questions, answer)
    result = await wait_for_result(task_id= task.id)

    if "error" in result:
        return{
            "error": result["error"],
            "status_code": result.get("status_code", 500)
        }

    return result

@app.post("/api/doctors-report")
async def doctors_report(request: DoctorsReportRequest):
    result = request.result
    if result is None:
        return {
            "error": True,
            "message": "No result data provided. Please run complete_session() first and provide its output.",
        }, 400
    
    task = run_doctors_report_pipeline.delay(result)
    result = await wait_for_result(task_id= task.id)

    if "error" in result:
        return{
            "error": result["error"],
            "status_code": result.get("status_code", 500)
        }

    return result
    
