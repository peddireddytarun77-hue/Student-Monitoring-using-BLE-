# 📡 BLE Setup & Student Registration Guide

Now that you have the [esp32_tracker_firmware.ino](file:///d:/PROJECT%201%20DEAD%20END/esp32_tracker_firmware.ino) file, follow these steps to get everything working.

## 1. Set Your PC's IP in the Firmware (REQUIRED before flashing!)
1. On your PC, open Command Prompt and run: `ipconfig`
2. Find your **IPv4 Address** under your Wi-Fi adapter (e.g., `192.168.1.5`).
3. Open `esp32_tracker_firmware.ino` in a text editor.
4. Find line: `#define BACKEND_IP    "192.168.1.100"`
5. **Replace `192.168.1.100` with your actual PC IP** (e.g., `"192.168.1.5"`).

> [!IMPORTANT]
> Both your PC and ESP32 must be on the **same Wi-Fi network** (`Tarun`).

## 2. Flash the ESP32
1. Open the [Arduino IDE](https://www.arduino.cc/en/software).
2. Install the **ESP32 Board Support** (Go to Settings -> Boards Manager -> Search "ESP32").
3. Connect your ESP32 to your PC.
4. Open the `esp32_tracker_firmware.ino` file in Arduino IDE.
5. Select your board (e.g., "DOIT ESP32 DEVKIT V1") and the correct COM port.
6. Click **Upload** (the arrow button).

## 2. Get the MAC Address
1. Once uploaded, open the **Serial Monitor** in Arduino IDE (Magnifying glass icon in top right).
2. Set the baud rate to **115200**.
3. Press the **EN/RESET** button on your ESP32.
4. Look for a line like this:
   `MAC Address: AB:CD:EF:12:34:56`
5. **Copy this MAC Address.**

## 3. Register the Student
1. Open your Smart Attendance Dashboard ([http://127.0.0.1:5000/](http://127.0.0.1:5000/)).
2. Go to the **"Enroll Student"** tab.
3. Fill in the student details.
4. In the **"BLE Device MAC Address"** field, paste the address you copied (e.g., `AB:CD:EF:12:34:56`).
5. Complete the face capture and click **Enroll Student**.

## 4. Test Verification
1. Go to the **"BLE Device Monitor"** tab.
2. Click **"📡 Start BLE Scan"**.
3. You should see your ESP32 appear in the list with its name and signal strength (RSSI).
4. Now, go to **"Mark Attendance"** and try to verify. The system will now check BOTH the face AND the BLE signal!

> [!IMPORTANT]
> Make sure your PC's Bluetooth is turned **ON** before clicking "Start BLE Scan".
