#include <Arduino.h>
#include <BLEDevice.h>
#include <WiFi.h>

// ── CONFIG ───────────────────────────────────
#define DEVICE_NAME   "004904"        // Student identifier
#define WIFI_SSID     "Tarun"         // Authorized college WiFi
#define WIFI_PASS     "YourWiFiPassword" // Replace with actual password
#define BACKEND_IP    "192.168.1.100" // PC IP for future commands

// Sleep duration (60 seconds)
#define uS_TO_S_FACTOR 1000000ULL  
#define TIME_TO_SLEEP  60          

BLEAdvertising *adv;

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n--- NEXUS Tracker Pro ---");

  // 1. WiFi SSID Verification (Security)
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting to Authorized WiFi (");
  Serial.print(WIFI_SSID);
  Serial.print(")");

  int retry = 0;
  while (WiFi.status() != WL_CONNECTED && retry < 10) {
    delay(500);
    Serial.print(".");
    retry++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[SECURE] College WiFi Verified. Starting BLE...");
  } else {
    Serial.println("\n[ERROR] College WiFi not found. Restricted mode.");
  }

  // 2. Initialize BLE
  BLEDevice::init(DEVICE_NAME);
  adv = BLEDevice::getAdvertising();

  BLEAdvertisementData data;
  data.setFlags(0x04);
  data.setName(DEVICE_NAME);
  data.setManufacturerData("ATTN");

  adv->setAdvertisementData(data);
  adv->setScanResponse(true);

  BLEDevice::startAdvertising();
  Serial.println("[OK] BLE Broadcasting Student ID: " DEVICE_NAME);

  // 3. Deep Sleep (Low Power)
  Serial.println("Broadcasting for 10s before Deep Sleep...");
  delay(10000); 

  Serial.println("Entering Deep Sleep for 60s...");
  esp_sleep_enable_timer_wakeup(TIME_TO_SLEEP * uS_TO_S_FACTOR);
  esp_deep_sleep_start();
}

void loop() {
  // Never reached due to Deep Sleep
}