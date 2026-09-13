"""
The brain of the system.

For each non-urgent job:
  1. Check carbon intensity across all configured regions.
  2. If the greenest region is below the clean threshold, OR the job has
     hit its max-wait deadline, run it now (routed to that greenest region).
  3. Otherwise, reschedule a re-check in POLL_INTERVAL_SECONDS.

Runs as an asyncio background task started at app startup — no separate
worker process needed for the MVP (swap for a real worker pool / Celery /
arq if you outgrow a single process).
"""
import asyncio
import logging
import time

from . import store
from .carbon import provider
from .config import settings
from .inference import run_inference
from .models import JobRecord, JobStatus

logger = logging.getLogger("scheduler")

HOME_REGION = settings.REGIONS[0]


async def _execute(job: JobRecord, region: str, intensity: float) -> None:
    job.status = JobStatus.RUNNING
    job.started_at = time.time()
    job.region_used = region
    job.carbon_intensity_at_run = intensity
    await store.save_job(job)

    result, energy_kwh = await run_inference(job.prompt, job.estimated_tokens)

    actual_co2 = energy_kwh * intensity
    baseline_intensity = job.carbon_intensity_at_submit or intensity
    baseline_co2 = energy_kwh * baseline_intensity
    co2_saved = max(0.0, baseline_co2 - actual_co2)

    job.status = JobStatus.COMPLETED
    job.completed_at = time.time()
    job.energy_kwh = round(energy_kwh, 6)
    job.co2_emitted_g = round(actual_co2, 3)
    job.co2_saved_g = round(co2_saved, 3)
    job.delayed_by_minutes = round((job.started_at - job.submitted_at) / 60, 2)
    job.result = result
    await store.save_job(job)
    await store.dequeue(job.id)
    await store.bump_stats(co2_saved_g=co2_saved, co2_emitted_g=actual_co2)

    logger.info(
        "Job %s completed in %s (intensity=%.1f gCO2/kWh, saved=%.2fg, delayed=%.1fmin)",
        job.id, region, intensity, co2_saved, job.delayed_by_minutes,
    )


async def submit_job(job: JobRecord) -> JobRecord:
    """Entry point called by the API. Decides run-now vs queue."""
    intensities = await provider.get_intensity_all(settings.REGIONS)
    home_intensity = intensities[HOME_REGION]
    job.carbon_intensity_at_submit = home_intensity

    if job.urgent:
        best_region, best_intensity = min(intensities.items(), key=lambda kv: kv[1])
        await _execute(job, best_region, best_intensity)
        return job

    best_region, best_intensity = min(intensities.items(), key=lambda kv: kv[1])
    if best_intensity <= settings.CLEAN_THRESHOLD_G_PER_KWH:
        await _execute(job, best_region, best_intensity)
        return job

    # Not clean enough yet — queue it.
    max_wait = job.max_wait_minutes if job.max_wait_minutes is not None else settings.MAX_WAIT_MINUTES
    job.scheduled_for = job.submitted_at + max_wait * 60
    job.status = JobStatus.QUEUED
    await store.enqueue(job, ready_check_at=time.time() + settings.POLL_INTERVAL_SECONDS)
    logger.info(
        "Job %s queued (current best=%.1f gCO2/kWh in %s > threshold %.1f)",
        job.id, best_intensity, best_region, settings.CLEAN_THRESHOLD_G_PER_KWH,
    )
    return job


async def _tick() -> None:
    now = time.time()
    due_ids = await store.due_jobs(now)
    for job_id in due_ids:
        job = await store.get_job(job_id)
        if job is None or job.status != JobStatus.QUEUED:
            await store.dequeue(job_id)
            continue

        intensities = await provider.get_intensity_all(settings.REGIONS)
        best_region, best_intensity = min(intensities.items(), key=lambda kv: kv[1])
        deadline_hit = job.scheduled_for is not None and now >= job.scheduled_for

        if best_intensity <= settings.CLEAN_THRESHOLD_G_PER_KWH or deadline_hit:
            await _execute(job, best_region, best_intensity)
        else:
            await store.reschedule(job_id, now + settings.POLL_INTERVAL_SECONDS)


async def scheduler_loop() -> None:
    logger.info("Scheduler loop started (poll every %ss, threshold %.0f gCO2/kWh)",
                settings.POLL_INTERVAL_SECONDS, settings.CLEAN_THRESHOLD_G_PER_KWH)
    while True:
        try:
            await _tick()
        except Exception:
            logger.exception("Scheduler tick failed")
        await asyncio.sleep(min(5, settings.POLL_INTERVAL_SECONDS))
