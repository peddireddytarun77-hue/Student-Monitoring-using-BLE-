"""
Smart Attendance System - Complete Backend
==========================================
All-in-one: Flask API + MediaPipe FRS + BLE Scanner + Supabase DB
Run: python backend.py
Dashboard opens at: http://127.0.0.1:5000

Attendance Logic:
  - Window: 09:00 – 16:50 (Mon–Fri)
  - Activation: FRS + BLE presence → marks attendance "present" (once per day)
  - ESP broadcasts every 5 sec → backend detects signal
  - On confirmed BLE signal → logs a 1-min TimeLapse window in presence_log
  - total_present_minutes in attendance is updated incrementally
  - last_seen timestamp updated on every confirmed ESP signal
  - At 16:50 a day-end snapshot consolidates the final status
"""

import cv2, json, time, threading, asyncio, os
from dotenv import load_dotenv
load_dotenv()  # Load secrets from .env file
import numpy as np
import mediapipe as mp
from collections import defaultdict
import face_recognition
from flask import Flask, Response, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
from supabase import create_client, Client
from datetime import date, datetime, timedelta
import bleak



# Faces saved locally in project/faces/ folder
FACES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'faces')
os.makedirs(FACES_DIR, exist_ok=True)

# ─────────────────────────────────────────────
#  CONFIG  (edit if needed)
# ─────────────────────────────────────────────
SUPABASE_URL       = os.getenv("SUPABASE_URL", "https://giuwlorzwpbfrfablcva.supabase.co")
SUPABASE_KEY       = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImdpdXdsb3J6d3BiZnJmYWJsY3ZhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjgxMjc2MTEsImV4cCI6MjA4MzcwMzYxMX0.PnNwRmpeSmUhO0gfcPYYh6oMje2h9uCa3k8lpGLfV00")
CAMERA_INDEX       = 0        # 0 = built-in webcam
FACE_THRESHOLD     = 0.50     # Strictness: lower = stricter match
BLE_SCAN_TIMEOUT   = 5.0      # seconds per BLE scan cycle

# ── Attendance Window & Breaks ───────────────
ATT_START_H, ATT_START_M = 9,  0     # 09:00
ATT_END_H,   ATT_END_M   = 16, 50    # 16:50

# Break definitions (Start Hour, Start Min, End Hour, End Min)
BREAKS = [
    (10, 40, 10, 50),
    (12, 30, 13, 20),
    (15, 0,  15, 10)
]

# ── ESP TimeLapse Window ───────────────────────
# If at least 1 ESP signal is received within TIMELAPSE_SECONDS,
# a 1-minute window of presence is logged.
TIMELAPSE_SECONDS = 60   # 1 minute timelapse window

# ─────────────────────────────────────────────
#  INIT: Flask, Supabase, MediaPipe
# ─────────────────────────────────────────────
app      = Flask(__name__)
CORS(app)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# MediaPipe face detector (model_selection=1 = full-range up to ~5m)
_mp_det      = mp.solutions.face_detection
face_detector = _mp_det.FaceDetection(model_selection=1, min_detection_confidence=0.60)

# ─────────────────────────────────────────────
#  SHARED STATE  (protected by threading locks)
# ─────────────────────────────────────────────
_cam_lock  = threading.Lock()
_rec_lock  = threading.Lock()
_ble_lock  = threading.Lock()
_esp_lock  = threading.Lock()

_camera           = None
_rec_active       = False
_rec_result       = {}
_temp_face_enc    = None
_temp_face_img    = None
_known_encodings  = []
_known_students   = []
_ble_map          = {}
_ble_active       = False
_ble_reload_flag  = threading.Event()
_last_frame_time  = 0

# ── ESP Signal State ───────────────────────────
# Maps student_id → {'window_start': datetime, 'signal_count': int, 'last_signal': datetime}
_esp_state = {}

# ─────────────────────────────────────────────
#  ATTENDANCE WINDOW HELPERS
# ─────────────────────────────────────────────
def _in_attendance_window():
    """Returns True if current time is within the allowed attendance window, and NOT in a break."""
    now = datetime.now()
    start = now.replace(hour=ATT_START_H, minute=ATT_START_M, second=0, microsecond=0)
    end   = now.replace(hour=ATT_END_H,   minute=ATT_END_M,   second=0, microsecond=0)
    
    if not (start <= now <= end):
        return False
        
    for (bh1, bm1, bh2, bm2) in BREAKS:
        b_start = now.replace(hour=bh1, minute=bm1, second=0, microsecond=0)
        b_end   = now.replace(hour=bh2, minute=bm2, second=0, microsecond=0)
        if b_start <= now < b_end:
            return False # Inside a break
    return True

