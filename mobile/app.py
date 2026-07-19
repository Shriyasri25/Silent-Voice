"""
Silent Voice — Single-Process Edge AI Entry Point
==================================================

One command to run everything:

    python app.py

Architecture
------------
    ONE camera  →  ONE frame per iteration
                     │
                     ├── gesture.process(frame)
                     │       └── 3-bit code → phrase lookup → TTS
                     │
                     ├── face_detection.detect_faces(frame)
                     │       └── bboxes + confidence drawn on overlay
                     │
                     ├── [future] ocr.process(frame)
                     └── [future] eye_gaze.process(frame)

Camera ownership
----------------
    cv2.VideoCapture() is called ONLY in _open_camera() inside this file.
    gesture.py, face_detection.py, mobile_vision.py, and all other modules
    receive BGR frames passed by this loop — they NEVER open the camera.

Camera initialization behaviour
--------------------------------
    1. Read CAMERA_SOURCE from environment (fallback: IP Webcam URL below).
    2. "0" / 0 / "" → treat as local webcam index 0.
    3. Any other value → treat as URL; validate syntax before opening.
    4. Retry the configured source up to MAX_RETRIES times (1 s apart).
    5. If every retry fails → automatically try cv2.VideoCapture(0).
    6. RuntimeError is raised only if BOTH the configured source AND the
       webcam fallback fail.

Configuration (environment variables)
--------------------------------------
    CAMERA_SOURCE   — 0 for built-in webcam, or an IP Webcam URL
                      e.g. http://10.92.174.131:8080/video
    DISPLAY_WINDOWS — set to "0" to run headless (no imshow)
    DEBOUNCE_SEC    — seconds between identical gesture triggers (default 1.5)
    FPS_REPORT_SEC  — how often to print the timing report (default 3.0)
"""

from __future__ import annotations

import json
import os
import pathlib
import queue
import sys
import threading
import time
from urllib.parse import urlparse

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Path setup — make ai-pc/ importable for speech.py + phrases.json
# ---------------------------------------------------------------------------
_MOBILE_DIR = pathlib.Path(__file__).resolve().parent   # mobile/
_AI_PC_DIR  = _MOBILE_DIR.parent / "ai-pc"             # ai-pc/

if str(_MOBILE_DIR) not in sys.path:
    sys.path.insert(0, str(_MOBILE_DIR))
if str(_AI_PC_DIR) not in sys.path:
    sys.path.insert(0, str(_AI_PC_DIR))

# ---------------------------------------------------------------------------
# Local module imports — NO VideoCapture in any of these
# ---------------------------------------------------------------------------
import face_detection as _fd   # detect_faces(frame) → FaceDetectionResult
import gesture        as _gs   # process(frame)       → GestureResult

# ---------------------------------------------------------------------------
# AI-PC module imports
# ---------------------------------------------------------------------------
from speech import get_engine   # SpeechEngine singleton (Sarvam / pyttsx3)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Camera source: read from env, fall back to IP Webcam URL.
# Override at runtime:  set CAMERA_SOURCE=0   (local webcam)
#                       set CAMERA_SOURCE=http://192.168.1.x:8080/video
_RAW_SOURCE: str = os.environ.get(
    "CAMERA_SOURCE", "http://10.92.174.131:8080/video"
)

# Normalise "0" / "" to integer 0 so OpenCV uses the local webcam device.
def _parse_source(raw: str) -> "str | int":
    stripped = raw.strip()
    if stripped in ("", "0"):
        return 0
    try:
        return int(stripped)
    except ValueError:
        return stripped   # treat as URL

CAMERA_SOURCE: "str | int" = _parse_source(_RAW_SOURCE)

# Show OpenCV imshow windows. Set DISPLAY_WINDOWS=0 for headless / SSH.
DISPLAY_WINDOWS: bool = os.environ.get("DISPLAY_WINDOWS", "1") != "0"

# Minimum seconds between identical gesture triggers
DEBOUNCE_SEC: float = float(os.environ.get("DEBOUNCE_SEC", "1.5"))

# How often to print the FPS / timing report
FPS_REPORT_SEC: float = float(os.environ.get("FPS_REPORT_SEC", "3.0"))

