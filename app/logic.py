import cv2, json, time, os, numpy as np
import mediapipe as mp
import face_recognition
from datetime import datetime, date, timedelta
from .config import logger, FACES_DIR, FACE_THRESHOLD, ATT_START_H, ATT_START_M, ATT_END_H, ATT_END_M, BREAKS
from .shared import state
from .database import supabase

_mp_det = mp.solutions.face_detection
face_detector = _mp_det.FaceDetection(model_selection=1, min_detection_confidence=0.60)

def in_attendance_window():
    now = datetime.now()
    start = now.replace(hour=ATT_START_H, minute=ATT_START_M, second=0, microsecond=0)
    end   = now.replace(hour=ATT_END_H,   minute=ATT_END_M,   second=0, microsecond=0)
    if not (start <= now <= end): return False
    for (bh1, bm1, bh2, bm2) in BREAKS:
        b_start = now.replace(hour=bh1, minute=bm1, second=0, microsecond=0)
        b_end   = now.replace(hour=bh2, minute=bm2, second=0, microsecond=0)
        if b_start <= now < b_end: return False
    return True

def recently_ended_break():
    now = datetime.now()
    for (bh1, bm1, bh2, bm2) in BREAKS:
        b_end = now.replace(hour=bh2, minute=bm2, second=0, microsecond=0)
        if 0 <= (now - b_end).total_seconds() < 60: return True
    return False

def detect_face(frame):
    h, w  = frame.shape[:2]
    rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    res   = face_detector.process(rgb)
    drawn = frame.copy()
    crop  = None
    if res.detections:
        det  = res.detections[0]
        bb   = det.location_data.relative_bounding_box
        x1, y1 = max(0, int(bb.xmin * w)), max(0, int(bb.ymin * h))
        x2, y2 = min(w, int((bb.xmin + bb.width)*w)), min(h, int((bb.ymin + bb.height)*h))
        cv2.rectangle(drawn, (x1, y1), (x2, y2), (0, 255, 100), 2)
        crop = frame[max(0,y1-20):min(h,y2+20), max(0,x1-20):min(w,x2+20)]
    return drawn, crop

def encode_face(face_bgr):
    rgb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
    encs = face_recognition.face_encodings(rgb)
    return encs[0] if encs else None

def match_face(enc):
    if not state.known_encodings: return None, 0.0
    dists = face_recognition.face_distance(state.known_encodings, enc)
    idx = int(np.argmin(dists))
    dist = dists[idx]
    if dist < FACE_THRESHOLD:
        return state.known_students[idx], round((1 - dist) * 100, 1)
    return None, 0.0

_last_load_time = 0
CACHE_TTL = 300 # 5 minutes

def load_faces():
    global _last_load_time
    # Use cached encodings if less than 5 mins old
    if time.time() - _last_load_time < CACHE_TTL and state.known_encodings:
        return

    try:
        rows = supabase.table('face_encodings').select('*, students(id, name, roll_no, class_name)').execute().data
        state.known_encodings.clear()
        state.known_students.clear()
        if rows:
            for r in rows:
                state.known_encodings.append(np.array(json.loads(r['encoding'])))
                state.known_students.append(r['students'])
        _last_load_time = time.time()
        logger.info(f"[FRS] {len(state.known_encodings)} face(s) loaded (Refreshed Cache)")
    except Exception as e:
        logger.error(f"[FRS] Load error: {e}")

