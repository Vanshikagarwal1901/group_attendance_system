from pathlib import Path
import importlib.util
import sys
import types
from importlib.machinery import SourcelessFileLoader

import cv2
import numpy as np



BASE_DIR = Path(__file__).resolve().parent.parent.parent
RETINAFACE_DIR = BASE_DIR / "retinaface"
RETINAFACE_WEIGHTS = RETINAFACE_DIR / "weights" / "Resnet50_Final.pth"

_MODEL = None
_CFG = None
_TORCH = None


def _ensure_package_namespace(name: str) -> None:
    if name in sys.modules:
        return

    package = types.ModuleType(name)
    package.__path__ = [str(RETINAFACE_DIR)]
    sys.modules[name] = package


def _load_sourceless_module(module_name: str, pyc_path: Path):
    loader = SourcelessFileLoader(module_name, str(pyc_path))
    spec = importlib.util.spec_from_loader(module_name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    loader.exec_module(module)
    return module


def _ensure_retinaface_imports():
    global _CFG
    global _TORCH

    if _CFG is not None and _TORCH is not None:
        return

    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))

    for package_name in ["data", "layers", "layers.functions", "layers.modules", "models", "utils", "utils.nms"]:
        _ensure_package_namespace(package_name)

    torch = __import__("torch")
    cfg_module = _load_sourceless_module("data.config", RETINAFACE_DIR / "data" / "__pycache__" / "config.cpython-313.pyc")
    cfg_re50 = cfg_module.cfg_re50
    _load_sourceless_module(
        "layers.functions.prior_box",
        RETINAFACE_DIR / "layers" / "functions" / "__pycache__" / "prior_box.cpython-313.pyc",
    )
    _load_sourceless_module(
        "utils.nms.py_cpu_nms",
        RETINAFACE_DIR / "utils" / "nms" / "__pycache__" / "py_cpu_nms.cpython-313.pyc",
    )

    _TORCH = torch
    _CFG = cfg_re50


def _load_model():
    global _MODEL

    if _MODEL is not None:
        return _MODEL

    if not RETINAFACE_WEIGHTS.exists():
        raise FileNotFoundError(f"RetinaFace weights not found: {RETINAFACE_WEIGHTS}")

    _ensure_retinaface_imports()

    _load_sourceless_module(
        "models.net",
        RETINAFACE_DIR / "models" / "__pycache__" / "net.cpython-313.pyc",
    )
    retinaface_module = _load_sourceless_module(
        "models.retinaface",
        RETINAFACE_DIR / "models" / "__pycache__" / "retinaface.cpython-313.pyc",
    )
    RetinaFace = retinaface_module.RetinaFace

    model = RetinaFace(cfg=_CFG, phase="test")
    state_dict = _TORCH.load(str(RETINAFACE_WEIGHTS), map_location="cpu")
    clean_state_dict = {k.replace("module.", ""): v for k, v in state_dict.items()}
    model.load_state_dict(clean_state_dict, strict=False)
    model.eval()
    _MODEL = model
    return _MODEL


def _decode_boxes(loc: np.ndarray, priors: np.ndarray, variances: list[float]) -> np.ndarray:
    boxes = np.concatenate(
        (
            priors[:, :2] + loc[:, :2] * variances[0] * priors[:, 2:],
            priors[:, 2:] * np.exp(loc[:, 2:] * variances[1]),
        ),
        axis=1,
    )
    boxes[:, :2] -= boxes[:, 2:] / 2
    boxes[:, 2:] += boxes[:, :2]
    return boxes


def detect_face_crops(
    image: np.ndarray,
    confidence_threshold: float = 0.6,
    nms_threshold: float = 0.4,
) -> list[np.ndarray]:
    _ensure_retinaface_imports()

    prior_box_module = sys.modules["layers.functions.prior_box"]
    nms_module = sys.modules["utils.nms.py_cpu_nms"]

    PriorBox = prior_box_module.PriorBox
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

    boxes = _decode_boxes(loc.squeeze(0).numpy(), priors.numpy(), _CFG["variance"])
    boxes = boxes * scale.numpy()
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
