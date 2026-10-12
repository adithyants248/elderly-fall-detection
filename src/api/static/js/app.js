'use strict';
const eventsNode = document.querySelector('#events');
const message = document.querySelector('#message');
const demo = document.querySelector('#demo');
const cameraReset = document.querySelector('#camera-reset');
let busy = false, lastSnapshot = '', connected = false;
function node(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}
async function api(path, method = 'GET', body) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(path, {method, signal: controller.signal,
      headers: body ? {'Content-Type': 'application/json'} : {},
      body: body ? JSON.stringify(body) : undefined, cache: 'no-store'});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Check the request fields and try again.');
    return data;
  } finally { clearTimeout(timeout); }
}
function caregiver() {
  const id = document.querySelector('#caregiver').value.trim();
  if (!id) throw new Error('Enter a caregiver ID before responding.');
  return id;
}
function button(label, action, className) {
  const b = node('button', label, className);
  b.addEventListener('click', () => perform(action));
  return b;
}
async function perform(action) {
  if (busy) return;
  busy = true;
  message.textContent = '';
  document.querySelectorAll('button').forEach(b => b.disabled = true);
  try { await action(); } catch (error) { message.textContent = error.message; }
  finally {
    busy = false;
    lastSnapshot = '';
    await refresh();
    if (!connected) document.querySelectorAll('#events button').forEach(b => b.disabled = false);
  }
}
function render(events) {
  const active = events.filter(e => e.status !== 'ACKNOWLEDGED').length;
  document.querySelector('#count').textContent = String(active);
  const fragment = document.createDocumentFragment();
  if (!active) fragment.append(node('p', 'No alerts awaiting review. Camera monitoring status is shown above.', 'empty'));
  for (const event of [...events].reverse()) {
    const card = node('article', undefined, 'event');
    if (event.status !== 'ACKNOWLEDGED') card.classList.add('needs-review');
    const path = '/api/falls/' + encodeURIComponent(event.event_id);
    if (event.simulated) card.append(node('span', 'DEMO / SIMULATED FALL', 'badge'));
    else card.append(node('span', 'AI / VERIFIED EVENT', 'badge'));
    const recorded = event.emergency_response?.status === 'RESPONSE_RECORDED';
    card.append(node('h3', recorded ? 'RESPONSE RECORDED' : event.status === 'ACKNOWLEDGED' ? '✓ Fall acknowledged' : '🚨 FALL DETECTED', event.status === 'ACKNOWLEDGED' ? 'success' : 'alert'));
    const details = node('dl', undefined, 'details');
    for (const [label, value] of [
      ['Person ID', event.person_id], ['Fall probability', event.detection_probability === null ? 'Unavailable' : (event.detection_probability * 100).toFixed(1) + '%'],
      ['Verification', event.simulated ? 'Simulated confirmation' : 'Confirmed fall'],
      ['Received', new Date(event.created_at).toLocaleString()], ['Current status', event.status],
      ...(event.acknowledged_by ? [['Acknowledged by', event.acknowledged_by]] : [])]) {
      const group = node('div'); group.append(node('dt', label), node('dd', value)); details.append(group);
    }
    card.append(details);
    const technical = node('details', undefined, 'technical');
    technical.append(node('summary', 'Technical event details'),
      node('p', 'Event ID: ' + event.event_id, 'muted'),
      node('p', 'Detection source time: ' + event.timestamp + ' s (not wall-clock time)', 'muted'));
    card.append(technical);
    const timeline = node('ol', undefined, 'timeline');
    const responseState = event.emergency_response;
    for (const [title, done, detail] of [
      ['Fall detected', true, event.simulated ? 'Demo event injected' : 'Received ' + new Date(event.created_at).toLocaleString()],
      ['Verification', true, event.simulated ? 'Simulated; AI not run' : 'Confirmed by AI pipeline'],
      ['Caregiver notified', event.status !== 'CONFIRMED', 'Local mock alert; no push delivery'],
      ['Acknowledged', event.status === 'ACKNOWLEDGED', event.acknowledged_at ? new Date(event.acknowledged_at).toLocaleString() : 'Awaiting caregiver review'],
      ['Hospital selected', !!responseState?.selected_hospital_id, responseState?.selected_hospital_name || 'Choose a mock hospital'],
      ['Emergency response recorded', recorded, recorded ? 'Mock record only' : 'Not recorded']]) {
      const step = node('li', (done ? '✓ ' : '○ ') + title, done ? 'done' : '');
      step.append(node('small', detail)); timeline.append(step);
    }
    card.append(timeline);
    if (event.status !== 'ACKNOWLEDGED') {
      card.append(button('ACKNOWLEDGE FALL', async () => {
        await api(path + '/acknowledge', 'POST', {caregiver_id: caregiver()});
        await api(path + '/hospitals');
      }));
    } else {
      const response = event.emergency_response;
      card.append(node('h3', 'Nearby Hospitals'), node('p', 'Fictional demo hospitals · Geographic distance from mock coordinates, not road distance.', 'muted'));
      if (!response || response.status === 'ACKNOWLEDGED') {
        card.append(node('p', 'Hospital options have not been loaded or none were returned.'));
        card.append(button('LOAD MOCK HOSPITALS', () => api(path + '/hospitals')));
      } else if (response.status === 'HOSPITALS_AVAILABLE') {
        const list = node('div', undefined, 'hospitals');
        for (const hospital of response.hospitals) {
          const item = node('div', undefined, 'hospital');
          item.append(node('h4', hospital.name), node('p', hospital.distance_km.toFixed(2) + ' km'), node('p', hospital.address),
            button('SELECT', () => api(path + '/hospital', 'POST', {hospital_id: hospital.hospital_id, caregiver_id: caregiver()})));
          list.append(item);
        }
        card.append(list);
      } else {
        card.append(node('p', 'Hospital selected: ' + response.selected_hospital_name, 'success'));
        const hospital = response.hospitals.find(h => h.hospital_id === response.selected_hospital_id);
        if (hospital) card.append(node('p', hospital.address + ' · ' + hospital.distance_km.toFixed(2) + ' km'));
        if (response.status === 'HOSPITAL_SELECTED') card.append(button('RECORD EMERGENCY RESPONSE', () => api(path + '/emergency-response', 'POST')));
        else card.append(node('p', '✓ Mock emergency response recorded successfully. No hospital contacted or ambulance dispatched.', 'success'));
      }
    }
    fragment.append(card);
  }
  eventsNode.replaceChildren(fragment);
}
async function refresh() {
  if (busy) return;
  try {
    const events = await api('/api/falls');
    if (busy) return;
    if (!connected && message.textContent.startsWith('Connection unavailable.')) message.textContent = '';
    connected = true;
    document.querySelector('#connection').textContent = '● API connected';
    const snapshot = JSON.stringify(events);
    if (snapshot !== lastSnapshot) { render(events); lastSnapshot = snapshot; }
    document.querySelectorAll('#events button').forEach(b => b.disabled = false);
  } catch (error) {
    connected = false;
    lastSnapshot = '';
    document.querySelector('#connection').textContent = '○ Offline · retrying';
    document.querySelector('#count').textContent = '—';
    message.textContent = 'Connection unavailable. Displayed events may be out of date.';
  }
  demo.disabled = !connected || demo.hidden;
}
demo.addEventListener('click', () => perform(() => api('/api/demo/fall', 'POST')));
cameraReset.addEventListener('click', () => perform(() => api('/api/system/camera/reset', 'POST')));
async function refreshCamera() {
  try {
    const status = await api('/api/system/status');
    const labels = {disabled: 'Disabled', starting: 'Starting', running: 'Running',
      unavailable: 'Unavailable', stopped: 'Stopped', error: 'Error'};
    const age = status.last_frame_at ? Date.now() - Date.parse(status.last_frame_at) : 0;
    const stale = status.camera_status === 'running' && age > 10000;
    document.querySelector('#camera-status').textContent = 'AI Camera: ' +
      (stale ? 'Waiting for frames' : (labels[status.camera_status] || 'Unknown'));
    document.querySelector('#camera-detail').textContent =
      (stale ? 'No completed frame in the last 10 seconds. Check the camera/AI worker.' : status.message) +
      (status.pending_events ? ' Alerts awaiting ingestion: ' + status.pending_events + '.' : '') +
      (status.latched_events ? ' Confirmed episodes remain latched until explicitly rearmed.' : '');
    const d = status.diagnostics || {};
    const live = status.camera_status === 'running' && !!status.last_frame_at && !stale;
    const state = live ? d.state : null;
    const awaitingRearm = state === 'CONFIRMED_FALL' && d.reason === 'awaiting_reset';
    const stateLabel = awaitingRearm ? 'Previous fall confirmed — awaiting camera rearm' : state === 'CONFIRMED_FALL' ? 'CONFIRMED FALL' : state === 'FALL_SUSPECTED' ? 'FALL SUSPECTED' : state === 'NORMAL' && d.temporal_ready && d.person_detected === 1 ? 'NORMAL' : 'MONITORING';
    document.querySelector('.monitor-hero').dataset.tone = state === 'CONFIRMED_FALL' ? 'danger' : stateLabel === 'NORMAL' ? 'good' : 'warning';
    document.querySelector('#live-label').textContent = live ? 'LIVE OBSERVATIONS' : 'MONITORING NOT LIVE';
    document.querySelector('#monitor-state').textContent = live ? stateLabel : stale ? 'Waiting for camera frames' : 'Monitoring unavailable';
    document.querySelector('#monitor-summary').textContent = live ? (d.person_detected === 0 ? 'No person detected in the latest observation.' : d.temporal_ready ? 'Latest camera observations are being checked for fall activity.' : 'Preparing the observation history for AI monitoring.') : status.message;
    document.querySelector('#person-state').textContent = !live ? 'Unavailable' : d.person_detected === 1 ? 'Person detected' : d.person_detected === 0 ? 'No person detected' : 'Unavailable';
    document.querySelector('#last-observation').textContent = status.last_frame_at ? 'Last frame: ' + new Date(status.last_frame_at).toLocaleTimeString() : 'No observation received';
    document.querySelector('#ai-status').textContent = !live ? labels[status.ai_status] || 'Unavailable' : d.temporal_ready ? 'Ready' : 'Warming up';
    document.querySelector('#state-status').textContent = live ? stateLabel : 'Unavailable';
    const diagnostics = document.querySelector('#diagnostic-details');
    diagnostics.replaceChildren();
    for (const [name, value] of [['Frames processed', status.frames_processed], ['Fall probability', d.fall_probability == null ? 'Unavailable' : (d.fall_probability * 100).toFixed(1) + '%'], ['Buffer frames', d.buffer_frames ?? 'Unavailable'], ['Verifier reason', d.reason || 'Unavailable'], ['Onset supported', d.transition_supported == null ? 'Unavailable' : String(d.transition_supported)], ['Pending delivery', status.pending_events]]) {
      const group = node('div'); group.append(node('dt', name), node('dd', String(value))); diagnostics.append(group);
    }
    cameraReset.hidden = status.camera_status !== 'running' || !status.latched_events;
    cameraReset.disabled = busy || !!status.pending_events || status.reset_requested;
    document.querySelector('#camera-reset-help').hidden = cameraReset.hidden;
  } catch (error) {
    document.querySelector('.monitor-hero').dataset.tone = 'warning';
    document.querySelector('#live-label').textContent = 'MONITORING NOT LIVE';
    document.querySelector('#monitor-state').textContent = 'Monitoring unavailable';
    document.querySelector('#monitor-summary').textContent = 'Backend connection unavailable. Last observations may be out of date.';
    for (const id of ['person-state', 'ai-status', 'state-status']) document.querySelector('#' + id).textContent = 'Unavailable';
    document.querySelector('#camera-status').textContent = 'AI Camera: Status unavailable';
    document.querySelector('#camera-detail').textContent = 'Camera monitoring could not be verified. Demo and event requests remain separate.';
    cameraReset.hidden = true;
    document.querySelector('#camera-reset-help').hidden = true;
  }
}
async function poll() { await Promise.all([refresh(), refreshCamera()]); setTimeout(poll, 2000); }
api('/api/health').then(data => { demo.hidden = !data.demo_enabled; }).catch(() => {});
poll();
