import os
import json
import uuid
import cv2
import glob
import numpy as np
from typing import List

class Preprocessor:
    def __init__(self, session_id: str = None, base_dir: str = "datasets"):
        self.session_id = session_id or str(uuid.uuid4())
        self.session_dir = os.path.join(base_dir, self.session_id)
        
        self.images_dir = os.path.join(self.session_dir, "images")
        self.sparse_dir = os.path.join(self.session_dir, "sparse")
        self.dense_dir = os.path.join(self.session_dir, "dense")
        
        self._create_directories()
        
    def _create_directories(self):
        for directory in [self.images_dir, self.sparse_dir, self.dense_dir]:
            os.makedirs(directory, exist_ok=True)
            
    def compute_blur_score(self, img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    def compute_texture_score(self, img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return float(np.std(gray))

    def apply_unsharp_mask(self, img):
        blurred = cv2.GaussianBlur(img, (5, 5), 1.0)
        sharpened = 2.0 * img - 1.0 * blurred
        return np.clip(sharpened, 0, 255).astype(np.uint8)

    def validate_and_resize(self, filepath: str, mode: str):
        img = cv2.imread(filepath)
        if img is None:
            return None, "corrupted"
            
        h, w = img.shape[:2]
        
        # Downscale logic based on mode
        if mode == "rtx3050_safe":
            max_size = 640
        elif mode == "fast":
            max_size = 800
        elif mode == "balanced":
            max_size = 1280
        else:
            max_size = 1920
            
        if max(h, w) > max_size:
            scale = max_size / max(h, w)
            new_w, new_h = int(w * scale), int(h * scale)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

        # Dataset Quality Checks (Just calculate scores, don't reject)
        blur_score = self.compute_blur_score(img)
        texture_score = self.compute_texture_score(img)

        # Apply Sharpening
        img = self.apply_unsharp_mask(img)
            
        return img, {"blur": blur_score, "texture": texture_score}

    def normalize_dataset(self, mode: str = "high") -> dict:
        raw_dir = os.path.join(self.session_dir, "raw_uploads")
        if not os.path.exists(raw_dir):
            raise Exception("raw_uploads directory does not exist.")
            
        supported_exts = ["*.jpg", "*.jpeg", "*.png"]
        files = []
        for ext in supported_exts:
            files.extend(glob.glob(os.path.join(raw_dir, ext)))
            files.extend(glob.glob(os.path.join(raw_dir, ext.upper())))
            
        files = sorted(list(set(files)))
        
        # Pre-evaluate images if RTX3050 safe mode requires truncation
        evaluations = []
        rejected_count = 0
        reasons = {}
        
        for filepath in files:
            img, result = self.validate_and_resize(filepath, mode)
            if img is not None:
                evaluations.append({
                    "filepath": filepath,
                    "img": img,
                    "blur": result["blur"],
                    "texture": result["texture"]
                })
            else:
                rejected_count += 1
                reason = result.split(" ")[0]
                reasons[reason] = reasons.get(reason, 0) + 1

        truncation_count = 0
        if mode == "rtx3050_safe" and len(evaluations) > 30:
            evaluations.sort(key=lambda x: x["blur"], reverse=True) # Sharpest first
            truncation_count = len(evaluations) - 30
            rejected_count += truncation_count
            reasons["truncated_vram"] = truncation_count
            evaluations = evaluations[:30]

        accepted_count = 0
        total_blur = 0
        total_texture = 0
        
        jpeg_quality = 85 if mode == "rtx3050_safe" else 95
        
        for eval_data in evaluations:
            out_filename = f"image_{accepted_count:04d}.jpg"
            out_path = os.path.join(self.images_dir, out_filename)
            cv2.imwrite(out_path, eval_data["img"], [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
            accepted_count += 1
            total_blur += eval_data["blur"]
            total_texture += eval_data["texture"]
            
        # Scene Health Score (0-100)
        health_score = 0
        if accepted_count > 0:
            avg_blur = total_blur / accepted_count
            avg_texture = total_texture / accepted_count
            health_score = min(100, int((avg_blur / 150) * 50 + (avg_texture / 50) * 50))
                
        metadata = {
            "session_id": self.session_id,
            "total_uploads": len(files),
            "accepted_count": accepted_count,
            "rejected_count": rejected_count,
            "rejection_reasons": reasons,
            "health_score": health_score,
            "mode": mode,
            "status": "preprocessed",
            "image_truncation_count": truncation_count
        }
        
        with open(os.path.join(self.session_dir, "metadata.json"), "w") as f:
            json.dump(metadata, f, indent=4)
            
        return metadata
