"""
Silent Voice — Face Detection Module

Detects faces in a BGR frame using MediaPipe Face Detection, draws
bounding boxes with confidence scores, and returns cropped face images
ready for downstream processing.

Architecture:
    frame
      ↓
    MediaPipe Face Detection
      ↓
    Face Bounding Box
      ↓
    crop_face()
      ↓
    [TODO] preprocess()          ← resize, grayscale, normalize
      ↓
    [TODO] FER+ ONNX inference   ← onnxruntime session
      ↓
    Emotion label

Integration:
    Import and call detect_faces() on any BGR frame captured via OpenCV
    (local webcam or IP Webcam stream). The returned bounding boxes use
    the same coordinate space as the original frame, so they overlay
    cleanly on the existing Hand Gesture and Mobile Vision pipelines.

Usage (standalone):
    pip install mediapipe opencv-python
    python face_detection.py

    Press Esc to quit.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import cv2
import mediapipe as mp
import numpy as np

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
    annotated_frame: np.ndarray          # BGR frame with boxes drawn
    bboxes: list[FaceBBox]               # one entry per detected face
    crops: list[np.ndarray]              # BGR crop per detected face
    # TODO: add emotion_labels: list[str] here when FER+ is integrated


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


# Module-level detector — shared by all callers in the same process.
# Re-initialise only if you need different confidence / model settings.
_detector: Optional[mp.solutions.face_detection.FaceDetection] = None


def _get_detector() -> mp.solutions.face_detection.FaceDetection:
    """Return the module-level detector, creating it on first call."""
    global _detector
    if _detector is None:
        _detector = initialize_face_detector()
    return _detector


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def detect_faces(
    frame: np.ndarray,
    detector: Optional[mp.solutions.face_detection.FaceDetection] = None,
) -> FaceDetectionResult:
    """
    Detect all faces in a BGR frame and return annotated results.

    Steps:
        1. Convert BGR → RGB for MediaPipe.
        2. Run face detection.
        3. Convert relative bounding boxes → pixel coordinates.
        4. Crop each face from the original frame.
        5. Draw boxes + confidence scores on an annotated copy.

    Args:
        frame:    BGR image as a NumPy array (from cv2.VideoCapture.read()).
        detector: Optional pre-created detector. Uses the module-level
                  singleton when omitted.

    Returns:
        FaceDetectionResult with annotated_frame, bboxes, and crops.
    """
    if detector is None:
        detector = _get_detector()

    h, w = frame.shape[:2]
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # MediaPipe requires the image to be marked non-writeable for performance.
    rgb.flags.writeable = False
    results = detector.process(rgb)
    rgb.flags.writeable = True

    bboxes: list[FaceBBox] = []
    crops:  list[np.ndarray] = []

    if results.detections:
        for detection in results.detections:
            bbox = _relative_bbox_to_pixels(detection, w, h)
            bboxes.append(bbox)
            crops.append(crop_face(frame, bbox))

    annotated = draw_face_boxes(frame, bboxes)

    # TODO: When integrating FER+ ONNX inference, add a loop here:
    #   emotion_labels = []
    #   for crop in crops:
    #       preprocessed = preprocess(crop)          # TODO: implement preprocess()
    #       emotion = run_fer_inference(preprocessed) # TODO: implement run_fer_inference()
    #       emotion_labels.append(emotion)
    #   Store emotion_labels in FaceDetectionResult and overlay on annotated.

    return FaceDetectionResult(
        annotated_frame=annotated,
        bboxes=bboxes,
        crops=crops,
    )


def crop_face(frame: np.ndarray, bbox: FaceBBox) -> np.ndarray:
    """
    Crop a single face from the frame using its bounding box.

    Applies CROP_PADDING on all sides and clamps to image boundaries so
    the crop is always valid regardless of edge-touching detections.

    The returned crop is a fresh NumPy array in BGR format — it is
    independent of the source frame and safe to store or pass downstream.

    Args:
        frame: Original BGR frame.
        bbox:  Pixel-space bounding box for the face.

    Returns:
        BGR crop as a NumPy array, ready for future preprocessing.

        # TODO: preprocess() will resize, convert to grayscale, and
        #       normalise this crop before passing it to the FER+ ONNX model.
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
) -> np.ndarray:
    """
    Draw bounding boxes and confidence scores onto a copy of the frame.

    Each box is labelled "Face: 0.XX" above the top-left corner,
    matching the overlay style used in hand_gesture_camera.py.

    Args:
        frame:  BGR frame (not modified in place).
        bboxes: List of FaceBBox objects from detect_faces().

    Returns:
        Annotated BGR frame (new array — original is untouched).

        # TODO: After FER+ integration, also overlay the emotion label
        #       above each bounding box here.
    """
    annotated = frame.copy()

    for bbox in bboxes:
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
        label_y = max(bbox.y - 8, 15)  # stay within frame top edge
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

        # TODO: Draw emotion label above the confidence score here once
        #       FER+ ONNX inference is integrated:
        #   cv2.putText(annotated, emotion_label, (bbox.x, label_y - 20), ...)

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
    Standalone demo: open a webcam, run face detection, display results.

    Press Esc to quit.
    """
    cap = cv2.VideoCapture(CAMERA_SOURCE)
    if not cap.isOpened():
        raise RuntimeError(
            f"Could not open camera source '{CAMERA_SOURCE}'. "
            "Check the CAMERA_SOURCE variable at the top of this file."
        )

    # Reduce buffer size to 1 to always process the latest frame —
    # critical for real-time performance over IP Webcam streams.
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    detector = initialize_face_detector()
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

        cv2.imshow("Silent Voice — Face Detection", result.annotated_frame)

        # Optionally display the first cropped face in a separate window
        if result.crops:
            cv2.imshow("Silent Voice — Face Crop [0]", result.crops[0])

        if cv2.waitKey(1) & 0xFF == 27:  # Esc
            break

    cap.release()
    cv2.destroyAllWindows()
    print("[Face Detection] Stopped.")


if __name__ == "__main__":
    main()
