import torch

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

IMAGE_HEIGHT = 192
IMAGE_WIDTH = 192

N_SAMPLES_COARSE = 32
N_SAMPLES_FINE = 32

DIR_FREQS = 4

# Hash Grid Config
HASH_NUM_LEVELS = 8
HASH_LEVEL_DIM = 2
HASH_LOG2_SIZE = 13
HASH_BASE_RES = 16
HASH_MAX_RES = 1024

# Occupancy Grid Config
OCC_GRID_RES = 48
OCC_THRESHOLD = 0.01
OCC_DECAY = 0.95
OCC_UPDATE_EVERY = 5
OCC_WARMUP_EPOCHS = 25

# Dynamic Chunking Config
TARGET_ACTIVE_SAMPLES = 65536
MAX_RAYS_PER_BATCH = 8192

# Tiny MLP Config
HIDDEN_DIM = 64

LEARNING_RATE = 1e-4
EPOCHS = 150 # Deep benchmark validation
TRAIN_VIEWS = 20

RAYS_PER_BATCH = 2048 # Base fallback, dynamically scales up
CHUNK_SIZE = 4096

NEAR = 2.0
FAR = 6.0

CHECKPOINT_EVERY = 25

NOVEL_VIEW_RADIUS = 4.0
NOVEL_VIEW_THETA = 30.0
NOVEL_VIEW_PHI = -30.0

VIDEO_FRAMES = 24

# ----------------------------------------
# STAGE 3/4: Ingestion Pipeline Config
# ----------------------------------------
SESSION_BASE_DIR = "sessions"
SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png"}

MIN_UPLOADS = 5
MAX_UPLOADS = 300

MAX_TOTAL_UPLOAD_MB = 1024 # 1 GB
MAX_SINGLE_IMAGE_MB = 25   # 25 MB

# Preprocessing
TARGET_PROC_RES = (512, 512)
PADDING_COLOR = (0, 0, 0) # Neutral black padding
BLUR_THRESHOLD = 50.0      # Laplacian variance threshold for blur rejection
PHASH_HASH_SIZE = 8       # Perceptual hash sizing
PHASH_THRESHOLD = 5       # Hamming distance threshold for duplicate rejection

# ----------------------------------------
# Instant-NGP Configuration
# ----------------------------------------
INSTANT_NGP_PATH = r"C:\Users\Sawan\Downloads\instant-ngp-bin\Instant-NGP-for-RTX-3000-and-4000\instant-ngp.exe"