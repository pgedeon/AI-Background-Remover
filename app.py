import os
import time
import uuid
from io import BytesIO
from typing import List, Dict, Tuple

from flask import Flask, request, send_file, jsonify, send_from_directory, abort
from werkzeug.utils import secure_filename
import torch
from carvekit.api.high import HiInterface
from PIL import Image, UnidentifiedImageError

# Configuration
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
MAX_CONTENT_LENGTH_MB = float(os.getenv("MAX_UPLOAD_SIZE_MB", "10"))
MAX_CONTENT_LENGTH = int(MAX_CONTENT_LENGTH_MB * 1024 * 1024)  # per request
PROCESSED_DIR = os.getenv("PROCESSED_DIR", "processed")
STATIC_DIR = os.getenv("STATIC_DIR", ".")  # current project root contains index.html, script.js, style.css
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "5001"))
DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"

os.makedirs(PROCESSED_DIR, exist_ok=True)

# Default carvekit configuration
# Key parameters for fine-tuning background removal:
# - object_type: "hairs-like" (more aggressive) or "object" (less aggressive)
# - trimap_prob_threshold: Higher values make the mask more conservative (200-250)
# - trimap_dilation: Affects mask expansion (10-50)
# - trimap_erosion_iters: Affects mask erosion (1-10)
# Default configs; tuned for GPU when available
DEFAULT_CARVEKIT_CONFIG = {
    "object_type": "hairs-like",  # Can be "object" or "hairs-like"
    "batch_size_seg": int(os.getenv("BATCH_SIZE_SEG", "6")),
    "batch_size_matting": int(os.getenv("BATCH_SIZE_MATTING", "2")),
    "seg_mask_size": 640,  # Use 640 for Tracer B7
    "matting_mask_size": 2048,
    "trimap_prob_threshold": 231,
    "trimap_dilation": 30,
    "trimap_erosion_iters": 5,
    "fp16": (os.getenv("FP16", "auto").lower() == "1") or (
        os.getenv("FP16", "auto").lower() == "auto" and torch.cuda.is_available()
    ),
}

# Optional PNG compression level (0-9). 6 is a good balance.
PNG_COMPRESS_LEVEL = max(0, min(9, int(os.getenv("PNG_COMPRESS_LEVEL", "6"))))

# Enable TF32 on Ampere+ for speed if available
try:
    if torch.cuda.is_available():
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        # For PyTorch 2.x fine-grained matmul precision
        try:
            torch.set_float32_matmul_precision("high")
        except Exception:
            pass
except Exception:
    pass


def _normalized_interface_key(config: dict) -> Tuple:
    """Build a hashable key for interface-affecting params only."""
    base = {
        "object_type": config.get("object_type", DEFAULT_CARVEKIT_CONFIG["object_type"]),
        "batch_size_seg": config.get("batch_size_seg", DEFAULT_CARVEKIT_CONFIG["batch_size_seg"]),
        "batch_size_matting": config.get("batch_size_matting", DEFAULT_CARVEKIT_CONFIG["batch_size_matting"]),
        "seg_mask_size": config.get("seg_mask_size", DEFAULT_CARVEKIT_CONFIG["seg_mask_size"]),
        "matting_mask_size": config.get("matting_mask_size", DEFAULT_CARVEKIT_CONFIG["matting_mask_size"]),
        "trimap_prob_threshold": config.get("trimap_prob_threshold", DEFAULT_CARVEKIT_CONFIG["trimap_prob_threshold"]),
        "trimap_dilation": config.get("trimap_dilation", DEFAULT_CARVEKIT_CONFIG["trimap_dilation"]),
        "trimap_erosion_iters": config.get("trimap_erosion_iters", DEFAULT_CARVEKIT_CONFIG["trimap_erosion_iters"]),
        "fp16": config.get("fp16", DEFAULT_CARVEKIT_CONFIG["fp16"]),
    }
    # Sort to make deterministic
    return tuple(sorted(base.items()))


# Very small LRU cache for interfaces to avoid heavy re-inits across presets
_INTERFACE_CACHE: Dict[Tuple, HiInterface] = {}
_INTERFACE_CACHE_ORDER: List[Tuple] = []
_INTERFACE_CACHE_MAX = max(2, int(os.getenv("INTERFACE_CACHE_SIZE", "4")))


