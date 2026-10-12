"""Same-process lifecycle and domain integration; no real camera or model."""
from copy import deepcopy
from threading import Event, get_ident
import time
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from src.api.app import create_app
from src.api.camera import CameraConfig, CameraWorker
from src.api.context import ApplicationContext
from src.core.fall_detection.camera import CameraUnavailable
from src.core.fall_verification.post_fall import PostFallVerifier


def confirmed(event_id="CAMERA-1", track_id=7):
    return {"state": "CONFIRMED_FALL", "event": {"type": "confirmed_fall",
        "event_id": event_id, "track_id": track_id, "timestamp": 3.0,
        "suspected_at": 0.0, "fall_probability": 0.87}}


def eventually(predicate):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("Worker did not reach the expected state")


class FakeSource:
    def __init__(self, results=(), *, open_error=None, read_error=None, eof=False):
        self.results = iter(results)
        self.open_error, self.read_error, self.eof = open_error, read_error, eof
        self.opened, self.closed = Event(), Event()
        self.reset_calls = []
        self.threads = []

    def open(self):
        self.threads.append(get_ident())
        self.opened.set()
        if self.open_error:
            raise self.open_error

    def read(self):
        self.threads.append(get_ident())
        if self.read_error:
            raise self.read_error
        time.sleep(.002)
        try:
            return object(), iter([next(self.results)])
        except StopIteration:
            return None if self.eof else (object(), iter([]))

    def reset(self, track_id):
        self.threads.append(get_ident())
        self.reset_calls.append(track_id)

    def close(self):
        self.threads.append(get_ident())
        self.closed.set()


