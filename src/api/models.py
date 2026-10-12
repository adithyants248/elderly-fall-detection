"""Validated transport contracts; domain state transitions stay in services."""
from datetime import datetime
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, StringConstraints, Field
from src.caregiver.models import EventStatus
from src.hospital.models import EmergencyResponse

Identifier = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=160)]


class AcknowledgeRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    caregiver_id: Identifier


class HospitalSelectionRequest(AcknowledgeRequest):
    hospital_id: Identifier


class FallView(BaseModel):
    event_id: str
    person_id: str
    timestamp: float
    detection_probability: float | None
    status: EventStatus
    created_at: datetime
    acknowledged_at: datetime | None
    acknowledged_by: str | None
    simulated: bool
    emergency_response: EmergencyResponse | None


class RecordedView(BaseModel):
    mock: bool = True
    message: str = 'Mock emergency response recorded successfully. No hospital contacted or ambulance dispatched.'
    response: EmergencyResponse


WorkerState = Literal['disabled', 'starting', 'running', 'unavailable', 'stopped', 'error']


class SystemStatus(BaseModel):
    camera_enabled: bool
    camera_status: WorkerState
    ai_status: WorkerState
    message: str
    frames_processed: int
    last_frame_at: datetime | None
    pending_events: int
    latched_events: int
    reset_requested: bool
    diagnostics: dict = Field(default_factory=dict)
