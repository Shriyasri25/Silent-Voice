"""
Silent Voice — mobile / camera device script

Captures webcam frames, estimates a simple expression label using
MediaPipe face landmarks (mouth-corner height as a happy/sad proxy,
with a brightness-based fallback), and posts the label to the AI PC's
/expression endpoint every frame.

Run:
  pip install -r requirements.txt   (mediapipe, opencv-python, requests)
  python mobile_vision.py

Set AI_PC_IP below to the AI PC's local network IP if running on a
separate phone/laptop. If both scripts run on the same machine,
leave it as localhost.

Performance optimizations applied
----------------------------------
  - Removed time.sleep(0.05)       : was artificially capping to 20 FPS
  - CAP_PROP_BUFFERSIZE = 1        : always grab the latest frame
  - 640×480 resolution             : minimal decode cost
  - MJPEG pixel format             : compressed stream from IP Webcam
  - HTTP POST on a background thread: expression send never stalls capture loop
  - rgb.flags.writeable = False    : avoids internal MediaPipe copy
  - Single BGR→RGB conversion      : reused for FaceMesh inference
  - FPS overlay on display frame
  - FPS + per-stage timing printed every 3 seconds
"""

import queue
import threading
import time

import cv2
import mediapipe as mp
import requests

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
# MediaPipe FaceMesh — fastest reliable settings
# ---------------------------------------------------------------------------
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=1,
    refine_landmarks=False,          # skip iris landmarks — not needed here
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
)

# Landmark indices for mouth corners and top/bottom lip
LEFT_MOUTH  = 61
RIGHT_MOUTH = 291
TOP_LIP     = 13
BOTTOM_LIP  = 14

# ---------------------------------------------------------------------------
# Background HTTP worker
# ---------------------------------------------------------------------------
# Expression changes are infrequent — a queue of size 1 is enough.
# If the worker is still sending, drop the new value (stale expressions
# arriving hundreds of ms late are worse than a small gap).
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
# Expression estimation
# ---------------------------------------------------------------------------

def _estimate_expression(rgb: "np.ndarray", frame_h: int, frame_w: int) -> str:
    """
    Estimate expression from a pre-converted RGB frame.

    Accepts the already-converted RGB array so the caller performs only
    one BGR→RGB conversion per frame instead of two.
    """
    import numpy as np

    results = face_mesh.process(rgb)

    if not results.multi_face_landmarks:
        # No face — brightness fallback
        # Convert a small centre crop to gray rather than the full frame
        cy, cx = frame_h // 2, frame_w // 2
        patch = rgb[cy-40:cy+40, cx-40:cx+40]
        brightness = patch.mean() if patch.size else 128
        if brightness > 140:
            return "HAPPY"
        elif brightness < 80:
            return "SAD"
        return "NEUTRAL"

    lm = results.multi_face_landmarks[0].landmark

    left   = lm[LEFT_MOUTH]
    right  = lm[RIGHT_MOUTH]
    top    = lm[TOP_LIP]
    bottom = lm[BOTTOM_LIP]

    mouth_width  = abs(right.x - left.x) * frame_w
    mouth_open   = abs(bottom.y - top.y) * frame_h
    corner_avg_y = (left.y + right.y) / 2
    mouth_center_y = (top.y + bottom.y) / 2

    if corner_avg_y < mouth_center_y - 0.005:
        return "HAPPY"
    if mouth_open < 2 and mouth_width < frame_w * 0.05:
        return "SAD"
    return "NEUTRAL"


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
    print()

    last_sent = ""

    # Timing accumulators
    t_report      = time.perf_counter()
    frame_count   = 0
    acc_capture   = 0.0
    acc_facemesh  = 0.0
    acc_enqueue   = 0.0
    acc_total     = 0.0

    while True:
        t_iter = time.perf_counter()

        # ---- 1. Capture --------------------------------------------------
        t0 = time.perf_counter()
        ret, frame = cap.read()
        acc_capture += (time.perf_counter() - t0) * 1000
        if not ret:
            continue

        h, w = frame.shape[:2]

        # ---- 2. Single BGR→RGB conversion — reused for FaceMesh ----------
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False   # avoids internal MediaPipe copy

        # ---- 3. FaceMesh inference ---------------------------------------
        t0 = time.perf_counter()
        expression = _estimate_expression(rgb, h, w)
        acc_facemesh += (time.perf_counter() - t0) * 1000

        rgb.flags.writeable = True

        # ---- 4. HTTP enqueue (non-blocking, only on change) --------------
        t0 = time.perf_counter()
        if expression != last_sent:
            _enqueue_expression(expression)
            last_sent = expression
        acc_enqueue += (time.perf_counter() - t0) * 1000

        acc_total  += (time.perf_counter() - t_iter) * 1000
        frame_count += 1

        # ---- 5. FPS / timing report --------------------------------------
        now_perf = time.perf_counter()
        elapsed  = now_perf - t_report
        if elapsed >= FPS_REPORT_SEC and frame_count > 0:
            n   = frame_count
            fps = n / elapsed
            print("=" * 44)
            print(f"  Capture    ........... {acc_capture  / n:6.1f} ms")
            print(f"  FaceMesh   ........... {acc_facemesh / n:6.1f} ms")
            print(f"  HTTP enqueue ......... {acc_enqueue  / n:6.1f} ms")
            print(f"  Total / frame ........ {acc_total    / n:6.1f} ms")
            print(f"  Capture FPS .......... {fps:6.1f}")
            print(f"  Processing FPS ....... {1000.0 / max(acc_facemesh / n, 1e-6):6.1f}")
            print("=" * 44)

            t_report    = now_perf
            frame_count = 0
            acc_capture = acc_facemesh = acc_enqueue = acc_total = 0.0

        # ---- 6. Display --------------------------------------------------
        fps_display = frame_count / max(elapsed, 1e-6)
        cv2.putText(frame, f"{expression}  {fps_display:.0f} FPS", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.imshow("Silent Voice — Mobile", frame)

        if cv2.waitKey(1) & 0xFF == 27:   # Esc to quit
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
