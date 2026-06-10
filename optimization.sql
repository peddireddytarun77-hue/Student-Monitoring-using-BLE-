-- NEXUS Smart Attendance: Database Optimizations
-- Run these in your Supabase SQL Editor for faster queries

-- 1. Index for attendance lookups (used by almost all routes)
CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance(date);
CREATE INDEX IF NOT EXISTS idx_attendance_student_id ON attendance(student_id);

-- 2. Index for BLE presence lookups
CREATE INDEX IF NOT EXISTS idx_presence_log_date ON presence_log(log_date);
CREATE INDEX IF NOT EXISTS idx_presence_log_ts ON presence_log(window_ts);

-- 3. Index for student roll numbers (Unique lookups)
CREATE INDEX IF NOT EXISTS idx_students_roll_no ON students(roll_no);

-- 4. Composite index for faster daily presence tracking
CREATE INDEX IF NOT EXISTS idx_presence_student_date ON presence_log(student_id, log_date);
