"""Disposable actual HTTP/server/camera smoke test; stores diagnostics, no images.

Uses FALL_CAMERA_* environment configuration. Never performs physical actions.
Run separately from an existing server (default smoke-test port 8001).
"""
import argparse
import json
import threading
import time

import httpx
import uvicorn


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=float, default=30)
    parser.add_argument('--port', type=int, default=8001)
    parser.add_argument('--browser', action='store_true')
    args = parser.parse_args()
    from src.api.app import app
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=args.port, log_level='warning'))
    thread = threading.Thread(target=server.run)
    thread.start()
    report = {'statuses': []}
    try:
        deadline = time.monotonic() + 30
        while not server.started:
            if not thread.is_alive() or time.monotonic() >= deadline:
                raise RuntimeError('Server did not start')
            time.sleep(.1)
        with httpx.Client(base_url=f'http://127.0.0.1:{args.port}', timeout=10) as client:
            report['dashboard_http'] = client.get('/').status_code
            deadline = time.monotonic() + args.seconds
            while time.monotonic() < deadline:
                status = client.get('/api/system/status')
                status.raise_for_status()
                report['statuses'].append(status.json())
                time.sleep(2)
            report['camera_events_before_demo'] = client.get('/api/falls').json()
            event = client.post('/api/demo/fall')
            assert event.status_code == 201
            assert event.json()['simulated']
            path = '/api/falls/' + event.json()['event_id']
            client.post(path + '/acknowledge', json={'caregiver_id': 'smoke-test'}).raise_for_status()
            offered = client.get(path + '/hospitals').json()
            client.post(path + '/hospital', json={
                'caregiver_id': 'smoke-test', 'hospital_id': offered['hospitals'][0]['hospital_id']
            }).raise_for_status()
            response = client.post(path + '/emergency-response')
            response.raise_for_status()
            assert response.json()['response']['status'] == 'RESPONSE_RECORDED'
            report['demo_workflow'] = 'RESPONSE_RECORDED'
            if args.browser:
                from scripts.check_dashboard_browser import main as check_browser
                check_browser(f'http://127.0.0.1:{args.port}')
                report['browser_workflow'] = 'passed'
    finally:
        server.should_exit = True
        thread.join()
        report['shutdown_status'] = app.state.camera.status()
        print(json.dumps(report, indent=2, default=str))


if __name__ == '__main__':
    main()
