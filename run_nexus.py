import threading
from app import create_app
from app.shared import state
from app.config import logger
from app.background import camera_cleanup_loop, recognition_thread, esp_timelapse_watchdog, ble_thread_fn

# ── INITIALIZE APP ──
app = create_app()

if __name__ == "__main__":
    logger.info("🚀 Starting NEXUS Smart Attendance System (Modular Edition)")

    # 1. Start Camera Cleanup Loop
    threading.Thread(target=camera_cleanup_loop, daemon=True).start()

    # 2. Start Face Recognition Thread
    threading.Thread(target=recognition_thread, daemon=True).start()

    # 3. Start ESP Watchdog & EOD Consolidation
    threading.Thread(target=esp_timelapse_watchdog, daemon=True).start()

    # 4. Start BLE Scanner Thread
    state.ble_active = True
    threading.Thread(target=ble_thread_fn, daemon=True).start()

    # 5. Run Flask
    logger.info("🌐 Web Dashboard available at http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
