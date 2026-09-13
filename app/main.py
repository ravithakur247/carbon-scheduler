import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from . import scheduler, store
from .carbon import provider
from .config import settings
from .models import InferenceRequest, JobRecord, JobStatus

_bg_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    global _bg_task
    _bg_task = asyncio.create_task(scheduler.scheduler_loop())
    yield
    _bg_task.cancel()


app = FastAPI(title="Carbon-Aware Inference Scheduler", lifespan=lifespan)


@app.post("/infer", response_model=JobRecord)
async def infer(request: InferenceRequest):
    job = JobRecord(
        id=str(uuid.uuid4())[:8],
        status=JobStatus.QUEUED,
        prompt=request.prompt,
        urgent=request.urgent,
        estimated_tokens=request.estimated_tokens,
        submitted_at=time.time(),
        max_wait_minutes=request.max_wait_minutes,
    )
    job = await scheduler.submit_job(job)
    return job


@app.get("/status/{job_id}", response_model=JobRecord)
async def status(job_id: str):
    job = await store.get_job(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job


@app.get("/carbon")
async def carbon_now():
    return await provider.get_intensity_all(settings.REGIONS)


@app.get("/stats")
async def stats():
    global_stats = await store.get_stats()
    depth = await store.queue_depth()
    return {**global_stats, "queue_depth": depth}


@app.get("/jobs")
async def jobs(limit: int = 25):
    return await store.recent_jobs(limit)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    with open("app/static/dashboard.html") as f:
        return f.read()


@app.get("/")
async def root():
    return {
        "service": "carbon-aware-inference-scheduler",
        "docs": "/docs",
        "dashboard": "/dashboard",
        "regions": settings.REGIONS,
        "clean_threshold_g_per_kwh": settings.CLEAN_THRESHOLD_G_PER_KWH,
    }
