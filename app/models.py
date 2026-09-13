from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class InferenceRequest(BaseModel):
    prompt: str = Field(..., description="The prompt / job payload")
    urgent: bool = Field(False, description="If true, bypasses the scheduler and runs immediately")
    estimated_tokens: int = Field(500, ge=1, description="Expected output tokens, used for energy estimate")
    max_wait_minutes: Optional[int] = Field(
        None, description="Override the default max wait before the job is forced to run"
    )


class JobRecord(BaseModel):
    id: str
    status: JobStatus
    prompt: str
    urgent: bool
    estimated_tokens: int
    submitted_at: float
    max_wait_minutes: Optional[int] = None
    scheduled_for: Optional[float] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    region_used: Optional[str] = None
    carbon_intensity_at_run: Optional[float] = None
    carbon_intensity_at_submit: Optional[float] = None
    energy_kwh: Optional[float] = None
    co2_emitted_g: Optional[float] = None
    co2_saved_g: Optional[float] = None
    delayed_by_minutes: Optional[float] = None
    result: Optional[str] = None
