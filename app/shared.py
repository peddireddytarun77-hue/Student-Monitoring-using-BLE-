import threading

class GlobalState:
    def __init__(self):
        self.cam_lock = threading.Lock()
        self.rec_lock = threading.Lock()
        self.ble_lock = threading.Lock()
        self.esp_lock = threading.Lock()
        
        self.camera = None
        self.rec_active = False
        self.rec_result = {}
        self.temp_face_enc = None
        self.temp_face_img = None
        self.known_encodings = []
        self.known_students = []
        self.ble_map = {}
        self.ble_active = False
        self.ble_reload_flag = threading.Event()
        self.last_frame_time = 0
        self.esp_state = {}

state = GlobalState()