class CameraIntegrationTests(unittest.TestCase):
    def test_real_inference_transition_diagnostics_reach_status(self):
        from test_live_safety import pipeline, step
        pipeline_instance = pipeline()
        results = [step(pipeline_instance, i) for i in range(61)]
        source = FakeSource(results, eof=True)
        with TestClient(self.app(source)) as client:
            eventually(lambda: source.closed.is_set())
            response = client.get('/api/system/status')
            self.assertEqual(response.status_code, 200)
            diagnostic = response.json()['diagnostics']['transition_diagnostics']
            self.assertEqual(diagnostic, results[-1]['transition_diagnostics'])
            self.assertEqual(diagnostic['history_rows'], 1)
            self.assertEqual(diagnostic['false_reason'], 'route_thresholds_not_met')
            self.assertFalse(diagnostic['geometry_supported'])
            self.assertFalse(diagnostic['temporal']['baseline_ready'])
            self.assertEqual(diagnostic['temporal']['rejection_reason'], 'collecting_baseline')
            self.assertFalse(diagnostic['candidate_allowed'])

    def app(self, source, context=None):
        self.context = context or ApplicationContext()
        self.application = create_app(self.context, camera_config=CameraConfig(enabled=True),
                                      camera_source_factory=lambda config: source)
        return self.application

    def test_disabled_does_not_construct_source_and_demo_still_works(self):
        factory = Mock(side_effect=AssertionError("camera must stay disabled"))
        with TestClient(create_app(camera_source_factory=factory)) as client:
            self.assertEqual(client.get('/api/system/status').json()['camera_status'], 'disabled')
            self.assertEqual(client.get('/').status_code, 200)
            self.assertEqual(client.get('/docs').status_code, 200)
            self.assertEqual(client.post('/api/demo/fall').status_code, 201)
        factory.assert_not_called()

    def test_factory_is_disabled_even_when_host_environment_enables_camera(self):
        with patch.dict('os.environ', {'FALL_CAMERA_ENABLED': '1'}):
            with TestClient(create_app()) as client:
                self.assertFalse(client.get('/api/system/status').json()['camera_enabled'])

    def test_environment_config(self):
        with patch.dict('os.environ', {'FALL_CAMERA_ENABLED': '1', 'FALL_CAMERA_SOURCE': 'clip.mp4',
                        'FALL_CAMERA_DEVICE': 'cpu', 'FALL_CAMERA_SELECTION': 'tracked'}):
            self.assertEqual(CameraConfig.from_env(), CameraConfig(True, 'clip.mp4', 'tracked', 'cpu'))

    def test_startup_running_shutdown_and_resource_ownership(self):
        source = FakeSource()
        with TestClient(self.app(source)) as client:
            eventually(lambda: client.get('/api/system/status').json()['camera_status'] == 'running')
            status = client.get('/api/system/status').json()
            self.assertGreater(status['frames_processed'], 0)
            self.assertIsNotNone(status['last_frame_at'])
            worker = self.application.state.camera
            worker.start()  # Idempotent; no second capture thread.
            self.assertNotEqual(source.threads[0], get_ident())
        self.assertTrue(source.closed.is_set())
        self.assertFalse(worker._thread.is_alive())
        self.assertEqual(worker.status()['camera_status'], 'stopped')
        self.assertEqual(len(set(source.threads)), 1)

    def test_starting_is_visible_without_blocking_api(self):
        source = FakeSource()
        gate = Event()
        source.open = lambda: gate.wait(5)
        try:
            with TestClient(self.app(source)) as client:
                self.assertEqual(client.get('/api/system/status').json()['camera_status'], 'starting')
                self.assertEqual(client.post('/api/demo/fall').status_code, 201)
                gate.set()
        finally:
            gate.set()

    def test_unavailable_camera_keeps_api_and_demo_alive(self):
        source = FakeSource(open_error=CameraUnavailable('private device details'))
        with TestClient(self.app(source)) as client:
            eventually(lambda: client.get('/api/system/status').json()['camera_status'] == 'unavailable')
            self.assertNotIn('private', client.get('/api/system/status').text)
            self.assertEqual(client.get('/api/health').status_code, 200)
            self.assertEqual(client.post('/api/demo/fall').status_code, 201)
        self.assertTrue(source.closed.is_set())

    def test_model_initialization_failure_is_sanitized(self):
        with TestClient(self.app(FakeSource(open_error=RuntimeError('secret model path')))) as client:
            eventually(lambda: client.get('/api/system/status').json()['ai_status'] == 'error')
            self.assertNotIn('secret', client.get('/api/system/status').text)
            self.assertEqual(client.post('/api/demo/fall').status_code, 201)

    def test_inference_failure_does_not_crash_server(self):
        source = FakeSource(read_error=RuntimeError('inference failed'))
        with TestClient(self.app(source)) as client:
            eventually(lambda: client.get('/api/system/status').json()['camera_status'] == 'error')
            self.assertEqual(client.get('/api/falls').json(), [])
        self.assertTrue(source.closed.is_set())

    def test_eof_is_stopped_and_releases_source(self):
        source = FakeSource(eof=True)
        with TestClient(self.app(source)) as client:
            eventually(lambda: source.closed.is_set())
            self.assertEqual(client.get('/api/system/status').json()['camera_status'], 'stopped')

    def test_exact_result_uses_context_and_existing_adapter(self):
        result = confirmed()
        context = ApplicationContext()
        consumer = Mock(wraps=context.consume_verification_result)
        context.consume_verification_result = consumer
        from src.caregiver.adapter import consume_verification_result as adapter
        with patch('src.api.context.consume_verification_result', wraps=adapter) as spy:
            with TestClient(self.app(FakeSource([result]), context)) as client:
                eventually(lambda: bool(client.get('/api/falls').json()))
                consumer.assert_called_once_with(result)
                spy.assert_called_once_with(result, context.caregiver, person_id=None)
                event = client.get('/api/falls').json()[0]
                self.assertEqual(event['event_id'], 'CAMERA-1')
                self.assertEqual(event['status'], 'ALERT_SENT')
                self.assertFalse(event['simulated'])

    def test_duplicate_and_latched_results_send_one_alert(self):
        result = confirmed()
        source = FakeSource([result, result, {'state': 'CONFIRMED_FALL', 'event': None}])
        with TestClient(self.app(source)) as client:
            eventually(lambda: self.application.state.camera.status()['frames_processed'] >= 3)
            self.assertEqual(len(client.get('/api/falls').json()), 1)
            self.assertEqual(len(self.context.caregiver.notifier.sent_alerts), 1)
            self.assertEqual(source.reset_calls, [])

    def test_nonconfirmed_never_creates_fall(self):
        source = FakeSource([{'state': s, 'event': None} for s in ('NORMAL', 'FALL_SUSPECTED')])
        with TestClient(self.app(source)) as client:
            eventually(lambda: self.application.state.camera.status()['frames_processed'] >= 2)
            self.assertEqual(client.get('/api/falls').json(), [])

    def test_failed_ingestion_retained_then_retried_after_eof(self):
        context = ApplicationContext()
        accept = context.consume_verification_result
        context.consume_verification_result = Mock(side_effect=OSError('temporary failure'))
        source = FakeSource([confirmed()], eof=True)
        worker = CameraWorker(context, CameraConfig(enabled=True), source_factory=lambda _: source,
                              retry_seconds=.01)
        worker.start()
        try:
            eventually(lambda: source.closed.is_set() and worker.status()['pending_events'] == 1)
            self.assertEqual(context.falls.list_all(), [])
            context.consume_verification_result.side_effect = accept
            eventually(lambda: worker.status()['pending_events'] == 0)
            self.assertEqual(len(context.falls.list_all()), 1)
        finally:
            worker.stop()

    def test_partial_acceptance_retry_deduplicates_existing_alert(self):
        context = ApplicationContext()
        accept = context.consume_verification_result
        calls = []
        def flaky(result):
            event = accept(result)
            calls.append(result)
            if len(calls) == 1:
                raise OSError('failure after ingestion')
            return event
        context.consume_verification_result = flaky
        with TestClient(self.app(FakeSource([confirmed()], eof=True), context)):
            eventually(lambda: len(calls) >= 2)
        self.assertEqual(len(context.falls.list_all()), 1)
        self.assertEqual(len(context.caregiver.notifier.sent_alerts), 1)
        self.assertEqual(calls[0], calls[1])

    def test_shutdown_keeps_failed_payload_in_memory(self):
        context = ApplicationContext()
        result = confirmed()
        context.consume_verification_result = Mock(side_effect=OSError('failed'))
        source = FakeSource([result])
        worker = CameraWorker(context, CameraConfig(enabled=True), source_factory=lambda _: source)
        worker.start()
        eventually(lambda: worker.status()['pending_events'] == 1)
        worker.stop()
        self.assertEqual(worker._pending['CAMERA-1'], result)
        self.assertFalse(worker._thread.is_alive())

    def test_real_verifier_to_complete_existing_workflow(self):
        verifier = PostFallVerifier()
        raw = dict.fromkeys(verifier.config.motion_limits(), 0.0)
        raw['person_detected'] = 1
        results = [verifier.update(17, .30, raw, i / 10) for i in range(32)]
        source = FakeSource(results)
        with TestClient(self.app(source)) as client:
            eventually(lambda: bool(client.get('/api/falls').json()))
            event = client.get('/api/falls').json()[0]
            path = '/api/falls/' + event['event_id']
            self.assertEqual(client.get(path + '/hospitals').status_code, 409)
            self.assertEqual(client.post(path + '/acknowledge', json={'caregiver_id': 'c1'}).status_code, 200)
            offered = client.get(path + '/hospitals').json()
            self.assertEqual(client.post(path + '/hospital', json={'caregiver_id': 'c1',
                             'hospital_id': offered['hospitals'][1]['hospital_id']}).status_code, 200)
            recorded = client.post(path + '/emergency-response').json()
            self.assertTrue(recorded['mock'])
            self.assertEqual(recorded['response']['status'], 'RESPONSE_RECORDED')
            self.assertEqual(client.get(path).json()['emergency_response'], recorded['response'])
            self.assertEqual(source.reset_calls, [])
            self.assertEqual(verifier.update(17, .1, raw, 4)['state'], 'CONFIRMED_FALL')

    def test_explicit_rearm_requires_ack_and_runs_on_worker_thread(self):
        source = FakeSource([confirmed()])
        with TestClient(self.app(source)) as client:
            eventually(lambda: self.application.state.camera.status()['camera_status'] == 'running')
            self.assertEqual(client.post('/api/system/camera/reset').status_code, 409)
            client.post('/api/falls/CAMERA-1/acknowledge', json={'caregiver_id': 'c1'})
            original = client.get('/api/falls/CAMERA-1').json()
            self.assertEqual(source.reset_calls, [])
            self.assertEqual(client.post('/api/system/camera/reset').status_code, 202)
            eventually(lambda: source.reset_calls == [7])
            self.assertEqual(client.get('/api/falls/CAMERA-1').json(), original)
            self.assertEqual(self.application.state.camera.status()['latched_events'], 0)
        self.assertEqual(len(set(source.threads)), 1)

    def test_rearm_disabled_is_rejected(self):
        with TestClient(create_app()) as client:
            self.assertEqual(client.post('/api/system/camera/reset').status_code, 409)

    def test_delivery_survives_later_person_failure_in_same_frame(self):
        source = FakeSource()
        def results():
            yield confirmed()
            raise RuntimeError('second person model failed')
        source.read = lambda: (object(), results())
        with TestClient(self.app(source)) as client:
            eventually(lambda: client.get('/api/system/status').json()['camera_status'] == 'error')
            self.assertEqual(client.get('/api/falls').json()[0]['event_id'], 'CAMERA-1')

    def test_failed_consumer_cannot_mutate_retained_result(self):
        context = ApplicationContext()
        accept = context.consume_verification_result
        calls = []
        def consumer(result):
            calls.append(deepcopy(result))
            if len(calls) == 1:
                result['event']['track_id'] = 'changed'
                raise OSError('failed after mutation')
            return accept(result)
        context.consume_verification_result = consumer
        with TestClient(self.app(FakeSource([confirmed()], eof=True), context)):
            eventually(lambda: len(calls) == 2)
        self.assertEqual(calls[0], calls[1])

    def test_ui_contains_worker_status_and_retains_demo(self):
        with TestClient(create_app()) as client:
            html = client.get('/').text
            self.assertIn('AI CAMERA', html)
            self.assertIn('SIMULATE DEMO FALL', html)
            js = client.get('/static/js/app.js').text
            self.assertIn('/api/system/status', js)
            self.assertIn('DEMO / SIMULATED FALL', js)
            self.assertIn('AI / VERIFIED EVENT', js)