def _is_end_of_day():
    """Returns True if we are at/past 16:50 today."""
    now = datetime.now()
    end = now.replace(hour=ATT_END_H, minute=ATT_END_M, second=0, microsecond=0)
    return now >= end

def _recently_ended_break():
    """Returns True if a break ended within the last minute. Checks for FRS proxy prevention."""
    now = datetime.now()
    for (bh1, bm1, bh2, bm2) in BREAKS:
        b_end = now.replace(hour=bh2, minute=bm2, second=0, microsecond=0)
        if 0 <= (now - b_end).total_seconds() < 60:
            return True
    return False

# ─────────────────────────────────────────────
#  CAMERA HELPERS
# ─────────────────────────────────────────────
def _get_camera():
    global _camera
    if _camera is None or not _camera.isOpened():
        _camera = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
        _camera.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        _camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    return _camera

def _read_frame():
    global _last_frame_time
    _last_frame_time = time.time()
    with _cam_lock:
        cam = _get_camera()
        ok, frame = cam.read()
    return frame if ok else None

def _camera_cleanup_loop():
    """Background loop to release camera hardware if idle to save battery."""
    global _camera
    while True:
        if _camera is not None and (time.time() - _last_frame_time > 5):
            if not _rec_active:
                with _cam_lock:
                    if _camera is not None:
                        print("[CAM] Idle timeout -> Releasing hardware (Battery Save)")
                        _camera.release()
                        _camera = None
        time.sleep(2)

# ─────────────────────────────────────────────
#  MEDIAPIPE: Detect face, draw box, crop face
# ─────────────────────────────────────────────
def detect_face(frame):
    h, w  = frame.shape[:2]
    rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    res   = face_detector.process(rgb)
    drawn = frame.copy()
    crop  = None

    if res.detections:
        det  = res.detections[0]
        bb   = det.location_data.relative_bounding_box
        x1   = max(0, int(bb.xmin * w))
        y1   = max(0, int(bb.ymin * h))
        x2   = min(w, int((bb.xmin + bb.width)  * w))
        y2   = min(h, int((bb.ymin + bb.height) * h))
        conf = det.score[0]

        cv2.rectangle(drawn, (x1, y1), (x2, y2), (0, 255, 100), 2)
        label = f"Face {conf:.0%}"
        cv2.putText(drawn, label, (x1, max(0, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 100), 1)

        p   = 20
        crop = frame[max(0,y1-p):min(h,y2+p), max(0,x1-p):min(w,x2+p)]

    return drawn, crop

# ─────────────────────────────────────────────
#  FACE RECOGNITION HELPERS
# ─────────────────────────────────────────────
def _encode(face_bgr):
    rgb  = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
    encs = face_recognition.face_encodings(rgb)
    return encs[0] if encs else None

def _match(enc):
    if not _known_encodings:
        return None, 0.0
    dists = face_recognition.face_distance(_known_encodings, enc)
    idx   = int(np.argmin(dists))
    dist  = dists[idx]
    if dist < FACE_THRESHOLD:
        return _known_students[idx], round((1 - dist) * 100, 1)
    return None, 0.0

def _load_faces():
    global _known_encodings, _known_students
    _known_encodings = []
    _known_students  = []
    try:
        rows = supabase.table('face_encodings').select(
            '*, students(id, name, roll_no, class_name)'
        ).execute().data
        if rows:
            for r in rows:
                enc_data = json.loads(r['encoding'])
                _known_encodings.append(np.array(enc_data))
                _known_students.append(r['students'])
        print(f"[FRS] {len(_known_encodings)} face(s) loaded from DB")
    except Exception as e:
        print(f"[FRS] Load error: {e}")

# ─────────────────────────────────────────────
#  RECOGNITION BACKGROUND THREAD
# ─────────────────────────────────────────────
def _recognition_thread():
    global _rec_result
    _load_faces()
    while True:
        if not _rec_active:
            time.sleep(0.1)
            continue
        if time.time() - _last_frame_time > 10:
            time.sleep(1.0)
            continue

        frame = _read_frame()
        if frame is None:
            time.sleep(0.1)
            continue

        _, crop = detect_face(frame)

        if crop is None:
            with _rec_lock:
                _rec_result = {'face_detected': False}
            time.sleep(0.1)
            continue

        enc = _encode(crop)
        if enc is None:
            with _rec_lock:
                _rec_result = {'face_detected': True, 'face_identified': False}
            time.sleep(0.1)
            continue

        student, conf = _match(enc)
        with _rec_lock:
            if student:
                _rec_result = {
                    'face_detected':   True,
                    'face_identified': True,
                    'student_id':      student['id'],
                    'student_name':    student['name'],
                    'roll_no':         student['roll_no'],
                    'class':           student['class_name'],
                    'confidence':      conf
                }
            else:
                _rec_result = {'face_detected': True, 'face_identified': False}

        time.sleep(0.3)

# ─────────────────────────────────────────────
#  VIDEO FEED (MJPEG stream with face box)
# ─────────────────────────────────────────────
def _gen_frames():
    while True:
        frame = _read_frame()
        if frame is None:
            time.sleep(0.05)
            continue
        annotated, _ = detect_face(frame)
        _, buf = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
               + buf.tobytes() + b'\r\n')
        time.sleep(0.04)

