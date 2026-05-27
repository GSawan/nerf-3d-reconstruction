import os
import json
import uuid
import glob
from typing import List, Dict
import cv2

import config
from utils.ingest.preprocess import process_image, hamming_distance
from utils.ingest.camera import generate_synthetic_transforms
from utils.ingest.normalize import normalize_scene


class IngestionError(Exception):
    pass

class InsufficientImagesError(IngestionError):
    pass

class UnsupportedFormatError(IngestionError):
    pass


class SessionManager:
    def __init__(self, session_id: str = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.base_dir = os.path.join(config.SESSION_BASE_DIR, self.session_id)
        
        self.raw_dir = os.path.join(self.base_dir, "raw")
        self.processed_dir = os.path.join(self.base_dir, "processed")
        self.outputs_dir = os.path.join(self.base_dir, "outputs")
        self.metadata_dir = os.path.join(self.base_dir, "metadata")
        
        self._create_directories()

    def _create_directories(self):
        for directory in [self.raw_dir, self.processed_dir, self.outputs_dir, self.metadata_dir]:
            os.makedirs(directory, exist_ok=True)

    def _get_supported_files(self, source_dir: str) -> List[str]:
        files = []
        for ext in config.SUPPORTED_FORMATS:
            files.extend(glob.glob(os.path.join(source_dir, f"*{ext}")))
            # Handle uppercase extensions
            files.extend(glob.glob(os.path.join(source_dir, f"*{ext.upper()}")))
            
        # Deterministic sort to ensure consistent camera assignments later
        files = sorted(list(set(files)))
        return files

    def run_pipeline(self, upload_dir: str):
        """
        Runs the complete ingestion pipeline: preprocessing, deduplication, 
        camera pose generation, and normalization.
        """
        print(f"Starting pipeline for session: {self.session_id}")
        
        files = self._get_supported_files(upload_dir)
        total_uploads = len(files)
        
        if total_uploads < config.MIN_UPLOADS:
            raise InsufficientImagesError(
                f"Found {total_uploads} valid images. Minimum required is {config.MIN_UPLOADS}."
            )
            
        if total_uploads > config.MAX_UPLOADS:
            # We can softly truncate or strictly raise. We choose strict.
            raise IngestionError(f"Exceeded max uploads ({config.MAX_UPLOADS}).")
            
        accepted_count = 0
        rejected_count = 0
        deduplicated_count = 0
        rejection_reasons = {}
        
        accepted_hashes = []
        
        # Process each image
        for i, filepath in enumerate(files):
            result = process_image(filepath, config.TARGET_PROC_RES)
            
            if result["status"] == "rejected":
                reason = result["reason"]
                rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
                rejected_count += 1
                continue
                
            # Duplicate check
            phash = result["hash"]
            is_duplicate = False
            for existing_hash in accepted_hashes:
                if hamming_distance(phash, existing_hash) <= config.PHASH_THRESHOLD:
                    is_duplicate = True
                    break
                    
            if is_duplicate:
                deduplicated_count += 1
                rejected_count += 1
                rejection_reasons["duplicate"] = rejection_reasons.get("duplicate", 0) + 1
                continue
                
            # Save accepted
            accepted_hashes.append(phash)
            # Standardized naming
            out_filename = f"train_{accepted_count:04d}.png"
            out_path = os.path.join(self.processed_dir, out_filename)
            cv2.imwrite(out_path, result["image"])
            accepted_count += 1

        # Compile and save session metadata
        metadata = {
            "session_id": self.session_id,
            "total_uploads": total_uploads,
            "accepted_count": accepted_count,
            "rejected_count": rejected_count,
            "deduplicated_count": deduplicated_count,
            "rejection_reasons": rejection_reasons,
            "preprocessing_resolution": config.TARGET_PROC_RES,
            "aabb_scale": 1.0
        }

        if accepted_count < config.MIN_UPLOADS:
            meta_path = os.path.join(self.metadata_dir, "session_metadata.json")
            with open(meta_path, "w") as f:
                json.dump(metadata, f, indent=4)
            raise InsufficientImagesError(
                f"Only {accepted_count} images survived preprocessing. Minimum is {config.MIN_UPLOADS}. Metadata: {metadata}"
            )

        # Generate Camera Poses
        transforms = generate_synthetic_transforms(accepted_count)
        
        # Normalize Scene
        normalized_transforms = normalize_scene(transforms)
        metadata["aabb_scale"] = normalized_transforms.get("aabb_scale", 1.0)
        
        # Save Transforms
        transforms_path = os.path.join(self.base_dir, "transforms.json")
        with open(transforms_path, "w") as f:
            json.dump(normalized_transforms, f, indent=4)
            
        meta_path = os.path.join(self.metadata_dir, "session_metadata.json")
        with open(meta_path, "w") as f:
            json.dump(metadata, f, indent=4)
            
        print(f"Pipeline complete! {accepted_count} images ready for reconstruction.")
        return metadata
