"""HTTP contracts using the actual domain services, without ML dependencies."""
import unittest
from unittest.mock import Mock
from fastapi.testclient import TestClient
from src.api.app import create_app
from src.api.context import ApplicationContext


class APITests(unittest.TestCase):
    def setUp(self):
        self.context = ApplicationContext()
        self.client = TestClient(create_app(self.context))
        self.addCleanup(self.client.close)

    def demo(self):
        response = self.client.post('/api/demo/fall')
        self.assertEqual(response.status_code, 201)
        return response.json()

    def acknowledge(self, event):
        response = self.client.post('/api/falls/' + event['event_id'] + '/acknowledge', json={'caregiver_id': 'c1'})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def offered(self):
        event = self.demo()
        self.acknowledge(event)
        path = '/api/falls/' + event['event_id']
        response = self.client.get(path + '/hospitals')
        self.assertEqual(response.status_code, 200)
        return path, response.json()

    def test_health(self):
        response = self.client.get('/api/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')

    def test_empty(self):
        self.assertEqual(self.client.get('/api/falls').json(), [])

    def test_dashboard_assets_and_docs(self):
        for path, text in (('/', 'Smart Elderly'), ('/static/js/app.js', 'setTimeout(poll, 2000)'),
                           ('/static/css/style.css', '@media'), ('/docs', 'swagger'), ('/openapi.json', '/api/falls')):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn(text, response.text)

    def test_demo_is_labeled_and_retrievable(self):
        event = self.demo()
        self.assertTrue(event['simulated'])
        self.assertTrue(event['event_id'].startswith('DEMO-'))
        self.assertEqual(event['status'], 'ALERT_SENT')
        self.assertEqual(self.client.get('/api/falls/' + event['event_id']).json(), event)
        self.assertEqual(self.client.get('/api/falls').json(), [event])
        self.assertNotIn('metadata', event)

    def test_demo_disabled(self):
        with TestClient(create_app(ApplicationContext(demo_enabled=False))) as client:
            self.assertEqual(client.post('/api/demo/fall').status_code, 404)
            self.assertEqual(client.get('/api/falls').json(), [])

    def test_missing_event_routes(self):
        for method, suffix, body in [('get', '', None), ('get', '/hospitals', None),
            ('post', '/acknowledge', {'caregiver_id': 'c1'}),
            ('post', '/hospital', {'caregiver_id': 'c1', 'hospital_id': 'MOCK-H001'}),
            ('post', '/emergency-response', None)]:
            with self.subTest(suffix=suffix):
                self.assertEqual(self.client.request(method, '/api/falls/missing' + suffix, json=body).status_code, 404)

    def test_acknowledgement_replay_and_conflict(self):
        event = self.demo()
        ack = self.acknowledge(event)
        self.assertEqual(ack['status'], 'ACKNOWLEDGED')
        self.assertEqual(ack['acknowledged_by'], 'c1')
        self.assertEqual(self.acknowledge(event), ack)
        self.assertEqual(self.client.post('/api/falls/' + event['event_id'] + '/acknowledge',
            json={'caregiver_id': 'c2'}).status_code, 409)

    def test_unacknowledged_hospitals_rejected(self):
        event = self.demo()
        self.assertEqual(self.client.get('/api/falls/' + event['event_id'] + '/hospitals').status_code, 409)
        self.assertEqual(self.context.responses.list_all(), [])

    def test_offered_hospitals_and_cached_search(self):
        path, response = self.offered()
        self.assertEqual(response['status'], 'HOSPITALS_AVAILABLE')
        self.assertEqual(len(response['hospitals']), 3)
        self.assertEqual(self.client.get(path + '/hospitals').json(), response)
        self.assertEqual(len(self.context.responses.list_all()), 1)

    def test_invalid_hospital_and_premature_record(self):
        path, response = self.offered()
        self.assertEqual(self.client.post(path + '/hospital', json={
            'hospital_id': 'unknown', 'caregiver_id': 'c1'}).status_code, 404)
        self.assertEqual(self.client.post(path + '/emergency-response').status_code, 409)
        self.assertEqual(self.client.get(path + '/hospitals').json(), response)

    def test_selection_before_offers(self):
        event = self.demo()
        self.acknowledge(event)
        self.assertEqual(self.client.post('/api/falls/' + event['event_id'] + '/hospital',
            json={'hospital_id': 'MOCK-H001', 'caregiver_id': 'c1'}).status_code, 404)

    def test_complete_flow_duplicate_record_and_refresh(self):
        path, offered = self.offered()
        selection = {'hospital_id': offered['hospitals'][1]['hospital_id'], 'caregiver_id': 'c1'}
        selected = self.client.post(path + '/hospital', json=selection)
        self.assertEqual(selected.status_code, 200)
        self.assertEqual(selected.json()['status'], 'HOSPITAL_SELECTED')
        self.assertEqual(self.client.post(path + '/hospital', json=selection).json(), selected.json())
        final = self.client.post(path + '/emergency-response')
        self.assertEqual(final.status_code, 200)
        self.assertTrue(final.json()['mock'])
        self.assertEqual(final.json()['response']['status'], 'RESPONSE_RECORDED')
        self.assertEqual(self.client.post(path + '/emergency-response').json(), final.json())
        self.assertEqual(self.client.get(path).json()['emergency_response'], final.json()['response'])
        self.assertEqual(len(self.context.hospital.emergency_service.recorded_requests), 1)

    def test_request_validation(self):
        event = self.demo()
        path = '/api/falls/' + event['event_id']
        for body in ({}, {'caregiver_id': ''}, {'caregiver_id': '   '}, {'caregiver_id': 1},
                     {'caregiver_id': 'c1', 'extra': True}, {'caregiver_id': 'x' * 161}):
            with self.subTest(body=body):
                self.assertEqual(self.client.post(path + '/acknowledge', json=body).status_code, 422)
        self.assertEqual(self.client.post(path + '/hospital', json={'caregiver_id': 'c1', 'hospital_id': ''}).status_code, 422)
        self.assertEqual(self.client.get('/api/falls/%20').status_code, 422)
        self.assertEqual(self.client.get('/api/falls/' + 'a' * 161).status_code, 422)

    def test_missing_location(self):
        self.context.location = None
        event = self.demo()
        self.acknowledge(event)
        response = self.client.get('/api/falls/' + event['event_id'] + '/hospitals')
        self.assertEqual(response.status_code, 422)
        self.assertIn('without a Location', response.json()['detail'])

    def test_multiple_events_and_isolated_apps(self):
        first, second = self.demo(), self.demo()
        self.assertNotEqual(first['event_id'], second['event_id'])
        self.acknowledge(first)
        self.assertEqual(self.client.get('/api/falls/' + second['event_id']).json()['status'], 'ALERT_SENT')
        with TestClient(create_app()) as other:
            self.assertEqual(other.get('/api/falls').json(), [])

    def test_verifier_adapter_shared_repository_and_duplicate_delivery(self):
        result = {'state': 'CONFIRMED_FALL', 'event': {'type': 'confirmed_fall',
            'event_id': 'AI-1', 'track_id': 1, 'timestamp': 3, 'fall_probability': .87}}
        self.context.consume_verification_result(result)
        self.context.consume_verification_result(result)
        events = self.client.get('/api/falls').json()
        self.assertEqual(len(events), 1)
        self.assertFalse(events[0]['simulated'])
        self.assertEqual(events[0]['event_id'], 'AI-1')

    def test_nonconfirmed_or_latched_result_does_not_inject(self):
        for state in ('NORMAL', 'FALL_SUSPECTED', 'CONFIRMED_FALL'):
            self.assertIsNone(self.context.consume_verification_result({'state': state, 'event': None}))
        self.assertEqual(self.client.get('/api/falls').json(), [])

    def test_unexpected_failure_hides_traceback(self):
        self.context.falls.list_all = Mock(side_effect=RuntimeError('private debug details'))
        with TestClient(create_app(self.context), raise_server_exceptions=False) as client:
            response = client.get('/api/falls')
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.json(), {'detail': 'Request failed. Please retry.'})
