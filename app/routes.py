import cv2, json, time, threading, os
from flask import Blueprint, Response, jsonify, request, send_file, send_from_directory, make_response
from functools import wraps
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from datetime import date, datetime, timedelta
from .config import logger, FACES_DIR, ATT_START_H, ATT_START_M, ATT_END_H, ATT_END_M, q_shield
from .shared import state
from .database import supabase
from .logic import detect_face, encode_face, in_attendance_window, load_faces
from .background import read_frame

api_bp = Blueprint('api', __name__)

# ── AUTH & SECURITY ──────────────────────────
DASHBOARD_PASS = os.environ.get("DASHBOARD_PASSWORD", "NexusAdmin123")

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get('auth_token')
        if token != DASHBOARD_PASS:
            return jsonify({'ok': False, 'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

from . import limiter

@api_bp.route('/login', methods=['POST'])
@limiter.limit("10 per minute")
def api_login():
    data = request.json
    if not data or not data.get('password'):
        return jsonify({'ok': False, 'error': 'Password required'}), 400
    if data.get('password') == DASHBOARD_PASS:
        res = make_response(jsonify({'ok': True}))
        res.set_cookie('auth_token', DASHBOARD_PASS, httponly=True, samesite='Lax')
        return res
    return jsonify({'ok': False, 'error': 'Invalid password'}), 401

@api_bp.route('/logout', methods=['POST'])
def api_logout():
    res = make_response(jsonify({'ok': True}))
    res.delete_cookie('auth_token')
    return res

@api_bp.route('/')
def serve_dashboard():
    # If not authed, the frontend should handle showing a login modal
    # For now, we just serve the file
    res = send_file('index.html')
    res.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return res

@api_bp.route('/status')
def api_status():
    return jsonify({'ok': True, 'time': datetime.now().isoformat(), 'attendance_window': in_attendance_window(), 'window_start': f"{ATT_START_H:02d}:{ATT_START_M:02d}", 'window_end': f"{ATT_END_H:02d}:{ATT_END_M:02d}"})

@api_bp.route('/quantum/status')
def api_quantum_status(): return jsonify(q_shield.get_status())

@api_bp.route('/quantum/audit')
def api_quantum_audit():
    limit = int(request.args.get('limit', 20))
    return jsonify({"audit_log": q_shield.get_audit()[:limit]})

@api_bp.route('/quantum/keygen', methods=['POST'])
def api_quantum_keygen():
    pub = q_shield.rotate_keys(); status = q_shield.get_status()
    return jsonify({"ok": True, "public_key": pub, "algorithm": status['kem_algorithm'], "keygen_ms": status['keygen_ms']})

@api_bp.route('/recognition/start', methods=['POST'])
def api_rec_start():
    load_faces(); state.rec_active = True
    with state.rec_lock: state.rec_result = {'face_detected': False}
    return jsonify({'ok': True})

@api_bp.route('/recognition/stop', methods=['POST'])
def api_rec_stop():
    state.rec_active = False
    with state.rec_lock: state.rec_result = {'face_detected': False}
    return jsonify({'ok': True})

@api_bp.route('/recognition/result')
def api_rec_result():
    with state.rec_lock: res = jsonify(dict(state.rec_result))
    res.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'; return res

@api_bp.route('/attendance/list')
def api_att_list():
    try:
        rows = supabase.table('attendance').select('*, students(name, roll_no, class_name)').order('date', desc=True).execute().data
        records = []
        for r in rows:
            stu = r.get('students') or {}
            records.append({'id': r['id'], 'name': stu.get('name','-'), 'roll_no': stu.get('roll_no','-'), 'class_name': stu.get('class_name','-'), 'date': r['date'], 'status': r['status'], 'total_present_minutes': r.get('total_present_minutes', 0)})
        return jsonify({'records': records})
    except Exception as e: return jsonify({'records': [], 'error': str(e)})

@api_bp.route('/video_feed')
def api_video():
    def gen():
        while True:
            frame = read_frame()
            if frame is None: time.sleep(0.05); continue
            ann, _ = detect_face(frame)
            _, buf = cv2.imencode('.jpg', ann, [cv2.IMWRITE_JPEG_QUALITY, 80])
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buf.tobytes() + b'\r\n')
            time.sleep(0.04)
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@api_bp.route('/student/enroll/capture', methods=['POST'])
def api_enroll_capture():
    frame = read_frame()
    if frame is None: return jsonify({'ok': False, 'error': 'Camera fail'})
    ann, crop = detect_face(frame)
    if crop is None: return jsonify({'ok': False, 'error': 'No face'})
    enc = encode_face(crop)
    if enc is None: return jsonify({'ok': False, 'error': 'Bad encoding'})
    state.temp_face_enc = enc.tolist()
    _, buf = cv2.imencode('.jpg', crop)
    state.temp_face_img = buf.tobytes()
    return jsonify({'ok': True})

@api_bp.route('/student/enroll/save', methods=['POST'])
@require_auth
def api_enroll_save():
    if not state.temp_face_enc: return jsonify({'ok': False, 'error': 'No face captured'})
    data = request.json
    name = str(data.get('name', '')).strip()
    roll = str(data.get('roll_no', '')).strip()
    
    # ── INPUT VALIDATION ──
    if len(name) < 2 or not name.replace(' ', '').isalpha():
        return jsonify({'ok': False, 'error': 'Invalid Name format'}), 400
    if not roll.isalnum() or len(roll) < 3:
        return jsonify({'ok': False, 'error': 'Invalid Roll No format'}), 400

    try:
        # Check if exists
        existing = supabase.table('students').select('id').eq('roll_no', roll).execute().data
        if existing: return jsonify({'ok': False, 'error': 'Roll number already exists'}), 409

        stu = supabase.table('students').insert({'name': name, 'roll_no': roll, 'class_name': data.get('class', 'General')}).execute().data[0]
        # ... rest same
        supabase.table('face_encodings').insert({'student_id': stu['id'], 'encoding': json.dumps(state.temp_face_enc)}).execute()
        f_path = os.path.join(FACES_DIR, f"{stu['id']}.jpg")
        with open(f_path, 'wb') as f: f.write(state.temp_face_img)
        load_faces(); state.temp_face_enc = None; state.temp_face_img = None
        return jsonify({'ok': True})
    except Exception as e: return jsonify({'ok': False, 'error': str(e)})

@api_bp.route('/attendance/mark', methods=['POST'])
def api_mark():
    data = request.json; sid = data['student_id']; today = date.today().isoformat()
    try:
        existing = supabase.table('attendance').select('id').eq('student_id', sid).eq('date', today).execute().data
        if not existing:
            supabase.table('attendance').insert({'student_id': sid, 'date': today, 'status': 'present', 'face_verified': True, 'last_seen': datetime.now().isoformat()}).execute()
        else:
            supabase.table('attendance').update({'status': 'present', 'face_verified': True, 'last_seen': datetime.now().isoformat()}).eq('id', existing[0]['id']).execute()
        q_shield.log_event("ATTENDANCE_MARK", {"student_id": sid, "method": "face_recognition", "timestamp": datetime.now().isoformat()})
        return jsonify({'ok': True})
    except Exception as e: return jsonify({'ok': False, 'error': str(e)})

@api_bp.route('/ble/devices')
def api_ble_devices():
    with state.ble_lock: return jsonify({'devices': list(state.ble_map.values())})

@api_bp.route('/ble/reload', methods=['POST'])
def api_ble_reload():
    state.ble_reload_flag.set(); return jsonify({'ok': True})

@api_bp.route('/faces/<sid>')
def serve_face(sid):
    return send_from_directory(FACES_DIR, f"{sid}.jpg")

# ── GDPR & COMPLIANCE ──
@api_bp.route('/student/delete/<sid>', methods=['DELETE'])
@require_auth
def api_student_delete(sid):
    try:
        supabase.table('students').delete().eq('id', sid).execute()
        # Clean up image
        f_path = os.path.join(FACES_DIR, f"{sid}.jpg")
        if os.path.exists(f_path): os.remove(f_path)
        load_faces()
        return jsonify({'ok': True})
    except Exception as e: return jsonify({'ok': False, 'error': str(e)})

@api_bp.route('/logs/purge', methods=['POST'])
@require_auth
def api_logs_purge():
    try:
        # Purge older than 30 days
        expiry = (datetime.now() - timedelta(days=30)).isoformat()
        supabase.table('presence_log').delete().lt('log_date', expiry).execute()
        return jsonify({'ok': True, 'msg': 'Logs older than 30 days purged'})
    except Exception as e: return jsonify({'ok': False, 'error': str(e)})