# ─────────────────────────────────────────────
#  ESP TIMELAPSE PRESENCE LOGGER
# ─────────────────────────────────────────────
def _record_esp_signal(student_id: str):
    """
    Called every time a registered ESP device is seen in a BLE scan.
    Logic:
      - Groups signals into 1-minute windows (TimeLapse)
      - After TIMELAPSE_SECONDS of first signal, flushes the window:
        * logs a row in presence_log
        * increments total_present_minutes in attendance
        * updates last_seen in attendance
    """
    now = datetime.now()
    with _esp_lock:
        state = _esp_state.get(student_id)

        if state is None or (now - state['window_start']).total_seconds() >= TIMELAPSE_SECONDS:
            # Start a new 1-min window
            if state is not None and state['signal_count'] >= 1:
                # Flush the old window → write to DB
                _flush_presence_window(student_id, state['window_start'], state['signal_count'])

            _esp_state[student_id] = {
                'window_start':  now,
                'signal_count':  1,
                'last_signal':   now
            }
        else:
            # Accumulate signals within the same window
            _esp_state[student_id]['signal_count'] += 1
            _esp_state[student_id]['last_signal']   = now

def _flush_presence_window(student_id: str, window_start: datetime, signal_count: int):
    """Write a one-minute presence window to DB. Called from inside _esp_lock."""
    today = date.today().isoformat()
    try:
        # 1) Log in presence_log table
        supabase.table('presence_log').upsert({
            'student_id':  student_id,
            'log_date':    today,
            'window_ts':   window_start.isoformat(),
            'esp_signals': signal_count
        }, on_conflict='student_id,window_ts').execute()

        # 2) Update attendance: increment minutes + last_seen
        existing = supabase.table('attendance').select('id, total_present_minutes') \
            .eq('student_id', student_id).eq('date', today).execute().data
        if existing:
            att = existing[0]
            new_mins = (att.get('total_present_minutes') or 0) + 1
            supabase.table('attendance').update({
                'total_present_minutes': new_mins,
                'last_seen': datetime.now().isoformat()
            }).eq('id', att['id']).execute()
            print(f"[ESP] Flushed window for {student_id}: +1 min → {new_mins} min total")
    except Exception as e:
        print(f"[ESP] Flush error for {student_id}: {e}")

