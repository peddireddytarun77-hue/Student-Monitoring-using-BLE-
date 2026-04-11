-- =====================================================
-- Smart Attendance System - Supabase Table Setup v2
-- Run this in: Supabase → SQL Editor → Run
-- =====================================================

-- TABLE 1: Students (basic info)
CREATE TABLE IF NOT EXISTS students (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name        TEXT NOT NULL,
    roll_no     TEXT UNIQUE NOT NULL,
    class_name  TEXT NOT NULL,
    section     TEXT DEFAULT '',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- TABLE 2: Face Encodings (128-d vector stored as JSON)
CREATE TABLE IF NOT EXISTS face_encodings (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    student_id  UUID REFERENCES students(id) ON DELETE CASCADE,
    encoding    TEXT NOT NULL,
    image_url   TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- TABLE 3: BLE Devices (ESP32 MAC address per student)
CREATE TABLE IF NOT EXISTS ble_devices (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    student_id  UUID REFERENCES students(id) ON DELETE CASCADE,
    mac_address TEXT UNIQUE NOT NULL,
    device_name TEXT DEFAULT '',
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- TABLE 4: Attendance (one record per student per day)
--   status:     'absent' | 'present' | 'suspicious'
--   time_in:    time of FRS+BLE activation (first check-in 09:00-16:50)
--   last_seen:  last ESP signal timestamp (updated every timelapse window)
--   total_present_minutes: cumulative BLE-confirmed presence in minutes
CREATE TABLE IF NOT EXISTS attendance (
    id                     UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    student_id             UUID REFERENCES students(id) ON DELETE CASCADE,
    date                   DATE NOT NULL DEFAULT CURRENT_DATE,
    time_in                TIME,
    last_seen              TIMESTAMPTZ,
    face_verified          BOOLEAN DEFAULT FALSE,
    ble_verified           BOOLEAN DEFAULT FALSE,
    status                 TEXT DEFAULT 'absent',
    total_present_minutes  INTEGER DEFAULT 0,
    created_at             TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(student_id, date)
);

-- TABLE 5: Presence Log (raw ESP signal events, one row per 1-min timelapse window)
--   Each time the ESP signal is detected → a new row is upserted for that window
CREATE TABLE IF NOT EXISTS presence_log (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    student_id  UUID REFERENCES students(id) ON DELETE CASCADE,
    log_date    DATE NOT NULL DEFAULT CURRENT_DATE,
    window_ts   TIMESTAMPTZ NOT NULL,   -- Start of the 1-min window
    esp_signals INTEGER DEFAULT 1,      -- Number of ESP signals received in this window
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(student_id, window_ts)
);

-- ─── ROW LEVEL SECURITY (allow all for development) ───
ALTER TABLE students       ENABLE ROW LEVEL SECURITY;
ALTER TABLE face_encodings ENABLE ROW LEVEL SECURITY;
ALTER TABLE ble_devices    ENABLE ROW LEVEL SECURITY;
ALTER TABLE attendance     ENABLE ROW LEVEL SECURITY;
ALTER TABLE presence_log   ENABLE ROW LEVEL SECURITY;

CREATE POLICY "allow_all" ON students       FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "allow_all" ON face_encodings FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "allow_all" ON ble_devices    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "allow_all" ON attendance     FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "allow_all" ON presence_log   FOR ALL USING (true) WITH CHECK (true);

-- Done! 5 tables ready.
-- Run ALTER statements below if tables already exist to add new columns:

-- ALTER TABLE attendance ADD COLUMN IF NOT EXISTS last_seen TIMESTAMPTZ;
-- ALTER TABLE attendance ADD COLUMN IF NOT EXISTS total_present_minutes INTEGER DEFAULT 0;
-- CREATE TABLE IF NOT EXISTS presence_log ( ... );  -- see above
