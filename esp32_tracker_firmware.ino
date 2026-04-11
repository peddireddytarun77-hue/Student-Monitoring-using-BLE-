/*
  Smart Attendance System - Student Tracker Node (Wi-Fi + BLE + PIR + QUANTUM)
  Device: ESP32
  
  Logic:
  - Connects to Campus Wi-Fi.
  - Gets real time via NTP.
  - Operates only between 09:00 - 16:50. Pauses tightly during breaks.
  - If PIR detects motion within allowed time, begins broadcasting.
  - **QUANTUM LAYER**: Fetches a dynamically rotating cryptographic token 
    from the Python backend every 60s to prevent replay attacks.
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <time.h>
#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEServer.h>

// ─── HARDWARE PINS ──────────────
#define LED_PIN       2   // Status LED
#define PIR_PIN       14  // HC-SR501 Data OUT

// ─── NETWORK CONFIG ─────────────
// ⚠️ Fill in your own WiFi credentials before flashing!
#define WIFI_SSID     "YOUR_WIFI_NAME"      // <--- CHANGE THIS
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"  // <--- CHANGE THIS

// ⚠️  UPDATE THIS to your PC's local IP where backend.py is running!
// Run `ipconfig` in cmd to find it (e.g. 192.168.1.5)
#define BACKEND_IP    "192.168.1.100"  // <--- CHANGE THIS

#define DEVICE_NAME   "004904"

// NTP Server setup
const char* ntpServer = "pool.ntp.org";
const long  gmtOffset_sec = 19800; // IST is GMT+5:30
const int   daylightOffset_sec = 0;

BLEAdvertising *pAdvertising;
bool isAdvertising = false;
unsigned long lastQuantumFetch = 0;
String currentQuantumToken = "AWAITING_TOKEN";

// ─── PROTOTYPES ──────────────
bool isValidTime();
void startBLE();
void stopBLE();
void fetchQuantumToken();

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  pinMode(PIR_PIN, INPUT);

  Serial.println("\n--- NEXUS Quantum Tracker Node Starting ---");

  // 1. Connect to Wi-Fi
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to Wi-Fi");
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[OK] Wi-Fi Connected!");
    configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);
    Serial.println("[OK] Time syncing with NTP...");
  } else {
    Serial.println("\n[WARN] Wi-Fi failed. NTP and Quantum APIs unreachable.");
  }

  // 2. Setup Base BLE
  BLEDevice::init(DEVICE_NAME);
  pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(BLEUUID((uint16_t)0xFEAA)); 
  pAdvertising->setScanResponse(true);
  pAdvertising->setMinPreferred(0x06);  
  pAdvertising->setMaxPreferred(0x12);
  
  Serial.println("[OK] Setup Complete. Entering monitoring loop.");
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.reconnect();
  }

  // Fetch a new Quantum Security Token from backend every 60 seconds
  if (WiFi.status() == WL_CONNECTED && (millis() - lastQuantumFetch > 60000)) {
    fetchQuantumToken();
    lastQuantumFetch = millis();
  }

  bool timeValid = isValidTime();
  bool motionDetected = digitalRead(PIR_PIN) == HIGH;
  bool isWifiConnected = (WiFi.status() == WL_CONNECTED);

  // Broadast ONLY if working hours, motion detected, AND Wi-Fi signal is unbroken
  if (timeValid && motionDetected && isWifiConnected) {
    if (!isAdvertising) {
      startBLE();
    }
    digitalWrite(LED_PIN, HIGH);
  } else {
    if (isAdvertising) {
      stopBLE();
    }
    digitalWrite(LED_PIN, LOW);
  }

  delay(1000); 
}

// ─── HELPERS ──────────────

bool isValidTime() {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) return false; // Safe fallback: no broadcast if NTP not synced

  int hr = timeinfo.tm_hour;
  int mn = timeinfo.tm_min;
  int totalMins = hr * 60 + mn;

  if (totalMins < 540 || totalMins >= 1010) return false; // Allowed: 09:00 to 16:50
  if (totalMins >= 640 && totalMins < 650) return false;  // Break 1
  if (totalMins >= 750 && totalMins < 800) return false;  // Break 2
  if (totalMins >= 900 && totalMins < 910) return false;  // Break 3

  return true;
}

void fetchQuantumToken() {
  HTTPClient http;
  String mac = BLEDevice::getAddress().toString().c_str();
  mac.replace(":", "");
  
  String url = "http://" + String(BACKEND_IP) + ":5000/quantum/ble_token/" + mac;
  
  http.begin(url);
  int httpCode = http.GET();
  
  if (httpCode == 200) {
    String payload = http.getString();
    // Quick string parsing for token bypassing JSON library limits
    int tokenStart = payload.indexOf("\"token\":\"") + 9;
    if (tokenStart > 8) {
      int tokenEnd = payload.indexOf("\"", tokenStart);
      currentQuantumToken = payload.substring(tokenStart, tokenEnd);
      Serial.println("[QUANTUM] New session token imported: " + currentQuantumToken);
      
      // If currently broadcasting, abruptly restart to apply new token
      if (isAdvertising) {
        stopBLE();
        startBLE(); 
      }
    }
  } else {
    Serial.println("[QUANTUM] API unreachable. Code: " + String(httpCode));
  }
  http.end();
}

void startBLE() {
  // Inject the Quantum Token dynamically into Manufacturer Data payload
  BLEAdvertisementData oAdvertisementData = BLEAdvertisementData();
  oAdvertisementData.setFlags(0x04); // BR_EDR_NOT_SUPPORTED
  
  String mfgData = "";
  mfgData += (char)0xFF; 
  mfgData += (char)0xFF; 
  mfgData += currentQuantumToken;
  
  oAdvertisementData.setManufacturerData(mfgData.c_str());
  oAdvertisementData.setName(DEVICE_NAME);
  pAdvertising->setAdvertisementData(oAdvertisementData);

  BLEDevice::startAdvertising();
  isAdvertising = true;
  Serial.println("[BLE] Broadcasting activated securely.");
}

void stopBLE() {
  pAdvertising->stop();
  isAdvertising = false;
  Serial.println("[BLE] Broadcasting STOPPED.");
}
