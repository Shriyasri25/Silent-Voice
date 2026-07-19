"""
Silent Voice — Face Detection + FER+ Emotion Recognition Module

Detects faces in a BGR frame using MediaPipe Face Detection, runs
FER+ INT8 emotion classification on each crop via ONNX Runtime, draws
bounding boxes with emotion labels, and returns full results.

Architecture:
    frame
      ↓
    MediaPipe Face Detection
      ↓
    Face Bounding Box  →  crop_face()
      ↓
    preprocess()       (64×64 grayscale, float32, NCHW)
      ↓
    FER+ ONNX Runtime inference
      ↓
    Emotion label + confidence

Compiled model (Qualcomm AI Hub — Snapdragon X Elite):
    ai-pc/models/emotion-ferplus-snapdragon-x-elite.onnx
    ai-pc/models/model.data   ← external data file, must stay alongside .onnx

Fallback model (original INT8, works on any CPU):
    ai-pc/models/emotion-ferplus-12-int8.onnx

Integration:
    Import and call detect_faces() on any BGR frame captured via OpenCV.
    The returned bounding boxes use the same coordinate space as the
    original frame and overlay cleanly on Hand Gesture / Mobile Vision.

Usage (standalone):
    pip install mediapipe opencv-python onnxruntime
    python face_detection.py

    Press Esc to quit.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Optional

import cv2
import mediapipe as mp
import numpy as np
import onnxruntime as ort

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Camera source — match the value used in hand_gesture_camera.py /
# mobile_vision.py. 0 = built-in webcam; use an IP Webcam URL for the phone.
#   e.g. "http://10.92.174.131:8080/video"
CAMERA_SOURCE = "http://10.92.174.131:8080/video"

# MediaPipe Face Detection model selection:
#   0 = short-range  (≤2 m, faster — best for webcam close-ups)
#   1 = full-range   (up to 5 m, slightly slower)
MODEL_SELECTION = 0

# Minimum detection confidence to accept a face (0.0–1.0)
MIN_DETECTION_CONFIDENCE = 0.5

# Visual style for bounding boxes
BOX_COLOR      = (0, 255, 0)   # green
BOX_THICKNESS  = 2
TEXT_COLOR     = (0, 255, 0)
FONT           = cv2.FONT_HERSHEY_SIMPLEX
FONT_SCALE     = 0.6
FONT_THICKNESS = 2

# Padding added around the raw bounding box before cropping (pixels).
# Gives downstream models a little context around the face boundary.
CROP_PADDING = 10

# ---------------------------------------------------------------------------
# FER+ model configuration
# ---------------------------------------------------------------------------

# Resolve model paths relative to this file's location.
# face_detection.py lives in mobile/ — the models are in ../ai-pc/models/
_THIS_DIR   = os.path.dirname(os.path.abspath(__file__))
_MODELS_DIR = os.path.join(_THIS_DIR, "..", "ai-pc", "models")

# Compiled model (Qualcomm AI Hub — optimised for Snapdragon X Elite).
# Uses external data: model.data must sit alongside this .onnx file.
COMPILED_MODEL_PATH  = os.path.join(_MODELS_DIR, "emotion-ferplus-snapdragon-x-elite.onnx")
COMPILED_DATA_PATH   = os.path.join(_MODELS_DIR, "model.data")   # external weights

# Fallback: original INT8 ONNX (works on any CPU with onnxruntime).
FALLBACK_MODEL_PATH  = os.path.join(_MODELS_DIR, "emotion-ferplus-12-int8.onnx")

# FER+ output label map (8 classes, index → emotion string)
EMOTION_LABELS = [
    "neutral", "happiness", "surprise", "sadness",
    "anger",   "disgust",   "fear",     "contempt",
]

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FaceBBox:
    """Pixel-space bounding box for a single detected face."""
    x: int          # left edge
    y: int          # top edge
    w: int          # width
    h: int          # height
    confidence: float  # detection confidence score (0.0–1.0)


@dataclass
class FaceDetectionResult:
    """All outputs produced by a single call to detect_faces()."""
    annotated_frame: np.ndarray          # BGR frame with boxes and emotion labels drawn
    bboxes: list[FaceBBox]               # one entry per detected face
    crops: list[np.ndarray]              # BGR crop per detected face
    emotion_labels: list[str]            # emotion string per detected face (e.g. "happiness")


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def initialize_face_detector(
    model_selection: int = MODEL_SELECTION,
    min_detection_confidence: float = MIN_DETECTION_CONFIDENCE,
) -> mp.solutions.face_detection.FaceDetection:
    """
    Create and return a MediaPipe FaceDetection instance.

    Call once at startup and reuse the returned object across frames for
    maximum efficiency — MediaPipe models are expensive to load.

    Args:
        model_selection:          0 = short-range (≤2 m), 1 = full-range (≤5 m).
        min_detection_confidence: Detections below this score are discarded.

    Returns:
        A ready-to-use mp.solutions.face_detection.FaceDetection object.
    """
    return mp.solutions.face_detection.FaceDetection(
        model_selection=model_selection,
        min_detection_confidence=min_detection_confidence,
    )


def initialize_fer_session() -> ort.InferenceSession:
    """
    Create and return an ONNX Runtime InferenceSession for FER+ inference.

    Load order:
      1. Compiled model (emotion-ferplus-snapdragon-x-elite.onnx) with
         QNNExecutionProvider — runs on Snapdragon X Elite NPU/DSP.
      2. Same compiled model with CPUExecutionProvider — fallback when
         QNN is unavailable (e.g. a non-Snapdragon machine).
      3. Original INT8 ONNX with CPUExecutionProvider — last resort.

    The compiled model uses external data (model.data), so both files must
    sit in the same directory. ONNX Runtime locates model.data automatically
    by its recorded relative path inside the .onnx file.

    Returns:
        A ready-to-use onnxruntime.InferenceSession.
    """
    # --- Attempt 1: compiled model on QNN (Snapdragon NPU) ---
    if os.path.exists(COMPILED_MODEL_PATH) and os.path.exists(COMPILED_DATA_PATH):
        available = [ep for ep in ort.get_available_providers()]
        if "QNNExecutionProvider" in available:
            try:
                sess = ort.InferenceSession(
                    COMPILED_MODEL_PATH,
                    providers=["QNNExecutionProvider"],
                )
                print("[FER+] Using compiled model on QNNExecutionProvider (NPU)")
                return sess
            except Exception as e:
                print(f"[FER+] QNN provider failed ({e}), falling back to CPU")

        # --- Attempt 2: compiled model on CPU ---
        try:
            sess = ort.InferenceSession(
                COMPILED_MODEL_PATH,
                providers=["CPUExecutionProvider"],
            )
            print("[FER+] Using compiled model on CPUExecutionProvider")
            return sess
        except Exception as e:
            print(f"[FER+] Compiled model failed ({e}), falling back to original")

    # --- Attempt 3: original INT8 ONNX on CPU ---
    sess = ort.InferenceSession(
        FALLBACK_MODEL_PATH,
        providers=["CPUExecutionProvider"],
    )
    print("[FER+] Using original INT8 ONNX on CPUExecutionProvider")
    return sess


# Module-level singletons — shared by all callers in the same process.
_detector: Optional[mp.solutions.face_detection.FaceDetection] = None
_fer_session: Optional[ort.InferenceSession] = None


def _get_detector() -> mp.solutions.face_detection.FaceDetection:
    """Return the module-level face detector, creating it on first call."""
    global _detector
    if _detector is None:
        _detector = initialize_face_detector()
    return _detector


def _get_fer_session() -> ort.InferenceSession:
    """Return the module-level FER+ session, creating it on first call."""
    global _fer_session
    if _fer_session is None:
        _fer_session = initialize_fer_session()
    return _fer_session


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def preprocess(crop: np.ndarray) -> np.ndarray:
    """
    Prepare a BGR face crop for FER+ ONNX inference.

    FER+ expects:
        - Shape  : (1, 1, 64, 64)   — NCHW, single grayscale channel
        - dtype  : float32
        - Range  : [0.0, 255.0]     — NOT normalised to [0, 1]

    Args:
        crop: BGR face crop from crop_face() — any size.

    Returns:
        NumPy array of shape (1, 1, 64, 64), dtype float32.
    """
    gray   = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)          # → (H, W)
    resized = cv2.resize(gray, (64, 64), interpolation=cv2.INTER_AREA)  # → (64, 64)
    blob   = resized.astype(np.float32)                       # keep [0, 255] range
    return blob[np.newaxis, np.newaxis, :, :]                 # → (1, 1, 64, 64)


def run_fer_inference(preprocessed: np.ndarray) -> str:
    """
    Run FER+ ONNX inference on a preprocessed face blob.

    Args:
        preprocessed: float32 array of shape (1, 1, 64, 64) from preprocess().

    Returns:
        Emotion label string, e.g. "happiness".
    """
    session = _get_fer_session()
    input_name = session.get_inputs()[0].name                 # "Input3"
    outputs = session.run(None, {input_name: preprocessed})  # list of arrays
    logits = outputs[0].flatten()                             # shape (8,)
    idx = int(np.argmax(logits))
    return EMOTION_LABELS[idx]


def detect_faces(
    frame: np.ndarray,
    detector: Optional[mp.solutions.face_detection.FaceDetection] = None,
) -> FaceDetectionResult:
    """
    Detect all faces in a BGR frame, run FER+ emotion inference, and
    return annotated results.

    Steps:
        1. Convert BGR → RGB for MediaPipe.
        2. Run face detection.
        3. Convert relative bounding boxes → pixel coordinates.
        4. Crop each face from the original frame.
        5. Preprocess each crop and run FER+ ONNX inference.
        6. Draw boxes + confidence scores + emotion labels on an annotated copy.

    Args:
        frame:    BGR image as a NumPy array (from cv2.VideoCapture.read()).
        detector: Optional pre-created detector. Uses the module-level
                  singleton when omitted.

    Returns:
        FaceDetectionResult with annotated_frame, bboxes, crops, and emotion_labels.
    """
    if detector is None:
        detector = _get_detector()

    h, w = frame.shape[:2]
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    rgb.flags.writeable = False
    results = detector.process(rgb)
    rgb.flags.writeable = True

    bboxes: list[FaceBBox] = []
    crops:  list[np.ndarray] = []
    emotion_labels: list[str] = []

    if results.detections:
        for detection in results.detections:
            bbox = _relative_bbox_to_pixels(detection, w, h)
            bboxes.append(bbox)
            crop = crop_face(frame, bbox)
            crops.append(crop)

            # FER+ emotion inference
            try:
                blob    = preprocess(crop)
                emotion = run_fer_inference(blob)
            except Exception:
                emotion = "unknown"
            emotion_labels.append(emotion)

    annotated = draw_face_boxes(frame, bboxes, emotion_labels)

    return FaceDetectionResult(
        annotated_frame=annotated,
        bboxes=bboxes,
        crops=crops,
        emotion_labels=emotion_labels,
    )


def crop_face(frame: np.ndarray, bbox: FaceBBox) -> np.ndarray:
    """
    Crop a single face from the frame using its bounding box.

    Applies CROP_PADDING on all sides and clamps to image boundaries so
    the crop is always valid regardless of edge-touching detections.

    The returned crop is a fresh NumPy array in BGR format — it is
    independent of the source frame and safe to store or pass downstream.
    Call preprocess() on the result before passing it to run_fer_inference().

    Args:
        frame: Original BGR frame.
        bbox:  Pixel-space bounding box for the face.

    Returns:
        BGR crop as a NumPy array.
    """
    h, w = frame.shape[:2]

    x1 = max(0, bbox.x - CROP_PADDING)
    y1 = max(0, bbox.y - CROP_PADDING)
    x2 = min(w, bbox.x + bbox.w + CROP_PADDING)
    y2 = min(h, bbox.y + bbox.h + CROP_PADDING)

    return frame[y1:y2, x1:x2].copy()


def draw_face_boxes(
    frame: np.ndarray,
    bboxes: list[FaceBBox],
    emotion_labels: Optional[list[str]] = None,
) -> np.ndarray:
    """
    Draw bounding boxes, confidence scores, and emotion labels onto a copy
    of the frame.

    Each box is labelled with the confidence score on one line and the
    emotion label on the line above it, matching the overlay style used
    in hand_gesture_camera.py.

    Args:
        frame:          BGR frame (not modified in place).
        bboxes:         List of FaceBBox objects from detect_faces().
        emotion_labels: Optional list of emotion strings, one per bbox.
                        When provided, the emotion is drawn above each box.

    Returns:
        Annotated BGR frame (new array — original is untouched).
    """
    annotated = frame.copy()

    for i, bbox in enumerate(bboxes):
        # Bounding box rectangle
        cv2.rectangle(
            annotated,
            (bbox.x, bbox.y),
            (bbox.x + bbox.w, bbox.y + bbox.h),
            BOX_COLOR,
            BOX_THICKNESS,
        )

        # Confidence label — e.g. "Face: 0.97"
        label = f"Face: {bbox.confidence:.2f}"
        label_y = max(bbox.y - 8, 15)
        cv2.putText(
            annotated,
            label,
            (bbox.x, label_y),
            FONT,
            FONT_SCALE,
            TEXT_COLOR,
            FONT_THICKNESS,
            cv2.LINE_AA,
        )

        # Emotion label drawn above confidence — e.g. "happiness"
        if emotion_labels and i < len(emotion_labels):
            emotion_y = max(label_y - 22, 15)
            cv2.putText(
                annotated,
                emotion_labels[i],
                (bbox.x, emotion_y),
                FONT,
                FONT_SCALE,
                (0, 200, 255),   # amber — visually distinct from the green confidence text
                FONT_THICKNESS,
                cv2.LINE_AA,
            )

    return annotated


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _relative_bbox_to_pixels(
    detection: mp.solutions.face_detection.Detection,
    frame_w: int,
    frame_h: int,
) -> FaceBBox:
    """
    Convert a MediaPipe Detection's relative bounding box to pixel coords.

    MediaPipe returns normalised coordinates in [0, 1]. Multiply by frame
    dimensions and clamp to ensure the box never exceeds image boundaries.

    Args:
        detection: A single MediaPipe detection result.
        frame_w:   Frame width in pixels.
        frame_h:   Frame height in pixels.

    Returns:
        FaceBBox with integer pixel coordinates.
    """
    rel_bb = detection.location_data.relative_bounding_box

    x = max(0, int(rel_bb.xmin * frame_w))
    y = max(0, int(rel_bb.ymin * frame_h))
    w = min(int(rel_bb.width  * frame_w), frame_w - x)
    h = min(int(rel_bb.height * frame_h), frame_h - y)

    confidence = detection.score[0]  # primary score; list for multi-stage models

    return FaceBBox(x=x, y=y, w=w, h=h, confidence=confidence)


# ---------------------------------------------------------------------------
# Standalone demo — mirrors the loop structure in hand_gesture_camera.py
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Standalone demo: open a webcam, run face detection + FER+ emotion
    recognition, display results.

    Press Esc to quit.
    """
    cap = cv2.VideoCapture(CAMERA_SOURCE)
    if not cap.isOpened():
        raise RuntimeError(
            f"Could not open camera source '{CAMERA_SOURCE}'. "
            "Check the CAMERA_SOURCE variable at the top of this file."
        )

    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    detector = initialize_face_detector()

    # Warm up the FER+ session (loads model on first call)
    print("[Face Detection] Initialising FER+ model ...")
    _get_fer_session()
    print("[Face Detection] Running — press Esc to quit.")

    fps_time = time.time()
    fps = 0.0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[Face Detection] Frame grab failed — retrying...")
            continue

        result = detect_faces(frame, detector)

        # FPS overlay (top-right corner)
        now = time.time()
        fps = 0.9 * fps + 0.1 * (1.0 / max(now - fps_time, 1e-6))
        fps_time = now
        cv2.putText(
            result.annotated_frame,
            f"FPS: {fps:.1f}",
            (frame.shape[1] - 110, 25),
            FONT,
            FONT_SCALE,
            (255, 255, 0),
            FONT_THICKNESS,
            cv2.LINE_AA,
        )

        # Face count overlay (top-left)
        face_count = len(result.bboxes)
        cv2.putText(
            result.annotated_frame,
            f"Faces: {face_count}",
            (10, 30),
            FONT,
            FONT_SCALE,
            TEXT_COLOR,
            FONT_THICKNESS,
            cv2.LINE_AA,
        )

        cv2.imshow("Silent Voice — Face Detection + Emotion", result.annotated_frame)

        if result.crops:
            cv2.imshow("Silent Voice — Face Crop [0]", result.crops[0])

        if cv2.waitKey(1) & 0xFF == 27:  # Esc
            break

    cap.release()
    cv2.destroyAllWindows()
    print("[Face Detection] Stopped.")


if __name__ == "__main__":
    main()
