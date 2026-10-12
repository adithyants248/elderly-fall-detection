"""Run with python -m uvicorn src.api.app:app --host 0.0.0.0 --port 8000."""
import logging
import os
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from fastapi import FastAPI, Path as ApiPath, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from src.caregiver.models import (CaregiverError, EventNotFoundError,
                                  DuplicateEventError, InvalidTransitionError)
from src.hospital.models import (HospitalError, ResponseNotFoundError, HospitalNotFoundError,
    EventNotAcknowledgedError, InvalidResponseStateError, DuplicateResponseError, EmergencyResponse)
from .context import ApplicationContext
from .models import AcknowledgeRequest, HospitalSelectionRequest, FallView, RecordedView, SystemStatus
from .camera import CameraConfig, CameraWorker, create_source

ROOT = Path(__file__).resolve().parent
EventID = Annotated[str, ApiPath(min_length=1, max_length=160, pattern=r'^\S(?:.*\S)?$')]


def create_app(context: ApplicationContext | None = None, *, camera_config=None,
               camera_source_factory=create_source):
    context = context if context is not None else ApplicationContext(
        demo_enabled=os.getenv('FALL_DEMO_ENABLED', '1') == '1')
    camera = CameraWorker(context, camera_config, source_factory=camera_source_factory)

    @asynccontextmanager
    async def lifespan(app):
        camera.start()
        try:
            yield
        finally:
            await asyncio.to_thread(camera.stop)

    app = FastAPI(title='Smart Elderly Fall Detection — Local Prototype', debug=False, lifespan=lifespan)
    # Flutter Web uses a changing localhost port during development.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(?:localhost|127\.0\.0\.1)(?::[0-9]+)?",
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.state.context = context
    app.state.camera = camera
    app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')

    async def domain_error(request: Request, exc: ValueError):
        if isinstance(exc, (EventNotFoundError, ResponseNotFoundError, HospitalNotFoundError)):
            status = 404
        elif isinstance(exc, (DuplicateEventError, InvalidTransitionError, EventNotAcknowledgedError,
                              InvalidResponseStateError, DuplicateResponseError)):
            status = 409
        else:
            status = 422
        return JSONResponse(status_code=status, content={'detail': str(exc)})

    app.add_exception_handler(CaregiverError, domain_error)
    app.add_exception_handler(HospitalError, domain_error)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logging.getLogger(__name__).exception('Application request failed')
        return JSONResponse(status_code=500, content={'detail': 'Request failed. Please retry.'})

    @app.get('/', include_in_schema=False)
    def dashboard():
        return FileResponse(ROOT / 'templates' / 'dashboard.html')

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'demo_enabled': context.demo_enabled,
                'hospital_data': 'mock', 'location': 'fictional demo coordinates; no GPS'}

    @app.get('/api/system/status', response_model=SystemStatus)
    def system_status():
        return camera.status()

    @app.post('/api/system/camera/reset', response_model=SystemStatus, status_code=202)
    def reset_camera_episode():
        return camera.request_reset()

    @app.get('/api/falls', response_model=list[FallView])
    def falls():
        with context.lock:
            return [context.view(e) for e in context.falls.list_all()]

    @app.get('/api/falls/{event_id}', response_model=FallView)
    def fall(event_id: EventID):
        with context.lock:
            return context.view(context.caregiver.get_event(event_id))

    @app.post('/api/falls/{event_id}/acknowledge', response_model=FallView)
    def acknowledge(event_id: EventID, body: AcknowledgeRequest):
        with context.lock:
            return context.view(context.caregiver.acknowledge_event(event_id, body.caregiver_id))

    @app.get('/api/falls/{event_id}/hospitals', response_model=EmergencyResponse)
    def hospitals(event_id: EventID):
        with context.lock:
            return context.hospital.start_response(event_id, context.location)

    @app.post('/api/falls/{event_id}/hospital', response_model=EmergencyResponse)
    def select(event_id: EventID, body: HospitalSelectionRequest):
        with context.lock:
            response = context.response_for(event_id)
            return context.hospital.select_hospital(response.response_id, body.hospital_id, body.caregiver_id)

    @app.post('/api/falls/{event_id}/emergency-response', response_model=RecordedView)
    def record(event_id: EventID):
        with context.lock:
            response = context.response_for(event_id)
            return RecordedView(response=context.hospital.record_response(response.response_id))

    @app.post('/api/demo/fall', response_model=FallView, status_code=201)
    def demo():
        if not context.demo_enabled:
            raise HTTPException(404, 'Demo injection is disabled.')
        return context.demo_fall()

    return app


# Factory calls are hardware-free by default, including tests. Only the server
# entry point opts into environment-configured camera ownership.
app = create_app(camera_config=CameraConfig.from_env())
