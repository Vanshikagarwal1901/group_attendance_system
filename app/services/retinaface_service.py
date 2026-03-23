from pathlib import Path
import importlib
import sys

import cv2
import numpy as np


BASE_DIR = Path(__file__).resolve().parent.parent.parent
RETINAFACE_DIR = BASE_DIR / "retinaface"
RETINAFACE_WEIGHTS = RETINAFACE_DIR / "weights" / "Resnet50_Final.pth"

_MODEL = None
_CFG = None
_TORCH = None


def _ensure_retinaface_imports():
    global _CFG
    global _TORCH

    if _CFG is not None and _TORCH is not None:
        return

    if str(RETINAFACE_DIR) not in sys.path:
        sys.path.insert(0, str(RETINAFACE_DIR))

    torch = importlib.import_module("torch")
    cfg_module = importlib.import_module("data")
    cfg_re50 = cfg_module.cfg_re50

    _TORCH = torch
    _CFG = cfg_re50


def _load_model():
    global _MODEL

    if _MODEL is not None:
        return _MODEL

    if not RETINAFACE_WEIGHTS.exists():
        raise FileNotFoundError(f"RetinaFace weights not found: {RETINAFACE_WEIGHTS}")

    _ensure_retinaface_imports()

    retinaface_module = importlib.import_module("models.retinaface")
    RetinaFace = retinaface_module.RetinaFace

    model = RetinaFace(cfg=_CFG, phase="test")
    state_dict = _TORCH.load(str(RETINAFACE_WEIGHTS), map_location="cpu")
    clean_state_dict = {k.replace("module.", ""): v for k, v in state_dict.items()}
    model.load_state_dict(clean_state_dict, strict=False)
    model.eval()
    _MODEL = model
    return _MODEL


def detect_face_crops(
    image: np.ndarray,
    confidence_threshold: float = 0.6,
    nms_threshold: float = 0.4,
) -> list[np.ndarray]:
    _ensure_retinaface_imports()

    prior_box_module = importlib.import_module("layers.functions.prior_box")
    box_utils_module = importlib.import_module("utils.box_utils")
    nms_module = importlib.import_module("utils.nms.py_cpu_nms")

    PriorBox = prior_box_module.PriorBox
    decode = box_utils_module.decode
    py_cpu_nms = nms_module.py_cpu_nms

    model = _load_model()
    img = np.float32(image)
    height, width, _ = img.shape
    scale = _TORCH.Tensor([width, height, width, height])

    img -= (104, 117, 123)
    img = img.transpose(2, 0, 1)
    img = _TORCH.from_numpy(img).unsqueeze(0)

    with _TORCH.no_grad():
        loc, conf, _ = model(img)

    priorbox = PriorBox(_CFG, image_size=(height, width))
    priors = priorbox.forward().data

    boxes = decode(loc.squeeze(0), priors, _CFG["variance"])
    boxes = boxes * scale
    boxes = boxes.numpy()
    scores = conf.squeeze(0).numpy()[:, 1]

    inds = np.where(scores > confidence_threshold)[0]
    boxes = boxes[inds]
    scores = scores[inds]

    if len(scores) == 0:
        return []

    dets = np.hstack((boxes, scores[:, np.newaxis])).astype(np.float32)
    keep = py_cpu_nms(dets, nms_threshold)
    dets = dets[keep]

    crops: list[np.ndarray] = []
    for box in dets:
        x1, y1, x2, y2, _score = box
        x1 = max(0, int(x1))
        y1 = max(0, int(y1))
        x2 = min(width, int(x2))
        y2 = min(height, int(y2))
        if x2 <= x1 or y2 <= y1:
            continue

        crop = image[y1:y2, x1:x2]
        if crop.size == 0:
            continue

        crops.append(crop)

    return crops


def detect_face_crops_from_path(
    image_path: str,
    confidence_threshold: float = 0.6,
    nms_threshold: float = 0.4,
) -> list[np.ndarray]:
    image = cv2.imread(image_path)
    if image is None:
        return []
    return detect_face_crops(image, confidence_threshold, nms_threshold)