# Camera retry settings
MAX_RETRIES    = 5
RETRY_DELAY_S  = 1.0

# ---------------------------------------------------------------------------
# Phrase table
# ---------------------------------------------------------------------------
_PHRASES_PATH = _AI_PC_DIR / "phrases.json"
with open(_PHRASES_PATH, encoding="utf-8") as _f:
    PHRASES: dict[str, str] = json.load(_f)

# ---------------------------------------------------------------------------
# Speech engine — one shared instance for the whole process
# ---------------------------------------------------------------------------
_speech = get_engine()

# ---------------------------------------------------------------------------
# Background TTS worker
# ---------------------------------------------------------------------------
# TTS (especially cloud Sarvam) can take 200 ms–3 s.  Running on a background
# thread ensures the camera loop never drops frames while audio plays.
# Queue(maxsize=1): if a new gesture arrives while one is queued, the stale
# phrase is replaced — we never speak out-of-date text.

_tts_queue: queue.Queue = queue.Queue(maxsize=1)


def _tts_worker() -> None:
    while True:
        phrase = _tts_queue.get()
        try:
            _speech.speak(phrase)
        except Exception as exc:
            print(f"[TTS ERROR] {exc}")
        finally:
            _tts_queue.task_done()


threading.Thread(target=_tts_worker, daemon=True, name="tts-worker").start()


def _enqueue_tts(phrase: str) -> None:
    """Non-blocking. If the queue is full, replace the waiting item."""
    try:
        _tts_queue.put_nowait(phrase)
    except queue.Full:
        try:
            _tts_queue.get_nowait()
            _tts_queue.task_done()
        except queue.Empty:
            pass
        try:
            _tts_queue.put_nowait(phrase)
        except queue.Full:
            pass


# ---------------------------------------------------------------------------
# Camera helpers
# ---------------------------------------------------------------------------

def _is_valid_url(source: "str | int") -> bool:
    """Return True if source looks like a syntactically valid HTTP/HTTPS URL."""
    if isinstance(source, int):
        return False
    try:
        p = urlparse(source)
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False


def _diagnose(source: "str | int") -> str:
    """Return a human-readable diagnosis string for a failed open attempt."""
    if isinstance(source, int):
        return (
            f"Local webcam index {source} is unavailable or busy. "
            "Check that no other application is using the camera."
        )
    if not _is_valid_url(source):
        return (
            f"'{source}' does not look like a valid URL. "
            "Expected format: http://<ip>:<port>/video"
        )
    parsed = urlparse(source)
    return (
        f"IP Webcam at '{source}' could not be reached. "
        f"Check that:\n"
        f"  • The IP Webcam app is running on the phone\n"
        f"  • The phone and this machine are on the same network\n"
        f"  • The host '{parsed.hostname}' is reachable (try ping)\n"
        f"  • The port {parsed.port} is not blocked by a firewall"
    )


def _try_open(source: "str | int", label: str) -> "cv2.VideoCapture | None":
    """
    Attempt to open a VideoCapture source up to MAX_RETRIES times.

    Returns the opened VideoCapture on success, or None on failure.
    Logs every attempt.
    """
    # Validate URL syntax before even trying to open
    if isinstance(source, str) and not _is_valid_url(source):
        print(f"[Camera] {label}: invalid URL syntax — '{source}'")
        print(f"[Camera] {_diagnose(source)}")
        return None

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"[Camera] {label} — attempt {attempt}/{MAX_RETRIES}: {source!r}")

        cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)

        if cap.isOpened():
            # Apply latency-optimised settings
            cap.set(cv2.CAP_PROP_FOURCC,       cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)

            actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            print(f"[Camera] {label} — opened successfully "
                  f"({actual_w}×{actual_h}) on attempt {attempt}")
            return cap

        cap.release()
        if attempt < MAX_RETRIES:
            print(f"[Camera] {label} — failed, retrying in {RETRY_DELAY_S:.0f}s...")
            time.sleep(RETRY_DELAY_S)

    print(f"[Camera] {label} — all {MAX_RETRIES} attempts failed.")
    print(f"[Camera] Diagnosis: {_diagnose(source)}")
    return None


