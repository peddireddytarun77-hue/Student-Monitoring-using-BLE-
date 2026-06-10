import cv2, time, asyncio, threading
from flask import Response
from datetime import datetime, date, timedelta
from .config import logger, TIMELAPSE_SECONDS, BLE_SCAN_TIMEOUT
from .shared import state
from .database import supabase
from .logic import detect_face, encode_face, match_face, load_faces, in_attendance_window, recently_ended_break

def get_camera():
    if state.camera is None or not state.camera.isOpened():
        state.camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        state.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        state.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    return state.camera

def read_frame():
    state.last_frame_time = time.time()
    with state.cam_lock:
        cam = get_camera()
        ok, frame = cam.read()
    return frame if ok else None

def camera_cleanup_loop():
    while True:
        if state.camera is not None and (time.time() - state.last_frame_time > 5):
            if not state.rec_active:
                with state.cam_lock:
                    if state.camera is not None:
                        logger.info("[CAM] Idle timeout -> Releasing hardware")
                        state.camera.release()
                        state.camera = None
        time.sleep(2)

def recognition_thread():
    load_faces()
    while True:
        if not state.rec_active:
            time.sleep(0.1); continue
        frame = read_frame()
        if frame is None:
            time.sleep(0.1); continue
        _, crop = detect_face(frame)
        if crop is None:
            with state.rec_lock: state.rec_result = {'face_detected': False}
            time.sleep(0.1); continue
        enc = encode_face(crop)
        if enc is None:
            with state.rec_lock: state.rec_result = {'face_detected': True, 'face_identified': False}
            time.sleep(0.1); continue
        student, conf = match_face(enc)
        with state.rec_lock:
            if student:
                state.rec_result = {'face_detected':True, 'face_identified':True, 'student_id':student['id'], 'student_name':student['name'], 'roll_no':student['roll_no'], 'class':student['class_name'], 'confidence':conf}
            else:
                state.rec_result = {'face_detected': True, 'face_identified': False}
        time.sleep(0.3)

def record_esp_signal(student_id):
    now = datetime.now()
    with state.esp_lock:
        s = state.esp_state.get(student_id)
        if s is None or (now - s['window_start']).total_seconds() >= TIMELAPSE_SECONDS:
            if s is not None and s['signal_count'] >= 1:
                flush_presence_window(student_id, s['window_start'], s['signal_count'])
            state.esp_state[student_id] = {'window_start': now, 'signal_count': 1, 'last_signal': now}
        else:
            state.esp_state[student_id]['signal_count'] += 1
            state.esp_state[student_id]['last_signal'] = now

def flush_presence_window(student_id, window_start, signal_count):
    today = date.today().isoformat()
    try:
        supabase.table('presence_log').upsert({'student_id': student_id, 'log_date': today, 'window_ts': window_start.isoformat(), 'esp_signals': signal_count}, on_conflict='student_id,window_ts').execute()
        existing = supabase.table('attendance').select('id, total_present_minutes').eq('student_id', student_id).eq('date', today).execute().data
        if existing:
            att = existing[0]
            new_mins = (att.get('total_present_minutes') or 0) + 1
            supabase.table('attendance').update({'total_present_minutes': new_mins, 'last_seen': datetime.now().isoformat()}).eq('id', att['id']).execute()
            logger.info(f"[ESP] Flushed window for {student_id}: +1 min")
    except Exception as e:
        logger.error(f"[ESP] Flush error for {student_id}: {e}")

def esp_timelapse_watchdog():
    _eod_done = {'done': False, 'last_date': None}
    while True:
        now = datetime.now(); today = date.today().isoformat()
        with state.esp_lock:
            for sid, s in list(state.esp_state.items()):
                if s and (now - s['window_start']).total_seconds() >= TIMELAPSE_SECONDS:
                    flush_presence_window(sid, s['window_start'], s['signal_count'])
                    state.esp_state[sid] = None
            for sid in [k for k, v in state.esp_state.items() if v is None]: del state.esp_state[sid]
        try:
            time_threshold = (now - timedelta(minutes=5)).isoformat()
            missing = supabase.table('attendance').select('*, students(name)').eq('date', today).eq('status', 'present').lt('last_seen', time_threshold).execute().data
            for m in missing:
                logger.warning(f"[ALERT] Student {m['students']['name']} missing > 5m!")
                supabase.table('attendance').update({'status': 'suspicious', 'ble_verified': False}).eq('id', m['id']).execute()
        except: pass
        if recently_ended_break():
            try:
                present_students = supabase.table('attendance').select('id').eq('date', today).eq('face_verified', True).execute().data
                for s in present_students:
                    supabase.table('attendance').update({'face_verified': False, 'status': 'suspicious'}).eq('id', s['id']).execute()
            except: pass
        time.sleep(30)

async def ble_loop():
    from bleak import BleakScanner
    registered = {}; _last_reg_reload = 0
    def _reload():
        nonlocal registered, _last_reg_reload
        try:
            rows = supabase.table('ble_devices').select('mac_address, device_name, student_id, students(name)').eq('is_active', True).execute().data
            registered = {r['mac_address'].upper(): r for r in rows}
            _last_reg_reload = time.time()
            logger.info(f"[BLE] {len(registered)} devices loaded")
        except: pass
    _reload()
    while state.ble_active:
        if state.ble_reload_flag.is_set() or time.time() - _last_reg_reload > 60:
            _reload(); state.ble_reload_flag.clear()
        try:
            found = await BleakScanner.discover(timeout=BLE_SCAN_TIMEOUT, return_adv=True)
            new_map = {}; matched = []
            for mac_raw, (device, adv) in found.items():
                mac = mac_raw.upper(); rssi = adv.rssi if hasattr(adv, 'rssi') else -99
                reg = registered.get(mac)
                entry = {'mac':mac, 'name':device.name or 'Unknown', 'rssi':rssi, 'registered':False}
                if reg:
                    entry.update({'registered':True, 'device_name':reg['device_name'], 'student_id':reg['student_id'], 'student_name':reg['students']['name'] if reg.get('students') else None})
                    matched.append(mac)
                    if in_attendance_window(): record_esp_signal(reg['student_id'])
                new_map[mac] = entry
            with state.ble_lock: state.ble_map.clear(); state.ble_map.update(new_map)
        except Exception as e: logger.error(f"[BLE] Scan error: {e}")
        await asyncio.sleep(2)

def ble_thread_fn():
    asyncio.run(ble_loop())
