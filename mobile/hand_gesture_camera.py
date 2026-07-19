"""
Silent Voice — Camera-based gesture detection (flex sensor replacement)

Uses MediaPipe Hands to track your hand from the webcam and detects
index/middle/ring finger bend state, producing the same 3-bit code
("000".."111") the flex-sensor glove would have sent — so it drops into
the existing phrase table with zero changes to phrases.json.

Run:
  pip install -r requirements.txt   (mediapipe, opencv-python, requests)
  python hand_gesture_camera.py

Set AI_PC_IP below if the AI PC is a separate device on the network.
Requires ai-pc/main_camera.py to be running (not the serial version).

Performance optimizations applied
----------------------------------
  - CAP_PROP_BUFFERSIZE = 1        : always grab the latest frame, no queue build-up
  - 640x480 capture resolution     : half the pixels of 1080p → ~4× faster decode
  - MJPEG pixel format             : hardware-compressed stream from IP Webcam,
                                     drastically less bandwidth than raw YUYV
  - model_complexity = 0           : MediaPipe Lite model (~2× faster, same accuracy
                                     at arm's length)
  - static_image_mode = False      : enables tracking mode — detection only on first
                                     frame, fast KLT tracker on subsequent frames
  - HTTP POST on a background thread: gesture send never stalls the capture loop
  - rgb.flags.writeable = False    : avoids a full-frame copy inside MediaPipe
  - Single BGR→RGB conversion      : done once on the (already small) 640×480 frame
  - FPS + per-stage timing printed every 3 seconds
"""

import math
import queue
import threading
import time

import cv2
import mediapipe as mp
import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

AI_PC_IP  = "localhost"          # change to AI PC LAN IP if on a separate device
AI_PC_URL = f"http://{AI_PC_IP}:5000/gesture"

# Camera source: 0 = built-in webcam.
# For IP Webcam (Android) use the MJPEG stream URL, e.g.:
#   CAMERA_SOURCE = "http://192.168.1.42:8080/video"
CAMERA_SOURCE = "http://10.92.174.131:8080/video"

DEBOUNCE_SEC      = 0.3   # minimum seconds between identical gesture sends
FPS_REPORT_SEC    = 3.0   # how often to print the FPS / timing report

# ---------------------------------------------------------------------------
# MediaPipe — fastest reliable settings
# ---------------------------------------------------------------------------
# model_complexity=0  → Lite model  (~75 landmarks, ~2× faster than default)
# static_image_mode=False           → tracking mode (detection only once)
# max_num_hands=1                   → skip multi-hand search
# ---------------------------------------------------------------------------
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=1,
    model_complexity=0,
    min_detection_confidence=0.6,
    min_tracking_confidence=0.5,
)
mp_draw = mp.solutions.drawing_utils

# Landmark indices
WRIST   = 0
FINGERS = {
    "index":  {"tip": 8,  "pip": 6},
    "middle": {"tip": 12, "pip": 10},
    "ring":   {"tip": 16, "pip": 14},
}

# ---------------------------------------------------------------------------
# Background HTTP worker
# ---------------------------------------------------------------------------
# A dedicated thread drains a queue of gesture codes and POSTs them to the
# AI PC. This means the camera loop NEVER waits for a network round-trip.
# Queue size = 1: if a POST is slow we drop intermediate codes rather than
# accumulate a backlog (stale gestures are useless).
# ---------------------------------------------------------------------------

_http_queue: queue.Queue = queue.Queue(maxsize=1)


def _http_worker() -> None:
    """Drain _http_queue and POST each code. Runs as a daemon thread."""
    while True:
        code = _http_queue.get()
        try:
            requests.post(AI_PC_URL, json={"gesture": code}, timeout=1.0)
            print(f"  Sent gesture: {code}")
        except requests.exceptions.RequestException as exc:
            print(f"  HTTP send failed: {exc}")
        finally:
            _http_queue.task_done()


threading.Thread(target=_http_worker, daemon=True).start()


def _enqueue_gesture(code: str) -> None:
    """Non-blocking put — drop the code if the worker is still busy."""
    try:
        _http_queue.put_nowait(code)
    except queue.Full:
        pass   # previous send still in progress; skip this duplicate


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _dist(a, b) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def _is_bent(landmarks, tip_idx: int, pip_idx: int) -> bool:
    wrist = landmarks[WRIST]
    tip   = landmarks[tip_idx]
    pip   = landmarks[pip_idx]
    return _dist(wrist, tip) < _dist(wrist, pip)


def _get_gesture_code(landmarks) -> str:
    index_bit  = "1" if _is_bent(landmarks, FINGERS["index"]["tip"],
                                             FINGERS["index"]["pip"])  else "0"
    middle_bit = "1" if _is_bent(landmarks, FINGERS["middle"]["tip"],
                                             FINGERS["middle"]["pip"]) else "0"
    ring_bit   = "1" if _is_bent(landmarks, FINGERS["ring"]["tip"],
                                             FINGERS["ring"]["pip"])   else "0"
    return index_bit + middle_bit + ring_bit


# ---------------------------------------------------------------------------
# Capture setup
# ---------------------------------------------------------------------------