def create_interface(config=None):
    """Create a carvekit HiInterface with the given configuration"""
    if config is None:
        config = DEFAULT_CARVEKIT_CONFIG
    return HiInterface(
        object_type=config.get("object_type", DEFAULT_CARVEKIT_CONFIG["object_type"]),
        batch_size_seg=config.get("batch_size_seg", DEFAULT_CARVEKIT_CONFIG["batch_size_seg"]),
        batch_size_matting=config.get("batch_size_matting", DEFAULT_CARVEKIT_CONFIG["batch_size_matting"]),
        device='cuda' if torch.cuda.is_available() else 'cpu',
        seg_mask_size=config.get("seg_mask_size", DEFAULT_CARVEKIT_CONFIG["seg_mask_size"]),
        matting_mask_size=config.get("matting_mask_size", DEFAULT_CARVEKIT_CONFIG["matting_mask_size"]),
        trimap_prob_threshold=config.get("trimap_prob_threshold", DEFAULT_CARVEKIT_CONFIG["trimap_prob_threshold"]),
        trimap_dilation=config.get("trimap_dilation", DEFAULT_CARVEKIT_CONFIG["trimap_dilation"]),
        trimap_erosion_iters=config.get("trimap_erosion_iters", DEFAULT_CARVEKIT_CONFIG["trimap_erosion_iters"]),
        fp16=config.get("fp16", DEFAULT_CARVEKIT_CONFIG["fp16"])
    )

def get_or_create_interface(config: dict) -> HiInterface:
    key = _normalized_interface_key(config)
    if key in _INTERFACE_CACHE:
        # bump LRU
        try:
            _INTERFACE_CACHE_ORDER.remove(key)
        except ValueError:
            pass
        _INTERFACE_CACHE_ORDER.append(key)
        return _INTERFACE_CACHE[key]
    # Create and insert
    iface = create_interface(dict(key))
    _INTERFACE_CACHE[key] = iface
    _INTERFACE_CACHE_ORDER.append(key)
    # evict
    while len(_INTERFACE_CACHE_ORDER) > _INTERFACE_CACHE_MAX:
        old = _INTERFACE_CACHE_ORDER.pop(0)
        try:
            del _INTERFACE_CACHE[old]
        except KeyError:
            pass
    return iface

# Initialize default interface (and optional warmup)
interface = get_or_create_interface(DEFAULT_CARVEKIT_CONFIG)
if os.getenv("WARMUP", "0") == "1":
    try:
        from PIL import Image
        dummy = Image.new("RGB", (DEFAULT_CARVEKIT_CONFIG["seg_mask_size"], DEFAULT_CARVEKIT_CONFIG["seg_mask_size"]))
        _ = interface([dummy])
    except Exception:
        pass

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.get("/health")
def health():
    return jsonify(status="ok"), 200

@app.get("/info")
def info():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    gpu_name = None
    if device == "cuda":
        try:
            gpu_name = torch.cuda.get_device_name(0)
        except Exception:
            gpu_name = "CUDA"
    return jsonify(
        device=device,
        gpu=gpu_name,
        torch=torch.__version__,
        fp16=DEFAULT_CARVEKIT_CONFIG["fp16"],
        tf32=getattr(torch.backends.cuda.matmul, "allow_tf32", False) if torch.cuda.is_available() else False,
        png_compress_level=PNG_COMPRESS_LEVEL,
    ), 200

@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")

@app.get("/script.js")
def script_js():
    return send_from_directory(STATIC_DIR, "script.js")

@app.get("/style.css")
def style_css():
    return send_from_directory(STATIC_DIR, "style.css")

@app.get("/processed/<path:filename>")
def get_processed(filename: str):
    return send_from_directory(PROCESSED_DIR, filename)

