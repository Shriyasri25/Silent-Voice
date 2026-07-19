"""
Silent Voice — mobile / camera device script

Captures webcam frames, runs FER+ emotion classification via
face_detection.detect_faces() (which uses the Qualcomm AI Hub compiled
model with QNN/NPU when available, or falls back to CPU), and posts the
dominant emotion label to the AI PC's /expression endpoint on every change.

The old FaceMesh-based heuristic (mouth-corner geometry + brightness fallback)
has been replaced with the real FER+ ONNX inference pipeline so the expression
label sent to the AI PC is consistent with what face_detection.py reports.

Run:
  pip install -r requirements.txt   (mediapipe, opencv-python, requests, onnxruntime)
  python mobile_vision.py

Set AI_PC_IP below to the AI PC's local network IP if running on a
separate phone/laptop. If both scripts run on the same machine,
leave it as localhost.

Performance notes
-----------------
  - CAP_PROP_BUFFERSIZE = 1        : always grab the latest frame
  - 640×480 + MJPEG               : minimal decode cost
  - HTTP POST on a background thread: never stalls the capture loop
  - FER+ session loaded once at startup and reused across all frames
  - FPS + per-stage timing printed every FPS_REPORT_SEC seconds
"""

import queue
import threading
import time

import cv2
import requests

import face_detection as _fd   # detect_faces() → FaceDetectionResult

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

AI_PC_IP  = "localhost"
AI_PC_URL = f"http://{AI_PC_IP}:5000/expression"

# Camera source: 0 = built-in webcam.
# For IP Webcam (Android):  CAMERA_SOURCE = "http://192.168.1.42:8080/video"
CAMERA_SOURCE = 0

FPS_REPORT_SEC = 3.0   # how often to print the timing report

# ---------------------------------------------------------------------------
# Background HTTP worker
# ---------------------------------------------------------------------------

_http_queue: queue.Queue = queue.Queue(maxsize=1)


def _http_worker() -> None:
    """Drain _http_queue and POST each expression label. Daemon thread."""
    while True:
        expression = _http_queue.get()
        try:
            requests.post(AI_PC_URL, json={"expression": expression}, timeout=1.0)
        except requests.exceptions.RequestException as exc:
            print(f"  [Expression] HTTP send failed: {exc}")
        finally:
            _http_queue.task_done()


threading.Thread(target=_http_worker, daemon=True).start()


def _enqueue_expression(expression: str) -> None:
    """Non-blocking put — drop silently if the worker is still busy."""
    try:
        _http_queue.put_nowait(expression)
    except queue.Full:
        pass


# ---------------------------------------------------------------------------
# Capture setup
# ---------------------------------------------------------------------------

def _open_capture(source) -> cv2.VideoCapture:
    """Open video source with latency-optimised settings."""
    cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_FOURCC,       cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)
    if not cap.isOpened():
        raise RuntimeError(
            f"Could not open camera source '{source}'. "
            "Check camera permissions / IP Webcam URL."
        )
    return cap


# ---------------------------------------------------------------------------
# Expression derivation
# ---------------------------------------------------------------------------