def _esp_timelapse_watchdog():
    """
    Runs every 30 sec. Flushes any 1-min windows that ended
    but haven't been flushed (e.g., student leaves mid-window).
    Also runs the end-of-day status consolidation at 16:50.
    """
    _eod_done = {'done': False, 'last_date': None}
    while True:
        now  = datetime.now()
        today = date.today().isoformat()

        # Flush stale open windows
        with _esp_lock:
            for sid, state in list(_esp_state.items()):
                elapsed = (now - state['window_start']).total_seconds()
                if elapsed >= TIMELAPSE_SECONDS and state['signal_count'] >= 1:
                    _flush_presence_window(sid, state['window_start'], state['signal_count'])
                    _esp_state[sid] = None  # Mark as flushed (next signal starts fresh)

            # Clean None entries
            for sid in [k for k, v in _esp_state.items() if v is None]:
                del _esp_state[sid]

        # Check for 5-minute missing students & notify/mark suspicious
        try:
            time_threshold = (now - timedelta(minutes=5)).isoformat()
            missing = supabase.table('attendance').select('*, students(name)').eq('date', today).eq('status', 'present').lt('last_seen', time_threshold).execute().data
            for m in missing:
                print(f"[ALERT] Staff Notification: Student {m['students']['name']} missing for > 5 mins!")
                supabase.table('attendance').update({'status': 'suspicious', 'ble_verified': False}).eq('id', m['id']).execute()
        except:
            pass

        # Reset Face Verification immediately after break times (Enforce FRS after break)
        if _recently_ended_break():
            print("[BREAK OVER] Resetting face_verified for everyone to prevent proxies!")
            try:
                present_students = supabase.table('attendance').select('id').eq('date', today).eq('face_verified', True).execute().data
                for s in present_students:
                    supabase.table('attendance').update({'face_verified': False, 'status': 'suspicious'}).eq('id', s['id']).execute()
            except:
                pass

        # End-of-day consolidation at 16:50
        if _is_end_of_day() and not _eod_done['done']:
            _eod_done['done'] = True
            _eod_done['last_date'] = today
            _run_eod_consolidation(today)
            print(f"[EOD] End-of-day consolidation done for {today}")

        # Reset EOD flag on next day
        if _eod_done['last_date'] and _eod_done['last_date'] != today:
            _eod_done['done'] = False

        time.sleep(30)

def _run_eod_consolidation(today: str):
    """
    At end of day (16:50), review all attendance records:
    - If student has total_present_minutes >= 1 → keep 'present'
    - If face_verified but no BLE → keep 'suspicious'
    - Leave 'absent' as-is
    This is idempotent — safe to run multiple times.
    """
    try:
        # 1. Promote absent accumulated people
        rows = supabase.table('attendance').select('*').eq('date', today).execute().data
        for row in rows:
            if row['status'] == 'absent' and row.get('total_present_minutes', 0) > 0:
                supabase.table('attendance').update({'status': 'present', 'ble_verified': True}).eq('id', row['id']).execute()
        
        # 2. Dump previous days to trash/history table
        try:
            old_rows = supabase.table('attendance').select('*').neq('date', today).execute().data
            for r in old_rows:
                supabase.table('attendance_history').upsert(r).execute()
                supabase.table('attendance').delete().eq('id', r['id']).execute()
            if old_rows:
                print(f"[EOD] Moved {len(old_rows)} old rows to attendance_history trash table.")
        except Exception as hist_e:
            print(f"[EOD] Warning: Could not dump history (Create tables if needed) - {hist_e}")

        print(f"[EOD] Consolidated {len(rows)} attendance records for {today}")
    except Exception as e:
        print(f"[EOD] Consolidation error: {e}")

