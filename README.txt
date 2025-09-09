AI Background Remover

Overview
- Simple web app to remove image backgrounds using CarveKit + PyTorch.
- GPU-accelerated by default (CUDA). Falls back to CPU if no GPU.
- Includes presets and quality controls (trimap, feather, alpha threshold) and batches images for speed.

Quick Start (Docker Compose)
Prerequisites
- Docker 24+
- NVIDIA drivers (for GPU) and nvidia-container-toolkit (https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)

Run
1) Build and start services:
   docker-compose up --build

2) Open the app:
   http://localhost:5001

Notes
- The Flask backend serves the UI directly (index.html/script.js/style.css) and the API.
- Health: GET /health
- Info:   GET /info (shows device/GPU, Torch, FP16, PNG level)

Environment Variables (docker-compose.yml)
- MAX_UPLOAD_SIZE_MB: Max upload size in MB (default 10).
- PROCESSED_DIR: Output directory for processed images (default processed).
- STATIC_DIR: Static files directory (default .).
- PORT: Flask port (default 5001).
- FP16: Set to "auto" (default), "1" to force on, or "0" to disable.
- PNG_COMPRESS_LEVEL: PNG compression level 0-9 (default 6).
- INTERFACE_CACHE_SIZE: Cache of model interfaces for preset switching (default 4).
- WARMUP: Set to 1 to run a dummy inference at startup.

Manual Docker (without compose)
1) Build image:
   docker build -t ai-background-remover .

2) Run with GPU (preferred):
   docker run --rm -it \
     --gpus all \
     -p 5001:5001 \
     -e MAX_UPLOAD_SIZE_MB=10 \
     -e PROCESSED_DIR=processed \
     -e STATIC_DIR=. \
     -e FP16=auto \
     -v $(pwd)/processed:/app/processed \
     ai-background-remover

3) Run without GPU (CPU only):
   docker run --rm -it -p 5001:5001 ai-background-remover

Local (no Docker)
1) Python 3.10+ recommended. Install dependencies:
   pip install -r requirements.txt

2) Run:
   python app.py

3) Open http://localhost:5001

Project Structure
- app.py            Flask server + background removal endpoints
- index.html        UI
- script.js         Client logic, presets, and API calls
- style.css         Styling
- Dockerfile        Container for GPU/CPU runtime
- docker-compose.yml Compose file with GPU enabled service
- processed/        Output images (mounted to host in compose)

Troubleshooting
- GPU not used: Ensure NVIDIA drivers + nvidia-container-toolkit installed; check /info endpoint.
- First run slow: Set WARMUP=1 to pre-initialize at container start.
- Large files: Increase MAX_UPLOAD_SIZE_MB and check browser/devtools for errors.

