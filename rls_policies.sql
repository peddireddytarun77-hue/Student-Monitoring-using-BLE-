-- NEXUS Smart Attendance: Proposed RLS Policies
-- Execute these in your Supabase SQL Editor

-- 1. Enable RLS on all tables
ALTER TABLE students ENABLE ROW LEVEL SECURITY;
ALTER TABLE attendance ENABLE ROW LEVEL SECURITY;
ALTER TABLE presence_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE ble_devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE face_encodings ENABLE ROW LEVEL SECURITY;

-- 2. Define "service_role" or "admin" access (Backend access)
-- Note: The backend currently uses the 'anon' key with full access.
-- For production, you should use the 'service_role' key or specific policies.

-- Example: Allow public read-only access to basic student info
CREATE POLICY "Public students are viewable by everyone" ON students
  FOR SELECT USING (true);

-- Example: Allow students to view only their own attendance (requires Auth)
-- CREATE POLICY "Individuals can view their own data" ON attendance
--   FOR SELECT USING (auth.uid() = student_id);

-- 3. Restrict sensitive data (Face Encodings)
-- Only allow the service role (backend) to view/edit encodings
CREATE POLICY "Service role only access" ON face_encodings
  USING (false)
  WITH CHECK (false);
-- (This effectively blocks anon access. Backend must use service_role key)
