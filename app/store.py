"""
Thin persistence layer on top of Redis.

Layout:
  job:{id}          -> hash of JobRecord fields (JSON-encoded values)
  queue:pending      -> sorted set, score = unix timestamp of "next check time"
  queue:jobset       -> set of job ids currently queued (for fast lookups)
  stats:global       -> hash of running totals (co2_saved_g, co2_emitted_g, jobs_completed)
"""
import json
import time
from typing import Optional

import redis.asyncio as redis

from .config import settings
from .models import JobRecord, JobStatus

_redis: Optional[redis.Redis] = None


def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def _job_key(job_id: str) -> str:
    return f"job:{job_id}"


async def save_job(job: JobRecord) -> None:
    r = get_redis()
    await r.set(_job_key(job.id), job.model_dump_json())


async def get_job(job_id: str) -> Optional[JobRecord]:
    r = get_redis()
    raw = await r.get(_job_key(job_id))
    if raw is None:
        return None
    return JobRecord.model_validate_json(raw)


async def enqueue(job: JobRecord, ready_check_at: float) -> None:
    r = get_redis()
    await save_job(job)
    await r.zadd("queue:pending", {job.id: ready_check_at})
    await r.sadd("queue:jobset", job.id)


async def dequeue(job_id: str) -> None:
    r = get_redis()
    await r.zrem("queue:pending", job_id)
    await r.srem("queue:jobset", job_id)


async def due_jobs(now: Optional[float] = None) -> list[str]:
    """Job ids whose scheduled check-time has passed."""
    r = get_redis()
    now = now or time.time()
    return await r.zrangebyscore("queue:pending", min=0, max=now)


async def reschedule(job_id: str, next_check_at: float) -> None:
    r = get_redis()
    await r.zadd("queue:pending", {job_id: next_check_at})


async def queue_depth() -> int:
    r = get_redis()
    return await r.zcard("queue:pending")


async def bump_stats(co2_saved_g: float, co2_emitted_g: float) -> None:
    r = get_redis()
    await r.hincrbyfloat("stats:global", "co2_saved_g", co2_saved_g)
    await r.hincrbyfloat("stats:global", "co2_emitted_g", co2_emitted_g)
    await r.hincrby("stats:global", "jobs_completed", 1)


async def get_stats() -> dict:
    r = get_redis()
    raw = await r.hgetall("stats:global")
    return {
        "co2_saved_g": float(raw.get("co2_saved_g", 0) or 0),
        "co2_emitted_g": float(raw.get("co2_emitted_g", 0) or 0),
        "jobs_completed": int(raw.get("jobs_completed", 0) or 0),
    }


async def recent_jobs(limit: int = 25) -> list[JobRecord]:
    """Best-effort recent job list by scanning job:* keys (fine at MVP scale)."""
    r = get_redis()
    keys = [k async for k in r.scan_iter(match="job:*")]
    jobs = []
    for k in keys:
        raw = await r.get(k)
        if raw:
            jobs.append(JobRecord.model_validate_json(raw))
    jobs.sort(key=lambda j: j.submitted_at, reverse=True)
    return jobs[:limit]
