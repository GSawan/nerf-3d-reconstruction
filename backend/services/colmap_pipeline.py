import os
import subprocess
import logging

# Resolve COLMAP executable — use env var if set, else known install path
_DEFAULT_COLMAP = r"C:\Users\Sawan\Downloads\COLMAP\COLMAP.bat"
COLMAP_EXE = os.environ.get("COLMAP_PATH", _DEFAULT_COLMAP)

class ColmapPipeline:
    def __init__(self, session_dir: str):
        self.session_dir = session_dir
        self.images_dir = os.path.join(session_dir, "images")
        self.sparse_dir = os.path.join(session_dir, "sparse")
        self.dense_dir = os.path.join(session_dir, "dense")
        self.database_path = os.path.join(session_dir, "database.db")
        
        # Ensure directories exist
        os.makedirs(self.sparse_dir, exist_ok=True)
        os.makedirs(self.dense_dir, exist_ok=True)
        
    def _run_command(self, command: str, step_name: str, ):
        """Helper to run a COLMAP command and capture output."""
        logging.info(f"Starting COLMAP step: {step_name}")
        logging.info(f"Command: {command}")
        
        try:
            # We use shell=True because on Windows, 'colmap' might be resolved via COLMAP.bat
            result = subprocess.run(
                command, 
                shell=True,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=14400  # 4 hour timeout per step to prevent stuck worker
            )
            logging.info(f"{step_name} completed successfully.")
            return result.stdout
        except subprocess.TimeoutExpired as e:
            logging.error(f"{step_name} timed out after 30 minutes.")
            raise Exception(f"COLMAP {step_name} timed out after 30 minutes")
        except subprocess.CalledProcessError as e:
            logging.error(f"{step_name} failed with error code {e.returncode}")
            logging.error(f"STDOUT: {e.stdout}")
            logging.error(f"STDERR: {e.stderr}")
            raise Exception(f"COLMAP {step_name} failed: {e.stderr}")

    def extract_features(self):
        """Runs the COLMAP feature extractor."""
        cmd = (
            f'"{COLMAP_EXE}" feature_extractor '
            f"--database_path \"{self.database_path}\" "
            f"--image_path \"{self.images_dir}\" "
            f"--ImageReader.camera_model SIMPLE_RADIAL "
            f"--ImageReader.single_camera 1 "
            f"--SiftExtraction.estimate_affine_shape 1 "
            f"--SiftExtraction.domain_size_pooling 1 "
            f"--FeatureExtraction.use_gpu 1"
        )
        self._run_command(cmd, "feature_extractor")

    def match_features(self):
        """Matches extracted features across images."""
        cmd = (
            f'"{COLMAP_EXE}" exhaustive_matcher '
            f"--database_path \"{self.database_path}\" "
            f"--SiftMatching.max_ratio 0.9 "
            f"--FeatureMatching.use_gpu 1"
        )
        self._run_command(cmd, "exhaustive_matcher")

    def reconstruct_sparse(self):
        """Runs the COLMAP mapper for sparse 3D reconstruction."""
        cmd = (
            f'"{COLMAP_EXE}" mapper '
            f"--database_path \"{self.database_path}\" "
            f"--image_path \"{self.images_dir}\" "
            f"--output_path \"{self.sparse_dir}\""
        )
        self._run_command(cmd, "mapper")
        
    def export_sparse_ply(self):
        """Converts the sparse/0 reconstruction into a PLY file for the web viewer."""
        sparse_zero_dir = os.path.join(self.sparse_dir, "0")
        ply_output_path = os.path.join(sparse_zero_dir, "sparse.ply")
        if not os.path.exists(sparse_zero_dir):
            logging.warning("Sparse directory 0 does not exist. Skipping PLY export.")
            return None
            
        cmd = (
            f'"{COLMAP_EXE}" model_converter '
            f"--input_path \"{sparse_zero_dir}\" "
            f"--output_path \"{ply_output_path}\" "
            f"--output_type PLY"
        )
        self._run_command(cmd, "model_converter_ply")
        return ply_output_path
        
    def export_sparse_txt(self):
        """Converts the sparse/0 reconstruction into TXT format for Gaussian splat parsing."""
        sparse_zero_dir = os.path.join(self.sparse_dir, "0")
        txt_output_path = os.path.join(self.sparse_dir, "txt")
        if not os.path.exists(sparse_zero_dir):
            logging.warning("Sparse directory 0 does not exist. Skipping TXT export.")
            return None
            
        os.makedirs(txt_output_path, exist_ok=True)
        cmd = (
            f'"{COLMAP_EXE}" model_converter '
            f"--input_path \"{sparse_zero_dir}\" "
            f"--output_path \"{txt_output_path}\" "
            f"--output_type TXT"
        )
        self._run_command(cmd, "model_converter_txt")
        return txt_output_path

    def undistort_images(self):
        """Prepares images for dense stereo by undistorting them."""
        sparse_zero_dir = os.path.join(self.sparse_dir, "0")
        cmd = (
            f'"{COLMAP_EXE}" image_undistorter '
            f"--image_path \"{self.images_dir}\" "
            f"--input_path \"{sparse_zero_dir}\" "
            f"--output_path \"{self.dense_dir}\" "
            f"--output_type COLMAP"
        )
        self._run_command(cmd, "image_undistorter")

    def run_patch_match(self):
        """Runs PatchMatch dense stereo to compute depth/normal maps."""
        cmd = (
            f'"{COLMAP_EXE}" patch_match_stereo '
            f"--workspace_path \"{self.dense_dir}\" "
            f"--workspace_format COLMAP "
            f"--PatchMatchStereo.geom_consistency true"
        )
        self._run_command(cmd, "patch_match_stereo")

    def run_stereo_fusion(self):
        """Fuses depth maps into a dense point cloud (fused.ply)."""
        fused_path = os.path.join(self.dense_dir, "fused.ply")
        cmd = (
            f'"{COLMAP_EXE}" stereo_fusion '
            f"--workspace_path \"{self.dense_dir}\" "
            f"--workspace_format COLMAP "
            f"--input_type geometric "
            f"--output_path \"{fused_path}\""
        )
        self._run_command(cmd, "stereo_fusion")
        return fused_path

    def generate_mesh(self):
        """Generates a 3D mesh using Poisson surface reconstruction."""
        fused_path = os.path.join(self.dense_dir, "fused.ply")
        mesh_path = os.path.join(self.dense_dir, "meshed-poisson.ply")
        if not os.path.exists(fused_path):
            logging.warning("fused.ply not found. Cannot generate mesh.")
            return None
            
        cmd = (
            f'"{COLMAP_EXE}" poisson_mesher '
            f"--input_path \"{fused_path}\" "
            f"--output_path \"{mesh_path}\" "
            f"--PoissonMeshing.depth 5"
        )
        self._run_command(cmd, "poisson_mesher")
        return mesh_path

    def analyze_model(self):
        """Runs the COLMAP model_analyzer on the sparse reconstruction."""
        sparse_zero_dir = os.path.join(self.sparse_dir, "0")
        if not os.path.exists(sparse_zero_dir):
            logging.warning("Sparse directory 0 does not exist. Cannot analyze model.")
            return None
        cmd = (
            f'"{COLMAP_EXE}" model_analyzer '
            f"--path \"{sparse_zero_dir}\""
        )
        return self._run_command(cmd, "model_analyzer")