def _open_capture(source) -> cv2.VideoCapture:
    """
    Open the video source with latency-optimised settings.

    - MJPEG pixel format  → hardware-compressed stream (IP Webcam sends MJPEG)
    - 640×480 resolution  → minimal decode cost; MediaPipe works well at this size
    - BUFFERSIZE = 1      → always read the newest frame; no queue build-up
    """
    cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)

    # Request MJPEG so IP Webcam sends compressed frames (much less bandwidth).
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

    # Target resolution — IP Webcam will honour this if supported.
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    # Keep only 1 frame in the OS buffer so we always get the latest image.
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        raise RuntimeError(
            f"Could not open camera source '{source}'. "
            "Check IP Webcam is running and CAMERA_SOURCE is correct."
        )
    return cap


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    cap = _open_capture(CAMERA_SOURCE)

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[Camera Gesture] Source      : {CAMERA_SOURCE}")
    print(f"[Camera Gesture] Resolution  : {actual_w}×{actual_h}")
    print(f"[Camera Gesture] Sending to  : {AI_PC_URL}")
    print(f"[Camera Gesture] MediaPipe   : model_complexity=0 (Lite), max_hands=1")
    print()

    last_sent          = None
    last_send_time     = 0.0

    # Timing accumulators for the FPS report
    t_report           = time.perf_counter()
    frame_count        = 0
    acc_capture        = 0.0   # ms spent in cap.read()
    acc_mediapipe      = 0.0   # ms spent in hands.process()
    acc_gesture        = 0.0   # ms spent in gesture classification
    acc_enqueue        = 0.0   # ms spent enqueuing HTTP post
    acc_total          = 0.0   # ms per full iteration

    while True:
        t_iter_start = time.perf_counter()

        # ---- 1. Capture --------------------------------------------------
        t0 = time.perf_counter()
        ret, frame = cap.read()
        t_capture = (time.perf_counter() - t0) * 1000
        if not ret:
            continue

        acc_capture += t_capture

        # ---- 2. Pre-process ----------------------------------------------
        # Flip once; reuse for both display and inference — no duplicate copy.
        frame = cv2.flip(frame, 1)

        # Single BGR→RGB conversion on the 640×480 frame.
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Tell MediaPipe it can use this buffer directly (no internal copy).
        rgb.flags.writeable = False

        # ---- 3. MediaPipe inference --------------------------------------
        t0 = time.perf_counter()
        results = hands.process(rgb)
        t_mediapipe = (time.perf_counter() - t0) * 1000

        rgb.flags.writeable = True   # restore for any downstream use
        acc_mediapipe += t_mediapipe

        # ---- 4. Gesture classification -----------------------------------
        t0 = time.perf_counter()
        code = None
        if results.multi_hand_landmarks:
            hand_landmarks = results.multi_hand_landmarks[0]
            mp_draw.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
            code = _get_gesture_code(hand_landmarks.landmark)
            cv2.putText(frame, f"Code: {code}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        else:
            cv2.putText(frame, "No hand", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        t_gesture = (time.perf_counter() - t0) * 1000
        acc_gesture += t_gesture

        # ---- 5. HTTP enqueue (non-blocking) ------------------------------
        t0 = time.perf_counter()
        if code is not None:
            now = time.time()
            if code != last_sent and (now - last_send_time) > DEBOUNCE_SEC:
                _enqueue_gesture(code)
                last_sent      = code
                last_send_time = now
        t_enqueue = (time.perf_counter() - t0) * 1000
        acc_enqueue += t_enqueue

        # ---- 6. Display --------------------------------------------------
        acc_total  += (time.perf_counter() - t_iter_start) * 1000
        frame_count += 1

        # ---- 7. FPS / timing report every FPS_REPORT_SEC seconds ---------
        now_perf = time.perf_counter()
        if now_perf - t_report >= FPS_REPORT_SEC and frame_count > 0:
            n   = frame_count
            fps = n / (now_perf - t_report)

            print("=" * 44)
            print(f"  Capture    ........... {acc_capture  / n:6.1f} ms")
            print(f"  MediaPipe  ........... {acc_mediapipe/ n:6.1f} ms")
            print(f"  Gesture    ........... {acc_gesture  / n:6.1f} ms")
            print(f"  HTTP enqueue ......... {acc_enqueue  / n:6.1f} ms")
            print(f"  Total / frame ........ {acc_total    / n:6.1f} ms")
            print(f"  Capture FPS .......... {fps:6.1f}")
            print(f"  Processing FPS ....... {1000.0 / max(acc_mediapipe / n + acc_gesture / n, 1e-6):6.1f}")
            print(f"  Inference FPS ........ {1000.0 / max(acc_mediapipe / n, 1e-6):6.1f}")
            print("=" * 44)

            # Reset accumulators
            t_report    = now_perf
            frame_count = 0
            acc_capture = acc_mediapipe = acc_gesture = acc_enqueue = acc_total = 0.0

        cv2.imshow("Silent Voice — Camera Gesture", frame)
        if cv2.waitKey(1) & 0xFF == 27:   # Esc to quit
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
