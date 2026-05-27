import os
import json
import uuid
import cv2
import glob
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
            
    def validate_and_resize(self, filepath: str, max_size: int = 1600):
        """
        Validates if an image is readable and resizes it if it exceeds max_size,
        preserving aspect ratio. Returns the processed image matrix or None if invalid.
        """
        img = cv2.imread(filepath)
        if img is None:
            return None
            
        h, w = img.shape[:2]
        if max(h, w) > max_size:
            scale = max_size / max(h, w)
            new_w, new_h = int(w * scale), int(h * scale)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
            
        return img

    def normalize_dataset(self) -> dict:
        """
        Normalizes all raw uploaded images inside datasets/{session_id}/raw_uploads/
        into sequential filenames inside datasets/{session_id}/images/
        Generates and saves metadata.json.
        """
        raw_dir = os.path.join(self.session_dir, "raw_uploads")
        if not os.path.exists(raw_dir):
            raise Exception("raw_uploads directory does not exist.")
            
        supported_exts = ["*.jpg", "*.jpeg", "*.png"]
        files = []
        for ext in supported_exts:
            files.extend(glob.glob(os.path.join(raw_dir, ext)))
            files.extend(glob.glob(os.path.join(raw_dir, ext.upper())))
            
        files = sorted(list(set(files)))
        
        accepted_count = 0
        rejected_count = 0
        
        for filepath in files:
            img = self.validate_and_resize(filepath)
            if img is not None:
                out_filename = f"image_{accepted_count:04d}.jpg"
                out_path = os.path.join(self.images_dir, out_filename)
                cv2.imwrite(out_path, img, [cv2.IMWRITE_JPEG_QUALITY, 95])
                accepted_count += 1
            else:
                rejected_count += 1
                
        metadata = {
            "session_id": self.session_id,
            "total_uploads": len(files),
            "accepted_count": accepted_count,
            "rejected_count": rejected_count,
            "status": "preprocessed"
        }
        
        with open(os.path.join(self.session_dir, "metadata.json"), "w") as f:
            json.dump(metadata, f, indent=4)
            
        return metadata
