# NEXUS — Smart Attendance & Student Monitoring System

NEXUS is an all-in-one student monitoring solution that combines **Face Recognition** with **BLE (Bluetooth Low Energy) Tracker Verification** to provide a secure and automated attendance system.

## 🚀 Key Features

-   **📸 Face Recognition**: Uses MediaPipe and `face_recognition` (dlib) for high-accuracy identification.
-   **📡 BLE Verification**: Ensures the student is physically present by detecting their assigned ESP32 tracker.
-   **🗺️ Live 2D Map**: Real-time spatial visualization of student locations based on signal strength (RSSI).
-   **🔋 Low Power (Pro)**: ESP32 trackers utilize Deep Sleep and WiFi SSID verification for security and battery efficiency.
-   **📊 Dashboard**: Comprehensive web interface for monitoring, enrollment, and attendance records.

## 🛠️ Components

### 1. Backend (Python/Flask)
The core engine that handles:
-   Face detection and recognition.
-   BLE scanning via `bleak`.
-   Database management through **Supabase**.
-   Attendance logic (time-lapse windows, end-of-day consolidation).

### 2. Frontend (HTML5/Vanilla CSS/JS)
A premium, dark-themed dashboard with:
-   Live video feed.
-   Real-time BLE signal radar.
-   Interactive 2D Map.
-   Enrollment and Attendance history tabs.

### 3. Firmware (ESP32)
Low-power beacon firmware that:
-   Verifies college WiFi before broadcasting.
-   Uses Deep Sleep to last for weeks on battery.

## 📦 Installation & Setup

### Prerequisites
-   Python 3.8+
-   Arduino IDE (for ESP32)
-   Supabase Account

### Setup Backend
1.  Clone the repository.
2.  Install dependencies: `pip install -r requirements.txt`
3.  Configure `.env` with your Supabase credentials.
4.  Run the system: `python backend.py`

### Setup ESP32
1.  Open `esp32_tracker_firmware/esp32_tracker_firmware.ino`.
2.  Set your PC's IP and WiFi credentials.
3.  Flash to your ESP32 device.

## 🛡️ Security
NEXUS project was designed with security in mind, originally featuring a Quantum-resistant cryptographic simulation layer (Kyber/Dilithium) to protect student data against future threats.

---

**Developed for Student Monitoring using BLE & Face Recognition.**
