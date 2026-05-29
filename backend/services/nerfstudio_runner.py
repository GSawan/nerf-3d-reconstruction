import os
import subprocess
import threading
import json
import logging
import torch

def run_ns_process_data(session_id: str, images_dir: str, output_dir: str, update_state_cb):
    """
    Runs ns-process-data images to generate COLMAP and transforms.json
    """
    update_state_cb(session_id, "transforms_generation", 10, "Running ns-process-data to estimate camera poses...")
    
    # Run inside the Conda environment
    conda_python = os.path.join("C:\\Users\\Sawan\\miniconda3\\envs\\nerfstudio\\python.exe")
    
    colmap_model_path = os.path.join("..", "sparse", "0")
    
    cmd = [
        conda_python, "-m", "nerfstudio.scripts.process_data", "images",
        "--data", images_dir,
        "--output-dir", output_dir,
        "--skip-colmap",
        "--colmap-model-path", colmap_model_path
    ]
    
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["TERM"] = "dumb"
    

    
    try:
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True, 
            encoding="utf-8", 
            errors="ignore",
            env=env
        )
        for line in iter(process.stdout.readline, ''):
            line = line.strip()
            if not line:
                continue
            update_state_cb(session_id, "transforms_generation", 50, f"[ns-process-data] {line}")
            
        process.wait()
        if process.returncode != 0:
            raise Exception(f"ns-process-data failed with code {process.returncode}")
            
        update_state_cb(session_id, "transforms_generation", 100, "Camera poses estimated successfully.")
        return True
    except Exception as e:
        update_state_cb(session_id, "failed", 0, str(e), error="ns-process-data failed")
        return False

def run_ns_train(session_id: str, data_dir: str, update_state_cb):
    """
    Runs ns-train splatfacto
    """
    # Pre-flight check: Is CUDA available?
    if not torch.cuda.is_available():
        raise Exception("CUDA is not available. GPU is required to train Splatfacto.")

    update_state_cb(session_id, "ngp_training", 0, "Starting ns-train splatfacto...")
    
    conda_python = os.path.join("C:\\Users\\Sawan\\miniconda3\\envs\\nerfstudio\\python.exe")
    
    # Pre-flight flag validation
    update_state_cb(session_id, "ngp_training", 1, "Validating Nerfstudio CLI arguments...")
    help_cmd = [conda_python, "-m", "nerfstudio.scripts.train", "splatfacto", "--help"]
    try:
        help_output = subprocess.run(help_cmd, capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError as e:
        help_output = e.stdout + e.stderr
    
    # Write a wrapper script to fix DLL loading for gsplat_cuda on Windows Python >= 3.8
    wrapper_script = os.path.join(data_dir, "run_ns_train.py")
    with open(wrapper_script, "w") as f:
        f.write("import os\n")
        f.write("if hasattr(os, 'add_dll_directory'):\n")
        f.write("    try: os.add_dll_directory(r'C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v11.8\\bin')\n")
        f.write("    except Exception: pass\n")
        f.write("    try: os.add_dll_directory(r'C:\\Users\\Sawan\\miniconda3\\envs\\nerfstudio\\Library\\bin')\n")
        f.write("    except Exception: pass\n")
        f.write("import runpy\n")
        f.write("runpy.run_module('nerfstudio.scripts.train', run_name='__main__')\n")
        
    cmd = [
        conda_python, wrapper_script, "splatfacto",
        "--data", data_dir,
        "--vis", "viewer",
        "--viewer.websocket-port", "7007"
    ]
    
    # Conditionally inject RTX 3050 Mitigations if supported by this NS version
    if "--pipeline.model.cull-alpha-thresh" in help_output:
        cmd.extend(["--pipeline.model.cull-alpha-thresh", "0.01"])
        
    if "--pipeline.model.continue-cull-post-densification" in help_output:
        cmd.extend(["--pipeline.model.continue-cull-post-densification", "False"])
        
    # Handle camera optimizer mode drift between versions
    if "--pipeline.model.camera-optimizer.mode" in help_output:
        cmd.extend(["--pipeline.model.camera-optimizer.mode", "off"])
    elif "--pipeline.datamanager.camera-optimizer.mode" in help_output:
        cmd.extend(["--pipeline.datamanager.camera-optimizer.mode", "off"])
    
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["TERM"] = "dumb"
    env["TORCH_NVCC_FLAGS"] = "-allow-unsupported-compiler -D__NV_NO_HOST_COMPILER_CHECK=1"
    env["CFLAGS"] = "/D__NV_NO_HOST_COMPILER_CHECK=1"
    env["CXXFLAGS"] = "/D__NV_NO_HOST_COMPILER_CHECK=1"
    
    # Inject Conda into PATH so ninja and nvcc are found by PyTorch JIT
    conda_prefix = "C:\\Users\\Sawan\\miniconda3\\envs\\nerfstudio"
    conda_scripts = os.path.join(conda_prefix, "Scripts")
    conda_bin = os.path.join(conda_prefix, "Library", "bin")
    env["PATH"] = f"{conda_scripts};{conda_bin};{conda_prefix};{env.get('PATH', '')}"
    
    try:
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True,
            encoding="utf-8",
            errors="ignore",
            env=env
        )
        
        def monitor_stdout():
            for line in iter(process.stdout.readline, ''):
                line = line.strip()
                if not line:
                    continue
                
                # Parse progress
                if "(Iter" in line and "Loss:" in line:
                    try:
                        iter_part = line.split("(Iter ")[1].split(")")[0]
                        current_iter, total_iter = map(int, iter_part.split("/"))
                        progress = int((current_iter / total_iter) * 100)
                        
                        loss_part = line.split("Loss: ")[1].split(" ")[0]
                        loss = float(loss_part)
                        
                        update_state_cb(session_id, "ngp_training", progress, f"Training Splatfacto: Iteration {current_iter}/{total_iter}", loss=loss)
                    except Exception:
                        update_state_cb(session_id, "ngp_training", -1, f"[ns-train] {line}")
                elif "Viewer at:" in line:
                    update_state_cb(session_id, "viewer_ready", -1, f"VIEWER_READY: {line}")
                elif "CUDA out of memory" in line or "OOM" in line:
                    update_state_cb(session_id, "ngp_training", -1, f"[CRITICAL] GPU Out of Memory: {line}")
                else:
                    update_state_cb(session_id, "ngp_training", -1, f"[ns-train] {line}")
                    
        thread = threading.Thread(target=monitor_stdout, daemon=True)
        thread.start()
        
        return process
    except Exception as e:
        update_state_cb(session_id, "failed", 0, str(e), error="ns-train failed")
        return None