def _open_camera(source: "str | int") -> cv2.VideoCapture:
    """
    Open the ONE camera for this process, with retry and automatic fallback.

    Steps:
        1. Try the configured source (URL or index) up to MAX_RETRIES times.
        2. If that fails and source is not already index 0, try webcam 0.
        3. Raise RuntimeError only after both options are exhausted.

    This is the ONLY place in the entire codebase that calls VideoCapture().

    Args:
        source: Integer webcam index or IP Webcam URL string.

    Returns:
        An opened cv2.VideoCapture, ready to read frames.

    Raises:
        RuntimeError: If the configured source AND the webcam fallback both fail.
    """
    # --- Attempt 1: configured source ---
    cap = _try_open(source, "Configured source")
    if cap is not None:
        print(f"[Camera] Using configured source: {source!r}")
        return cap

    # --- Attempt 2: local webcam fallback (skip if source is already 0) ---
    if source != 0:
        print("[Camera] Configured source failed — trying local webcam (index 0)...")
        cap = _try_open(0, "Webcam fallback")
        if cap is not None:
            print("[Camera] Using local webcam fallback (index 0).")
            return cap

    # --- Both failed ---
    raise RuntimeError(
        f"Could not open any camera source.\n"
        f"  Configured source : {source!r}\n"
        f"  Webcam fallback   : index 0\n"
        f"  Both failed after {MAX_RETRIES} retries each.\n"
        f"  {_diagnose(source)}"
    )


# ---------------------------------------------------------------------------
# Display compositor
# ---------------------------------------------------------------------------

