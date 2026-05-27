"""
Converts COLMAP sparse reconstruction output (cameras.bin + images.bin)
into the NeRF-compatible transforms.json format.
"""
import os
import json
import struct
import numpy as np
import collections


Camera = collections.namedtuple("Camera", ["id", "model", "width", "height", "params"])
Image = collections.namedtuple("Image", ["id", "qvec", "tvec", "camera_id", "name", "xys", "point3D_ids"])


def read_next_bytes(fid, num_bytes, format_char_sequence, endian_character="<"):
    data = fid.read(num_bytes)
    return struct.unpack(endian_character + format_char_sequence, data)


def read_cameras_binary(path_to_model_file):
    cameras = {}
    with open(path_to_model_file, "rb") as fid:
        num_cameras = read_next_bytes(fid, 8, "Q")[0]
        for _ in range(num_cameras):
            camera_properties = read_next_bytes(fid, 24, "iiQQ")
            camera_id = camera_properties[0]
            model_id = camera_properties[1]
            width = camera_properties[2]
            height = camera_properties[3]
            model_names = {0: "SIMPLE_PINHOLE", 1: "PINHOLE", 2: "SIMPLE_RADIAL", 3: "RADIAL", 4: "OPENCV"}
            model_name = model_names.get(model_id, "UNKNOWN")
            num_params = {0: 3, 1: 4, 2: 4, 3: 5, 4: 8}.get(model_id, 4)
            params = read_next_bytes(fid, 8 * num_params, "d" * num_params)
            cameras[camera_id] = Camera(
                id=camera_id, model=model_name, width=width, height=height, params=list(params)
            )
    return cameras


def read_images_binary(path_to_model_file):
    images = {}
    with open(path_to_model_file, "rb") as fid:
        num_reg_images = read_next_bytes(fid, 8, "Q")[0]
        for _ in range(num_reg_images):
            binary_image_properties = read_next_bytes(fid, 64, "idddddddi")
            image_id = binary_image_properties[0]
            qvec = binary_image_properties[1:5]
            tvec = binary_image_properties[5:8]
            camera_id = binary_image_properties[8]
            image_name = b""
            current_char = fid.read(1)
            while current_char != b"\x00":
                image_name += current_char
                current_char = fid.read(1)
            image_name = image_name.decode("utf-8")
            num_points2D = read_next_bytes(fid, 8, "Q")[0]
            x_y_id_s = read_next_bytes(fid, 24 * num_points2D, "ddq" * num_points2D)
            xys = np.column_stack([
                tuple(map(float, x_y_id_s[0::3])),
                tuple(map(float, x_y_id_s[1::3]))
            ])
            point3D_ids = [int(x) for x in x_y_id_s[2::3]]
            images[image_id] = Image(
                id=image_id, qvec=qvec, tvec=tvec, camera_id=camera_id,
                name=image_name, xys=xys, point3D_ids=point3D_ids
            )
    return images


def qvec2rotmat(qvec):
    """Convert quaternion to rotation matrix."""
    w, x, y, z = qvec
    return np.array([
        [1 - 2*y*y - 2*z*z,     2*x*y - 2*w*z,     2*x*z + 2*w*y],
        [    2*x*y + 2*w*z, 1 - 2*x*x - 2*z*z,     2*y*z - 2*w*x],
        [    2*x*z - 2*w*y,     2*y*z + 2*w*x, 1 - 2*x*x - 2*y*y]
    ])


def convert(sparse_dir: str, images_dir: str, output_path: str) -> dict:
    """
    Reads COLMAP binary output and writes transforms.json.
    Returns the parsed metadata dict.
    """
    cameras_bin = os.path.join(sparse_dir, "cameras.bin")
    images_bin = os.path.join(sparse_dir, "images.bin")

    cameras = read_cameras_binary(cameras_bin)
    images = read_images_binary(images_bin)

    # Get camera intrinsics from first camera
    cam = list(cameras.values())[0]
    W, H = cam.width, cam.height

    # SIMPLE_RADIAL or SIMPLE_PINHOLE: params = [f, cx, cy, ...]
    # PINHOLE: params = [fx, fy, cx, cy]
    if cam.model in ("SIMPLE_RADIAL", "SIMPLE_PINHOLE"):
        focal = cam.params[0]
    elif cam.model in ("PINHOLE", "OPENCV"):
        focal = (cam.params[0] + cam.params[1]) / 2
    else:
        focal = cam.params[0]

    camera_angle_x = 2.0 * np.arctan(W / (2.0 * focal))

    frames = []
    for img in images.values():
        R = qvec2rotmat(img.qvec)
        t = np.array(img.tvec)

        # COLMAP gives world-to-camera. Invert to camera-to-world (c2w).
        w2c = np.eye(4)
        w2c[:3, :3] = R
        w2c[:3, 3] = t
        c2w = np.linalg.inv(w2c)

        # NeRF convention: flip Y and Z axes
        c2w[0:3, 1] *= -1
        c2w[0:3, 2] *= -1

        # Store absolute path so subprocess can locate images regardless of CWD
        abs_image_path = os.path.abspath(os.path.join(images_dir, img.name))

        frames.append({
            "file_path": abs_image_path.replace("\\", "/"),
            "transform_matrix": c2w.tolist()
        })

    transforms = {
        "camera_angle_x": float(camera_angle_x),
        "w": int(W),
        "h": int(H),
        "fl_x": float(focal),
        "fl_y": float(focal),
        "cx": float(cam.params[1]) if len(cam.params) > 1 else W / 2,
        "cy": float(cam.params[2]) if len(cam.params) > 2 else H / 2,
        "frames": frames
    }

    with open(output_path, "w") as f:
        json.dump(transforms, f, indent=2)

    return transforms
