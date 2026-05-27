import cv2
import numpy as np
from typing import Tuple

import config


def compute_blur_score(image: np.ndarray) -> float:
    """
    Computes the Laplacian variance of the image.
    Lower score means more blurry.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    variance = cv2.Laplacian(gray, cv2.CV_64F).var()
    return float(variance)


def compute_phash(image: np.ndarray) -> np.ndarray:
    """
    Computes a simple difference hash (dHash) for lightweight perceptual deduplication.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    hash_size = config.PHASH_HASH_SIZE
    # Resize to (hash_size + 1, hash_size) to compute adjacent column differences
    resized = cv2.resize(gray, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    diff = resized[:, 1:] > resized[:, :-1]
    return diff.flatten()


def hamming_distance(hash1: np.ndarray, hash2: np.ndarray) -> int:
    return np.count_nonzero(hash1 != hash2)


def resize_and_pad(image: np.ndarray, target_res: Tuple[int, int], pad_color: Tuple[int, int, int]) -> np.ndarray:
    """
    Resizes the image to fit within target_res while preserving aspect ratio,
    then pads the rest of the image with pad_color to exactly match target_res.
    """
    h, w = image.shape[:2]
    target_w, target_h = target_res

    scale = min(target_w / w, target_h / h)
    new_w = int(w * scale)
    new_h = int(h * scale)

    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)

    top = (target_h - new_h) // 2
    bottom = target_h - new_h - top
    left = (target_w - new_w) // 2
    right = target_w - new_w - left

    padded = cv2.copyMakeBorder(
        resized,
        top, bottom, left, right,
        cv2.BORDER_CONSTANT,
        value=pad_color
    )

    return padded


def process_image(filepath: str, target_res: Tuple[int, int]) -> dict:
    """
    Reads, evaluates, and processes an image.
    Returns a dict with 'status' (success/rejected), 'reason', 'image' (if successful), and 'hash'.
    """
    image = cv2.imread(filepath)
    if image is None:
        return {"status": "rejected", "reason": "corrupted or invalid format"}

    # Blur detection
    blur_score = compute_blur_score(image)
    if blur_score < config.BLUR_THRESHOLD:
        return {"status": "rejected", "reason": f"blurry (score: {blur_score:.2f})"}

    # Resize and pad
    processed = resize_and_pad(image, target_res, config.PADDING_COLOR)
    
    # Compute perceptual hash on the processed image
    phash = compute_phash(processed)

    return {
        "status": "success",
        "image": processed,
        "hash": phash,
        "blur_score": blur_score
    }
