"""Face preprocessing: detect, crop, align faces from images."""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def has_human_face(image_path: Path) -> bool:
    """Quick check if image contains a human face."""
    img = cv2.imread(str(image_path))
    if img is None:
        return False
    return _detect_face_mediapipe(img) is not None or _detect_face_opencv(img) is not None


def detect_and_crop_face(
    image_path: Path,
    output_path: Path,
    target_size: int = 256,
    padding_ratio: float = 0.3,
) -> Path:
    """Detect face in image, crop with padding, resize to target size.

    Parameters
    ----------
    image_path : Path
        Input image with a face.
    output_path : Path
        Where to save the cropped face image.
    target_size : int
        Output image size (square).
    padding_ratio : float
        Extra padding around detected face bbox (0.3 = 30%).

    Returns
    -------
    Path
        Path to cropped face image.
    """
    image_path = Path(image_path)
    output_path = Path(output_path)

    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError(f"Cannot read image: {image_path}")

    h, w = img.shape[:2]

    # Try MediaPipe face detection first
    face_bbox = _detect_face_mediapipe(img)

    if face_bbox is None:
        # Fallback: use OpenCV Haar cascade
        face_bbox = _detect_face_opencv(img)

    if face_bbox is None:
        # No face detected — use center crop as last resort
        logger.warning("No face detected in %s, using center crop", image_path)
        face_bbox = _center_crop_bbox(w, h)

    # Add padding
    x, y, fw, fh = face_bbox
    pad_w = int(fw * padding_ratio)
    pad_h = int(fh * padding_ratio)

    x1 = max(0, x - pad_w)
    y1 = max(0, y - pad_h)
    x2 = min(w, x + fw + pad_w)
    y2 = min(h, y + fh + pad_h)

    # Make square
    crop_w = x2 - x1
    crop_h = y2 - y1
    size = max(crop_w, crop_h)

    # Center the square crop
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2
    x1 = max(0, cx - size // 2)
    y1 = max(0, cy - size // 2)
    x2 = min(w, x1 + size)
    y2 = min(h, y1 + size)

    cropped = img[y1:y2, x1:x2]
    resized = cv2.resize(cropped, (target_size, target_size), interpolation=cv2.INTER_LANCZOS4)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), resized)

    logger.info(
        "Face cropped: %s -> %s (bbox: %d,%d,%d,%d -> %dx%d)",
        image_path.name, output_path.name, x1, y1, x2, y2, target_size, target_size,
    )
    return output_path


def _detect_face_mediapipe(img: np.ndarray) -> tuple[int, int, int, int] | None:
    """Detect face using MediaPipe Face Detection."""
    try:
        import mediapipe as mp

        with mp.solutions.face_detection.FaceDetection(
            model_selection=1, min_detection_confidence=0.5
        ) as detector:
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            results = detector.process(rgb)

            if not results.detections:
                return None

            detection = results.detections[0]
            bbox = detection.location_data.relative_bounding_box
            h, w = img.shape[:2]

            return (
                int(bbox.xmin * w),
                int(bbox.ymin * h),
                int(bbox.width * w),
                int(bbox.height * h),
            )
    except ImportError:
        logger.debug("MediaPipe not available, skipping")
        return None
    except Exception as e:
        logger.debug("MediaPipe detection failed: %s", e)
        return None


def _detect_face_opencv(img: np.ndarray) -> tuple[int, int, int, int] | None:
    """Fallback face detection using OpenCV Haar cascade."""
    try:
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        cascade = cv2.CascadeClassifier(cascade_path)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, 1.1, 4, minSize=(50, 50))

        if len(faces) == 0:
            return None

        # Return largest face (convert numpy int to Python int)
        faces_sorted = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
        x, y, w, h = faces_sorted[0]
        return (int(x), int(y), int(w), int(h))
    except Exception as e:
        logger.debug("OpenCV face detection failed: %s", e)
        return None


def _center_crop_bbox(w: int, h: int) -> tuple[int, int, int, int]:
    """Generate a center crop bounding box."""
    size = min(w, h)
    x = (w - size) // 2
    y = (h - size) // 2
    return (x, y, size, size)