def _build_display_frame(
    gesture_result: "_gs.GestureResult",
    face_result:    "_fd.FaceDetectionResult",
    fps:            float,
    last_phrase:    str,
) -> np.ndarray:
    """
    Merge gesture and face+emotion annotations onto a single display frame.

    The gesture module flips the frame horizontally (mirror mode).
    Face bboxes come from the unflipped frame, so we mirror their x coords
    to align with the flipped display.

    For each detected face we draw:
      • green bounding box
      • green confidence label  ("Face: 0.97")
      • amber emotion label     ("happiness")  from FER+ inference
    """
    display = gesture_result.annotated_frame.copy()
    h, w = display.shape[:2]

    for i, bbox in enumerate(face_result.bboxes):
        # Mirror x so the box aligns with the horizontally-flipped gesture frame
        mx = w - (bbox.x + bbox.w)

        # Bounding box
        cv2.rectangle(
            display,
            (mx, bbox.y),
            (mx + bbox.w, bbox.y + bbox.h),
            (0, 255, 0), 2,
        )

        # Confidence label
        label_y = max(bbox.y - 8, 15)
        cv2.putText(
            display, f"Face: {bbox.confidence:.2f}",
            (mx, label_y),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2, cv2.LINE_AA,
        )

        # Emotion label (amber) — one line above confidence
        if i < len(face_result.emotion_labels):
            emotion_y = max(label_y - 20, 15)
            cv2.putText(
                display, face_result.emotion_labels[i],
                (mx, emotion_y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 255), 2, cv2.LINE_AA,
            )

    # Status bar — bottom of frame
    face_count = len(face_result.bboxes)
    dominant   = face_result.emotion_labels[0] if face_result.emotion_labels else "—"
    cv2.putText(
        display,
        f"FPS: {fps:.1f}  |  Faces: {face_count}  |  Emotion: {dominant}",
        (10, h - 10),
        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 2, cv2.LINE_AA,
    )

    # Last spoken phrase — top right
    if last_phrase:
        cv2.putText(
            display, f"Said: {last_phrase}",
            (max(0, w - 400), 55),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 200, 0), 2, cv2.LINE_AA,
        )

    return display


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Single-process entry point.

    Opens the camera once, then on every frame:
      1. gesture.process(frame)             — MediaPipe Hands
      2. face_detection.detect_faces(frame) — MediaPipe Face Detection
      3. Phrase lookup + async TTS          — gesture code → phrase → speech
      4. Compositor + imshow                — merged overlay window

    Press Esc to quit.
    """
    print("=" * 52)
    print("  Silent Voice — Single-Process Edge AI")
    print("=" * 52)
    print(f"  Camera source  : {CAMERA_SOURCE!r}")
    print(f"  Display windows: {DISPLAY_WINDOWS}")
    print(f"  Debounce       : {DEBOUNCE_SEC}s")
    print(f"  Phrases loaded : {len(PHRASES)}")
    print(f"  Max retries    : {MAX_RETRIES} (1s apart)")
    print("=" * 52)
    print()

    # This is the ONE place in the entire codebase that opens the camera.
    cap = _open_camera(CAMERA_SOURCE)

    # Gesture debounce state
    last_code:      "str | None" = None
    last_send_time: float        = 0.0
    last_phrase:    str          = ""

    # Timing accumulators for FPS report
    t_report    = time.perf_counter()
    frame_count = 0
    acc_gesture = 0.0
    acc_face    = 0.0
    acc_total   = 0.0

    # Smoothed FPS for display overlay
    fps      = 0.0
    fps_time = time.time()

    print("[App] Pipeline running — press Esc to quit.\n")

    while True:
        t_iter = time.perf_counter()

        # ------------------------------------------------------------
        # 1. Capture — one read, shared by all modules this iteration
        # ------------------------------------------------------------
        ret, frame = cap.read()
        if not ret:
            print("[Camera] Frame grab failed — retrying...")
            continue

        # ------------------------------------------------------------
        # 2. Gesture detection  (MediaPipe Hands)
        # ------------------------------------------------------------
        t0 = time.perf_counter()
        gesture_result = _gs.process(frame)
        acc_gesture += (time.perf_counter() - t0) * 1000

        # ------------------------------------------------------------
        # 3. Face detection  (MediaPipe Face Detection)
        # ------------------------------------------------------------
        t0 = time.perf_counter()
        face_result = _fd.detect_faces(frame)
        acc_face += (time.perf_counter() - t0) * 1000

        # ------------------------------------------------------------
        # [Future] ocr_result    = ocr.process(frame)
        # [Future] gaze_result   = eye_gaze.process(frame)
        # ------------------------------------------------------------

        # ------------------------------------------------------------
        # 4. Phrase lookup + async TTS
        # ------------------------------------------------------------
        code = gesture_result.gesture_code
        if code is not None:
            now = time.time()
            if code != last_code or (now - last_send_time) > DEBOUNCE_SEC:
                phrase = PHRASES.get(code, "I need help")
                print(
                    f"[Gesture] code={code}  phrase='{phrase}'  "
                    f"face={'YES' if face_result.bboxes else 'NO'}"
                )
                _enqueue_tts(phrase)
                last_code      = code
                last_send_time = now
                last_phrase    = phrase

        # ------------------------------------------------------------
        # 5. FPS smoothing
        # ------------------------------------------------------------
        now_t    = time.time()
        fps      = 0.9 * fps + 0.1 / max(now_t - fps_time, 1e-6)
        fps_time = now_t

        acc_total  += (time.perf_counter() - t_iter) * 1000
        frame_count += 1

        # ------------------------------------------------------------
        # 6. Periodic timing report
        # ------------------------------------------------------------
        now_perf = time.perf_counter()
        elapsed  = now_perf - t_report
        if elapsed >= FPS_REPORT_SEC and frame_count > 0:
            n = frame_count
            print("=" * 46)
            print(f"  Gesture    ............. {acc_gesture / n:6.1f} ms")
            print(f"  FaceDetect ............. {acc_face    / n:6.1f} ms")
            print(f"  Total / frame .......... {acc_total   / n:6.1f} ms")
            print(f"  Pipeline FPS ........... {n / elapsed:6.1f}")
            print("=" * 46)
            t_report    = now_perf
            frame_count = 0
            acc_gesture = acc_face = acc_total = 0.0

        # ------------------------------------------------------------
        # 7. Display
        # ------------------------------------------------------------
        if DISPLAY_WINDOWS:
            display = _build_display_frame(
                gesture_result, face_result, fps, last_phrase
            )
            cv2.imshow("Silent Voice — Edge AI", display)
            if cv2.waitKey(1) & 0xFF == 27:   # Esc
                break
        else:
            time.sleep(0)   # yield to OS scheduler in headless mode

    # Cleanup
    cap.release()
    if DISPLAY_WINDOWS:
        cv2.destroyAllWindows()
    print("\n[App] Stopped.")


if __name__ == "__main__":
    main()