# ─────────────────────────────────────────────
#  BLE SCANNER (async, in background thread)
# ─────────────────────────────────────────────
async def _ble_loop():
    from bleak import BleakScanner
    registered = {}
    _last_reg_reload = 0

    def _reload_registered():
        nonlocal registered, _last_reg_reload
        try:
            rows = supabase.table('ble_devices').select(
                'mac_address, device_name, student_id, students(name)'
            ).eq('is_active', True).execute().data
            registered = {r['mac_address'].upper(): r for r in rows}
            _last_reg_reload = time.time()
            print(f"[BLE] {len(registered)} registered device(s) loaded.")
        except Exception as e:
            print(f"[BLE] Could not load devices: {e}")

    _reload_registered()

    while _ble_active:
        if _ble_reload_flag.is_set() or time.time() - _last_reg_reload > 60:
            _reload_registered()
            _ble_reload_flag.clear()

        try:
            found = await BleakScanner.discover(
                timeout=BLE_SCAN_TIMEOUT, return_adv=True
            )
            new_map = {}
            matched = []
            for mac_raw, (device, adv) in found.items():
                mac  = mac_raw.upper()
                rssi = adv.rssi if hasattr(adv, 'rssi') else -99
                reg  = registered.get(mac)
                
                entry = {
                    'mac':          mac,
                    'name':         device.name or adv.local_name or 'Unknown',
                    'rssi':         rssi,
                    'registered':   False, 
                    'device_name':  None,
                    'student_id':   None,
                    'student_name': None
                }

                if reg:
                    entry.update({
                        'registered':   True,
                        'device_name':  reg['device_name'],
                        'student_id':   reg['student_id'],
                        'student_name': reg['students']['name'] if reg.get('students') else None
                    })
                    matched.append(mac)

                new_map[mac] = entry

            with _ble_lock:
                _ble_map.clear()
                _ble_map.update(new_map)

            print(f"[BLE] Scan: {len(new_map)} found, {len(matched)} registered match(es): {matched}")

            # ── ESP Signal Recording (TimeLapse) ──────────────────
            # For every registered device found → record an ESP signal
            in_window = _in_attendance_window()
            for mac in matched:
                reg = registered[mac]
                sid = reg.get('student_id')
                if sid and in_window:
                    _record_esp_signal(sid)

        except Exception as e:
            print(f"[BLE] Scan error: {e}")
        await asyncio.sleep(2)

def _ble_thread_fn():
    asyncio.run(_ble_loop())




# ─────────────────────────────────────────────
#  FLASK API ROUTES
# ─────────────────────────────────────────────

# ── Dashboard ──
@app.route('/')
def serve_dashboard():
    res = send_file('index.html')
    res.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    res.headers['Pragma'] = 'no-cache'
    res.headers['Expires'] = '0'
    return res

# ── Status ──
@app.route('/status')
def api_status():
    now = datetime.now()
    in_win = _in_attendance_window()
    return jsonify({
        'ok': True,
        'time': now.isoformat(),
        'attendance_window': in_win,
        'window_start': f"{ATT_START_H:02d}:{ATT_START_M:02d}",
        'window_end':   f"{ATT_END_H:02d}:{ATT_END_M:02d}"
    })