@app.post("/upload")
def upload():
    # Parse carvekit configuration from query parameters
    # These parameters allow fine-tuning of background removal:
    # - object_type: "object" (less aggressive) or "hairs-like" (more aggressive)
    # - trimap_prob_threshold: Higher values preserve more content (200-250)
    # - trimap_dilation: Lower values reduce mask expansion (10-50)
    # - trimap_erosion_iters: Lower values reduce mask erosion (1-10)
    carvekit_config = {}
    try:
        # Get object type
        object_type = request.args.get('object_type')
        if object_type in ['object', 'hairs-like']:
            carvekit_config['object_type'] = object_type
        
        # Get numeric parameters
        for param in ['trimap_prob_threshold', 'trimap_dilation', 'trimap_erosion_iters']:
            value = request.args.get(param)
            if value is not None:
                try:
                    carvekit_config[param] = int(value)
                except ValueError:
                    pass  # Ignore invalid values
        # Optional: override fp16 explicitly
        fp16 = request.args.get('fp16')
        if fp16 in ['0', '1']:
            carvekit_config['fp16'] = (fp16 == '1')
    except Exception as e:
        print(f"Error parsing carvekit config: {e}")
        # Continue with default config if parsing fails

    # Expect multiple files under field name 'images'
    if "images" not in request.files:
        return jsonify(error="No images field in request"), 400

    files = request.files.getlist("images")
    if not files:
        return jsonify(error="No files uploaded"), 400

    # Create/retrieve interface with custom config if provided (cached)
    processing_interface = get_or_create_interface({**DEFAULT_CARVEKIT_CONFIG, **carvekit_config}) if carvekit_config else interface

    # Post-process controls (do not affect interface key)
    try:
        feather_radius = float(request.args.get('feather_radius', '0'))
        alpha_threshold = int(request.args.get('alpha_threshold', '0'))
        feather_radius = max(0.0, min(8.0, feather_radius))
        alpha_threshold = max(0, min(255, alpha_threshold))
    except Exception:
        feather_radius, alpha_threshold = 0.0, 0

    # Read images first to batch the processing for speed
    pil_images: List[Image.Image] = []
    file_metas: List[Dict] = []
    for f in files:
        original_name = secure_filename(f.filename or "")
        if not original_name or not allowed_file(original_name):
            file_metas.append({"ok": False, "name": original_name or "unknown", "error": "Unsupported or empty filename"})
            continue

        try:
            # Read into Pillow safely
            # Copy stream to BytesIO to avoid issues with some werkzeug streams
            buf = BytesIO(f.read())
            buf.seek(0)
            img = Image.open(buf)
            img.load()  # force load
        except UnidentifiedImageError:
            file_metas.append({"ok": False, "name": original_name, "error": "Invalid image data"})
            continue
        except Exception as e:
            file_metas.append({"ok": False, "name": original_name, "error": f"Failed to read image: {str(e)}"})
            continue
        # Ensure consistent mode for rembg
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        pil_images.append(img)
        file_metas.append({"ok": True, "name": original_name})

    # If no valid images remain
    if not pil_images:
        return jsonify(results=file_metas), 200

    # Batch process
    start_batch = time.time()
    try:
        processed_images = processing_interface(pil_images)
    except Exception as e:
        # Mark all as failed
        failed = [{"ok": False, "name": m.get("name", "unknown"), "error": f"Processing failed: {str(e)}"} for m in file_metas]
        return jsonify(results=failed), 200

    elapsed_total = (time.time() - start_batch) * 1000.0
    per_item_ms = int(elapsed_total / max(1, len(processed_images)))

    # Save outputs with optional post-process
    results: List[Dict] = []
    for idx, out_img in enumerate(processed_images):
        meta = file_metas[idx]
        if not meta.get("ok"):
            results.append(meta)
            continue
        try:
            if out_img.mode != "RGBA":
                out_img = out_img.convert("RGBA")

            # Post-process: alpha threshold and feathering
            if alpha_threshold > 0 or feather_radius > 0.0:
                r, g, b, a = out_img.split()
                if alpha_threshold > 0:
                    a = a.point(lambda px: 0 if px < alpha_threshold else px)
                if feather_radius > 0.0:
                    from PIL import ImageFilter
                    a = a.filter(ImageFilter.GaussianBlur(radius=feather_radius))
                out_img = Image.merge("RGBA", (r, g, b, a))

            out_name = f"{uuid.uuid4().hex}.png"
            out_path = os.path.join(PROCESSED_DIR, out_name)
            out_img.save(out_path, format="PNG", optimize=True, compress_level=PNG_COMPRESS_LEVEL)
            results.append({
                "ok": True,
                "name": meta.get("name", "image"),
                "url": f"/processed/{out_name}",
                "ms": per_item_ms,
            })
        except Exception as e:
            results.append({"ok": False, "name": meta.get("name", "image"), "error": f"Save failed: {str(e)}"})

    return jsonify(results=results), 200

# Legacy single-file endpoint kept for compatibility (optional)
@app.post("/remove-background")
def remove_background_single():
    # Parse carvekit configuration from query parameters
    carvekit_config = {}
    try:
        # Get object type
        object_type = request.args.get('object_type')
        if object_type in ['object', 'hairs-like']:
            carvekit_config['object_type'] = object_type
        
        # Get numeric parameters
        for param in ['trimap_prob_threshold', 'trimap_dilation', 'trimap_erosion_iters']:
            value = request.args.get(param)
            if value is not None:
                try:
                    carvekit_config[param] = int(value)
                except ValueError:
                    pass  # Ignore invalid values
    except Exception as e:
        print(f"Error parsing carvekit config: {e}")
        # Continue with default config if parsing fails

    if "file" not in request.files:
        return jsonify(error="No file part"), 400
    file = request.files["file"]
    if not file or file.filename == "":
        return jsonify(error="No selected file"), 400
    if not allowed_file(file.filename):
        return jsonify(error="Unsupported file type"), 400

    # Create/retrieve interface
    processing_interface = get_or_create_interface({**DEFAULT_CARVEKIT_CONFIG, **carvekit_config}) if carvekit_config else interface

    try:
        buf = BytesIO(file.read())
        buf.seek(0)
        img = Image.open(buf)
        img.load()
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        # Process image with carvekit using the appropriate interface
        processed_images = processing_interface([img])
        out_img = processed_images[0]
        if out_img.mode != "RGBA":
            out_img = out_img.convert("RGBA")

        img_byte_arr = BytesIO()
        out_img.save(img_byte_arr, format="PNG", optimize=True, compress_level=PNG_COMPRESS_LEVEL)
        img_byte_arr.seek(0)
        return send_file(img_byte_arr, mimetype="image/png")
    except UnidentifiedImageError:
        return jsonify(error="Invalid image data"), 400
    except Exception as e:
        return jsonify(error=f"Processing failed: {str(e)}"), 500

if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=DEBUG)
