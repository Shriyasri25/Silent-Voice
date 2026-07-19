"""
Silent Voice — Gesture Detection Module

Reusable module for the single-process Edge AI pipeline.

Public API
----------
    process(frame)  →  GestureResult

Accepts any OpenCV BGR frame and returns:
  • hand_detected   – True if a hand was found
  • gesture_code    – 3-bit string e.g. "010" (index/middle/ring bend state),
                      or None when no hand is visible
  • annotated_frame – copy of the input frame with landmarks + code drawn

Single-process rule
-------------------
    This module NEVER creates a VideoCapture object.
    The camera is opened once in app.py, which passes BGR frames here.

Gesture encoding
----------------
    Each bit = one finger: index | middle | ring
    "1" = tip closer to wrist than PIP (bent)
    "0" = extended
    Matches the 3-bit codes from the original flex-sensor glove.

Standalone test mode (development only):
    python gesture.py       — press Esc to quit.
"""

from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass
from typing import Optional

import cv2
import mediapipe as mp
import numpy as np

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL_COMPLEXITY         = 0    # 0 = Lite (~2× faster); 1 = Full
MIN_DETECTION_CONFIDENCE = 0.6
MIN_TRACKING_CONFIDENCE  = 0.5
MAX_NUM_HANDS            = 1    # single-hand mode — faster search

# Landmark indices
_WRIST   = 0
_FINGERS = {
    "index":  {"tip": 8,  "pip": 6},
    "middle": {"tip": 12, "pip": 10},
    "ring":   {"tip": 16, "pip": 14},
}

# ---------------------------------------------------------------------------
# Data structure
# ---------------------------------------------------------------------------

@dataclass
class GestureResult:
    """All outputs produced by a single call to process()."""
    hand_detected:   bool            # True if at least one hand was found
    gesture_code:    Optional[str]   # "000".."111", or None when no hand
    annotated_frame: np.ndarray      # BGR frame with landmarks + code drawn


# ---------------------------------------------------------------------------
# Module-level MediaPipe Hands — created once at import time
# ---------------------------------------------------------------------------
# static_image_mode=False enables tracking mode: detection only on the first
# frame, then fast KLT tracking on subsequent frames.

_mp_hands = mp.solutions.hands
_hands    = _mp_hands.Hands(
    static_image_mode        = False,
    max_num_hands            = MAX_NUM_HANDS,
    model_complexity         = MODEL_COMPLEXITY,
    min_detection_confidence = MIN_DETECTION_CONFIDENCE,
    min_tracking_confidence  = MIN_TRACKING_CONFIDENCE,
)
_mp_draw = mp.solutions.drawing_utils


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def process(frame: np.ndarray) -> GestureResult:
    """
    Detect hand landmarks in a BGR frame and classify the gesture code.

    Args:
        frame: BGR image from cv2.VideoCapture.read() — NOT modified in place.

    Returns:
        GestureResult(hand_detected, gesture_code, annotated_frame).
    """
    # Mirror so the user's right hand appears on the right side of the display
    flipped = cv2.flip(frame, 1)

    rgb = cv2.cvtColor(flipped, cv2.COLOR_BGR2RGB)
    rgb.flags.writeable = False          # avoids internal MediaPipe copy
    results = _hands.process(rgb)
    rgb.flags.writeable = True

    annotated     = flipped.copy()
    hand_detected = False
    gesture_code: Optional[str] = None

    if results.multi_hand_landmarks:
        hand_detected  = True
        hand_landmarks = results.multi_hand_landmarks[0]
        _mp_draw.draw_landmarks(annotated, hand_landmarks, _mp_hands.HAND_CONNECTIONS)
        gesture_code = _classify(hand_landmarks.landmark)
        cv2.putText(
            annotated, f"Gesture: {gesture_code}",
            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2, cv2.LINE_AA,
        )
    else:
        cv2.putText(
            annotated, "No hand",
            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2, cv2.LINE_AA,
        )

    return GestureResult(
        hand_detected   = hand_detected,
        gesture_code    = gesture_code,
        annotated_frame = annotated,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _dist(a, b) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def _is_bent(landmarks, tip_idx: int, pip_idx: int) -> bool:
    """True if the finger tip is closer to the wrist than the PIP joint."""
    wrist = landmarks[_WRIST]
    return _dist(wrist, landmarks[tip_idx]) < _dist(wrist, landmarks[pip_idx])


def _classify(landmarks) -> str:
    """Return 3-bit gesture code: index | middle | ring."""
    bits = [
        "1" if _is_bent(landmarks, _FINGERS[f]["tip"], _FINGERS[f]["pip"]) else "0"
        for f in ("index", "middle", "ring")
    ]
    return "".join(bits)


# ---------------------------------------------------------------------------
# Standalone demo — development / tuning only
# ---------------------------------------------------------------------------

def main() -> None:
    """Open a camera, run gesture detection, display results. Press Esc to quit."""
    # CAMERA_SOURCE is a local variable here — gesture.py never owns the camera
    # in production. app.py does.
    raw = os.environ.get("CAMERA_SOURCE", "http://10.92.174.131:8080/video")
    source: str | int = raw
    try:
        source = int(raw)
    except (ValueError, TypeError):
        pass

    cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_FOURCC,       cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)

    if not cap.isOpened():
        raise RuntimeError(f"[Gesture standalone] Could not open: {source!r}")

    print(f"[Gesture] Standalone mode — source: {source!r}  Press Esc to quit.")
    fps_time = time.time()
    fps = 0.0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[Gesture] Frame grab failed — retrying...")
            continue

        result = process(frame)

        now = time.time()
        fps = 0.9 * fps + 0.1 / max(now - fps_time, 1e-6)
        fps_time = now
        cv2.putText(
            result.annotated_frame, f"FPS: {fps:.1f}",
            (frame.shape[1] - 110, 25),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2, cv2.LINE_AA,
        )

        cv2.imshow("Silent Voice — Gesture (standalone)", result.annotated_frame)
        if cv2.waitKey(1) & 0xFF == 27:
            break

    cap.release()
    cv2.destroyAllWindows()
    print("[Gesture] Stopped.")


if __name__ == "__main__":
    main()
