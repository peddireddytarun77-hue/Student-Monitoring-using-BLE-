# Proposed GitHub Issues for NEXUS Project

To organize your project like a professional developer, you can create these two issues on GitHub. Copy and paste the titles and descriptions below.

---

## Issue 1: Optimization of Face Recognition Logic
**Title**: [Optimization] Implement Multi-threaded Face Encoding
**Description**:
Currently, face recognition is performed in a serial loop within the background thread. For faster detection and to handle multiple faces simultaneously in the future, we should:
- Move face encoding to a dedicated process pool.
- Implement a frame-skipping mechanism to reduce CPU load when no faces are detected.
- Optimize the `face_distance` matching threshold based on environmental lighting.

---

## Issue 2: Enhanced 2D Map Accuracy
**Title**: [Feature] Multi-Beacon Trilateration for 2D Map
**Description**:
The current 2D Map uses a single scanner (the PC) to estimate student proximity. To achieve true 2D positioning (X, Y coordinates), we should:
- Support multiple ESP32 "Static Scanners" placed at different corners of the room.
- Implement a trilateration algorithm in `backend.py` using RSSI values from at least 3 scanners.
- Add an "upload floorplan" feature to the dashboard for custom room layouts.

---

---

## Issue 3: Network Traffic & Load Management
**Title**: [Stability] Implement Congestion Control for High Network Traffic
**Description**:
The system occasionally experiences heavy load due to high network traffic from frequent BLE scanning and face data synchronization. To optimize performance:
- Implement a debouncing mechanism for BLE signal updates (TimeLapse logic optimization).
- Optimize API polling frequencies when the dashboard is in the background.
- Ensure efficient data serialization for Supabase queries to reduce bandwidth usage.
- Add exponential backoff for ESP32 WiFi reconnection attempts.

---

**Note to Developer**: To create these issues, go to the **Issues** tab on GitHub, click **New Issue**, and paste the content above.

