import cv2

print("Testing Camera 0...")
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
if not cap.isOpened():
    print("Failed to open Camera 0 with DSHOW, trying without DSHOW...")
    cap = cv2.VideoCapture(0)

if cap.isOpened():
    ret, frame = cap.read()
    if ret:
        print("SUCCESS! Camera read a frame successfully.")
    else:
        print("WARNING: Camera opened, but failed to read a frame (blank).")
    cap.release()
else:
    print("ERROR: Could not open Camera 0 at all.")