# ── Video Feed ──
@app.route('/video_feed')
def api_video():
    return Response(_gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

# ── Recognition ──
@app.route('/recognition/start', methods=['POST'])
def api_rec_start():
    global _rec_active, _rec_result
    _load_faces()
    _rec_active, _rec_result = True, {'face_detected': False}
    return jsonify({'ok': True, 'in_window': _in_attendance_window()})

@app.route('/recognition/stop', methods=['POST'])
def api_rec_stop():
    global _rec_active, _rec_result
    _rec_active = False
    with _rec_lock:
        _rec_result = {'face_detected': False}
    return jsonify({'ok': True})

@app.route('/recognition/result')
def api_rec_result():
    with _rec_lock:
        res = jsonify(dict(_rec_result))
    res.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return res

@app.route('/snapshot')
def api_snapshot():
    frame = _read_frame()
    if frame is None:
        return jsonify({'error': 'Camera not available'}), 503
    annotated, _ = detect_face(frame)
    _, buf = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return Response(buf.tobytes(), mimetype='image/jpeg')

@app.route('/camera/release', methods=['POST'])
def api_cam_release():
    global _camera
    with _cam_lock:
        if _camera is not None:
            _camera.release()
            _camera = None
    return jsonify({'ok': True})

@app.route('/db/reload', methods=['POST'])
def api_db_reload():
    _load_faces()
    return jsonify({'ok': True})

@app.route('/faces/<filename>')
def serve_face(filename):
    return send_from_directory(FACES_DIR, filename)

# ── Enrollment ──
@app.route('/enroll/capture_face', methods=['POST'])
def api_capture_face():
    global _temp_face_enc, _temp_face_img
    frame = _read_frame()
    if frame is None:
        return jsonify({'success': False, 'message': 'Camera not available.'})
    _, crop = detect_face(frame)
    if crop is None:
        return jsonify({'success': False, 'message': 'No face detected.'})
    enc = _encode(crop)
    if enc is None:
        return jsonify({'success': False, 'message': 'Face found but encoding failed.'})
    _temp_face_enc = enc
    _temp_face_img = crop.copy()
    return jsonify({'success': True, 'faces_detected': 1})

@app.route('/enroll/save', methods=['POST'])
def api_enroll_save():
    global _temp_face_enc, _temp_face_img
    d = request.get_json()
    if _temp_face_enc is None:
        return jsonify({'success': False, 'message': 'Capture face first.'})
    try:
        student = supabase.table('students').insert({
            'name':       d['name'],
            'roll_no':    d['roll_no'],
            'class_name': d['class_name'],
            'section':    d.get('section', '')
        }).execute().data[0]
        sid = student['id']

        img_filename = f"{d['roll_no'].replace('/', '_')}.jpg"
        img_path     = os.path.join(FACES_DIR, img_filename)
        if _temp_face_img is not None:
            cv2.imwrite(img_path, _temp_face_img)
            image_url = f"/faces/{img_filename}"
        else:
            image_url = None

        supabase.table('face_encodings').insert({
            'student_id': sid,
            'encoding':   json.dumps(_temp_face_enc.tolist()),
            'image_url':  image_url
        }).execute()

        if d.get('mac_address'):
            supabase.table('ble_devices').insert({
                'student_id':  sid,
                'mac_address': d['mac_address'].upper(),
                'device_name': d.get('device_name', '')
            }).execute()

        _temp_face_enc = None
        _temp_face_img = None
        _load_faces()
        _ble_reload_flag.set()
        return jsonify({'success': True, 'student_id': sid, 'image_url': image_url})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# ── Attendance ──
@app.route('/attendance/mark', methods=['POST'])
def api_att_mark():
    d = request.get_json()
    # Enforce attendance window
    if not _in_attendance_window():
        return jsonify({
            'success': False,
            'message': f'Attendance window closed. Allowed: {ATT_START_H:02d}:{ATT_START_M:02d} – {ATT_END_H:02d}:{ATT_END_M:02d}'
        }), 403
    try:
        today = date.today().isoformat()
        now   = datetime.now().strftime('%H:%M:%S')
        existing = supabase.table('attendance').select('id, total_present_minutes') \
            .eq('student_id', d['student_id']).eq('date', today).execute().data

        payload = {
            'face_verified': d['face_verified'],
            'ble_verified':  d['ble_verified'],
            'status':        d['status'],
            'time_in':       now,
            'last_seen':     datetime.now().isoformat()
        }
        if existing:
            supabase.table('attendance').update(payload).eq('id', existing[0]['id']).execute()
        else:
            supabase.table('attendance').insert({
                'student_id': d['student_id'],
                'date': today,
                'total_present_minutes': 0,
                **payload
            }).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/attendance/list')
def api_att_list():
    """Returns attendance records sorted by date DESC, then by name ASC."""
    try:
        q = supabase.table('attendance').select('*, students(name, roll_no, class_name)')
        if request.args.get('date'):
            q = q.eq('date', request.args['date'])
        if request.args.get('status'):
            q = q.eq('status', request.args['status'])
        # Sort by date DESC first, then name ASC via Python sort
        rows = q.order('date', desc=True).order('created_at', desc=True).execute().data

        # Sort by date DESC then student name ASC
        rows.sort(key=lambda r: (r['date'], r['students']['name'] if r.get('students') else ''),
                  reverse=False)
        rows.sort(key=lambda r: r['date'], reverse=True)

        records = []
        for r in rows:
            stu = r.get('students') or {}
            records.append({
                'id':                    r['id'],
                'name':                  stu.get('name', '—'),
                'roll_no':               stu.get('roll_no', '—'),
                'class_name':            stu.get('class_name', '—'),
                'date':                  r['date'],
                'time_in':               r.get('time_in'),
                'last_seen':             r.get('last_seen'),
                'face_verified':         r['face_verified'],
                'ble_verified':          r['ble_verified'],
                'status':                r['status'],
                'total_present_minutes': r.get('total_present_minutes', 0)
            })
        return jsonify({'records': records})
    except Exception as e:
        return jsonify({'records': [], 'error': str(e)})

@app.route('/attendance/presence/<student_id>')
def api_presence(student_id):
    """Returns the presence_log for a student for today (bar chart data)."""
    try:
        today = request.args.get('date', date.today().isoformat())
        rows  = supabase.table('presence_log') \
            .select('window_ts, esp_signals') \
            .eq('student_id', student_id) \
            .eq('log_date', today) \
            .order('window_ts') \
            .execute().data
        return jsonify({'log': rows, 'date': today})
    except Exception as e:
        return jsonify({'log': [], 'error': str(e)})

@app.route('/attendance/eod', methods=['POST'])
def api_eod():
    """Manually trigger end-of-day consolidation for today."""
    today = date.today().isoformat()
    _run_eod_consolidation(today)
    return jsonify({'ok': True, 'date': today})

# ── BLE ──
@app.route('/ble/scan/start', methods=['POST'])
def api_ble_start():
    global _ble_active
    if not _ble_active:
        _ble_active = True
        threading.Thread(target=_ble_thread_fn, daemon=True).start()
    return jsonify({'ok': True})

@app.route('/ble/scan/stop', methods=['POST'])
def api_ble_stop():
    global _ble_active
    _ble_active = False
    return jsonify({'ok': True})

@app.route('/ble/devices')
def api_ble_devices():
    with _ble_lock:
        return jsonify({'devices': list(_ble_map.values())})

@app.route('/ble/reload', methods=['POST'])
def api_ble_reload():
    _ble_reload_flag.set()
    return jsonify({'ok': True})

@app.route('/ble/check_student/<student_id>')
def api_ble_check(student_id):
    try:
        row = supabase.table('ble_devices').select('*') \
            .eq('student_id', student_id).eq('is_active', True).execute().data
        if not row:
            return jsonify({'device_registered': False, 'device_found': False, 'in_range': False})
        mac = row[0]['mac_address'].upper()
        with _ble_lock:
            found = _ble_map.get(mac)
        if found:
            return jsonify({
                'device_registered': True,
                'device_found':      True,
                'in_range':          True,
                'rssi':              found['rssi'],
                'device_name':       row[0]['device_name']
            })
        return jsonify({
            'device_registered': True,
            'device_found':      False,
            'in_range':          False,
            'device_name':       row[0]['device_name']
        })
    except Exception as e:
        return jsonify({'device_found': False, 'in_range': False, 'error': str(e)})

# ── ESP Signal State (for live bar chart) ──
@app.route('/esp/state')
def api_esp_state():
    """Returns current ESP signal state per student (for live UI bars)."""
    with _esp_lock:
        out = {}
        for sid, state in _esp_state.items():
            if state:
                out[sid] = {
                    'window_start':  state['window_start'].isoformat(),
                    'signal_count':  state['signal_count'],
                    'last_signal':   state['last_signal'].isoformat(),
                    'window_elapsed': (datetime.now() - state['window_start']).total_seconds()
                }
    return jsonify({'esp_state': out})

# ── Students List ──
@app.route('/students/list')
def api_students():
    try:
        rows = supabase.table('students').select(
            '*, ble_devices(mac_address, device_name)'
        ).order('name').execute().data
        return jsonify({'students': [{
            'id':         r['id'],
            'name':       r['name'],
            'roll_no':    r['roll_no'],
            'class_name': r['class_name'],
            'section':    r.get('section', ''),
            'mac_address':r['ble_devices'][0]['mac_address'] if r.get('ble_devices') else None,
            'device_name':r['ble_devices'][0]['device_name'] if r.get('ble_devices') else None
        } for r in rows]})
    except Exception as e:
        return jsonify({'students': [], 'error': str(e)})




# ─────────────────────────────────────────────
#  START
# ─────────────────────────────────────────────
if __name__ == '__main__':
    print("=" * 60)
    print("  NEXUS Smart Attendance System - Backend v2")
    print(f"  API  -> http://127.0.0.1:5000")
    print(f"  Attendance Window: {ATT_START_H:02d}:{ATT_START_M:02d} – {ATT_END_H:02d}:{ATT_END_M:02d}")
    print(f"  ESP TimeLapse: {TIMELAPSE_SECONDS}s windows")
    print("=" * 60)

    threading.Thread(target=_recognition_thread, daemon=True).start()
    print("[OK] Recognition thread started")

    _ble_active = True
    threading.Thread(target=_ble_thread_fn, daemon=True).start()
    print("[OK] BLE scanner started")

    threading.Thread(target=_camera_cleanup_loop, daemon=True).start()
    print("[OK] Camera idle release monitor started")

    threading.Thread(target=_esp_timelapse_watchdog, daemon=True).start()
    print("[OK] ESP TimeLapse watchdog started")

    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)