def _dominant_emotion(face_result: "_fd.FaceDetectionResult") -> str:
    """
    Return the expression label to send to the AI PC.

    Rules:
      • One or more faces detected → use the FER+ label of the first face,
        uppercased to match the existing protocol ("HAPPY", "NEUTRAL", etc.).
      • No face detected → return "NEUTRAL" as a safe default.

    FER+ outputs 8 classes; we map them to the 3-class vocabulary that
    main.py / main_camera.py already understand:
        happiness           → HAPPY
        surprise            → SURPRISE   (new, harmless addition)
        sadness / fear /
        disgust / contempt  → SAD
        neutral / anger     → NEUTRAL
    """
    if not face_result.emotion_labels:
        return "NEUTRAL"

    raw = face_result.emotion_labels[0]   # first detected face

    _MAP = {
        "happiness": "HAPPY",
        "surprise":  "SURPRISE",
        "sadness":   "SAD",
        "fear":      "SAD",
        "disgust":   "SAD",
        "contempt":  "NEUTRAL",
        "anger":     "NEUTRAL",
        "neutral":   "NEUTRAL",
    }
    return _MAP.get(raw, "NEUTRAL")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    cap = _open_capture(CAMERA_SOURCE)

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[Mobile Vision] Source     : {CAMERA_SOURCE}")
    print(f"[Mobile Vision] Resolution : {actual_w}×{actual_h}")
    print(f"[Mobile Vision] Sending to : {AI_PC_URL}")

    # Warm up the FER+ session so the first real frame isn't slow
    print("[Mobile Vision] Loading FER+ model ...")
    _fd._get_fer_session()
    print("[Mobile Vision] Ready.\n")

    last_sent = ""

    # Smoothed FPS for the display overlay — exponential moving average,
    # same pattern used in face_detection.py and app.py
    fps_smooth  = 0.0
    fps_time    = time.time()

    # Timing accumulators
    t_report     = time.perf_counter()
    frame_count  = 0
    acc_capture  = 0.0
    acc_fer      = 0.0
    acc_enqueue  = 0.0
    acc_total    = 0.0

    while True:
        t_iter = time.perf_counter()

        # ---- 1. Capture --------------------------------------------------
        t0 = time.perf_counter()
        ret, frame = cap.read()
        acc_capture += (time.perf_counter() - t0) * 1000
        if not ret:
            continue

        # ---- 2. FER+ inference via face_detection module -----------------
        t0 = time.perf_counter()
        face_result = _fd.detect_faces(frame)
        acc_fer += (time.perf_counter() - t0) * 1000

        # ---- 3. Derive expression label ----------------------------------
        expression = _dominant_emotion(face_result)

        # ---- 4. HTTP enqueue (non-blocking, only on change) --------------
        t0 = time.perf_counter()
        if expression != last_sent:
            _enqueue_expression(expression)
            last_sent = expression
        acc_enqueue += (time.perf_counter() - t0) * 1000

        acc_total  += (time.perf_counter() - t_iter) * 1000
        frame_count += 1

        # Smoothed FPS — update every frame, unaffected by accumulator resets
        now_wall = time.time()
        fps_smooth = 0.9 * fps_smooth + 0.1 / max(now_wall - fps_time, 1e-6)
        fps_time   = now_wall

        # ---- 5. FPS / timing report --------------------------------------
        now_perf = time.perf_counter()
        elapsed  = now_perf - t_report
        if elapsed >= FPS_REPORT_SEC and frame_count > 0:
            n   = frame_count
            fps = n / elapsed
            print("=" * 44)
            print(f"  Capture    ........... {acc_capture / n:6.1f} ms")
            print(f"  FER+ infer ........... {acc_fer     / n:6.1f} ms")
            print(f"  HTTP enqueue ......... {acc_enqueue / n:6.1f} ms")
            print(f"  Total / frame ........ {acc_total   / n:6.1f} ms")
            print(f"  Capture FPS .......... {fps:6.1f}")
            print(f"  Processing FPS ....... {1000.0 / max(acc_fer / n, 1e-6):6.1f}")
            print("=" * 44)
            t_report    = now_perf
            frame_count = 0
            acc_capture = acc_fer = acc_enqueue = acc_total = 0.0

        # ---- 6. Display --------------------------------------------------
        # Use the annotated frame from detect_faces (already has boxes + labels)
        display = face_result.annotated_frame.copy()
        cv2.putText(
            display,
            f"{expression}  {fps_smooth:.0f} FPS",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2,
        )
        cv2.imshow("Silent Voice — Mobile Vision", display)

        if cv2.waitKey(1) & 0xFF == 27:   # Esc to quit
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

