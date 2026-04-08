from pathlib import Path
import os
from uuid import uuid4

import cv2
import numpy as np
from fastapi import UploadFile
from deepface import DeepFace

from app.services.retinaface_service import detect_face_crops_from_path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
STUDENT_IMAGES_DIR = BASE_DIR / "data" / "student_images"
GROUP_IMAGES_DIR = BASE_DIR / "data" / "group_images"

STUDENT_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
GROUP_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# FaceNet embeddings with RetinaFace-first detection.
# Cosine similarity: 1.0 = identical, lower = less similar.
# DeepFace's recommended cosine distance threshold for FaceNet is 0.40,
# which corresponds to a similarity floor of 0.60.
_DEFAULT_MODEL = "Facenet512"
_MODEL_NAME = os.getenv("FACE_MODEL_NAME", _DEFAULT_MODEL)
_FALLBACK_DETECTOR_BACKENDS = ["retinaface", "mtcnn", "opencv"]
_MODEL_SIMILARITY_DEFAULTS = {
    "Facenet": 0.60,
    "Facenet512": 0.68,
    "ArcFace": 0.68,
}
SIMILARITY_THRESHOLD = float(
    os.getenv(
        "FACE_SIMILARITY_THRESHOLD",
        str(_MODEL_SIMILARITY_DEFAULTS.get(_MODEL_NAME, 0.65)),
    )
)
MIN_FACE_SIZE_PX = int(os.getenv("FACE_MIN_SIZE_PX", "60"))
MIN_FACE_SHARPNESS = float(os.getenv("FACE_MIN_SHARPNESS", "40.0"))


def _save_upload(file: UploadFile, destination: Path) -> None:
    with destination.open("wb") as out:
        out.write(file.file.read())


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _embedding_from_face_crop(face_crop: np.ndarray) -> np.ndarray | None:
    try:
        results = DeepFace.represent(
            img_path=face_crop,
            model_name=_MODEL_NAME,
            detector_backend="skip",
            enforce_detection=False,
        )
        if results:
            return np.array(results[0]["embedding"], dtype=np.float32)
    except Exception:
        pass
    return None


def _is_face_crop_usable(face_crop: np.ndarray) -> bool:
    height, width = face_crop.shape[:2]
    if min(height, width) < MIN_FACE_SIZE_PX:
        return False

    gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    return sharpness >= MIN_FACE_SHARPNESS


def _retinaface_embeddings(image_path: str) -> list[np.ndarray]:
    if not Path(image_path).exists():
        return []

    try:
        face_crops = detect_face_crops_from_path(image_path)
    except Exception:
        return []

    embeddings: list[np.ndarray] = []
    for crop in face_crops:
        if not _is_face_crop_usable(crop):
            continue
        embedding = _embedding_from_face_crop(crop)
        if embedding is not None:
            embeddings.append(embedding)

    return embeddings


def _deepface_backend_embeddings(image_path: str) -> list[np.ndarray]:
    if not Path(image_path).exists():
        return []

    for backend in _FALLBACK_DETECTOR_BACKENDS:
        try:
            results = DeepFace.represent(
                img_path=image_path,
                model_name=_MODEL_NAME,
                detector_backend=backend,
                enforce_detection=False,
            )
            embeddings = [
                np.array(result["embedding"], dtype=np.float32)
                for result in results
                if result.get("embedding")
            ]
            if embeddings:
                return embeddings
        except Exception:
            continue

    return []


def _get_embedding(image_path: str) -> np.ndarray | None:
    """Return the FaceNet embedding for the (single) face in a registration photo."""
    retinaface_embeddings = _retinaface_embeddings(image_path)
    if retinaface_embeddings:
        return retinaface_embeddings[0]

    fallback_embeddings = _deepface_backend_embeddings(image_path)
    if fallback_embeddings:
        return fallback_embeddings[0]

    return None


def _get_all_face_embeddings(image_path: str) -> list[np.ndarray]:
    """Detect every face in a group photo and return their FaceNet embeddings."""
    retinaface_embeddings = _retinaface_embeddings(image_path)
    if retinaface_embeddings:
        return retinaface_embeddings

    return _deepface_backend_embeddings(image_path)


def _group_image_embeddings(image_path: str) -> list[np.ndarray]:
    embeddings = _get_all_face_embeddings(image_path)
    if embeddings:
        return embeddings

    if not Path(image_path).exists():
        return []

    try:
        results = DeepFace.represent(
            img_path=image_path,
            model_name=_MODEL_NAME,
            detector_backend="skip",
            enforce_detection=False,
        )
        return [np.array(result["embedding"], dtype=np.float32) for result in results if result.get("embedding")]
    except Exception:
        return []


def register_student_photo(student_id: int, file: UploadFile) -> str:
    safe_name = file.filename or "photo.jpg"
    filename = f"student_{student_id}_{uuid4().hex}_{safe_name}"
    target = STUDENT_IMAGES_DIR / filename
    _save_upload(file, target)

    image = cv2.imread(str(target))
    if image is None:
        raise ValueError("Invalid image file")

    face_crops = detect_face_crops_from_path(str(target))
    usable_crops = [crop for crop in face_crops if _is_face_crop_usable(crop)]
    if not usable_crops:
        target.unlink(missing_ok=True)
        raise ValueError("No clear face detected. Upload a brighter and sharper photo.")
    if len(usable_crops) > 1:
        target.unlink(missing_ok=True)
        raise ValueError("Upload a single-person photo only.")

    return str(target)


def find_present_students(
    group_files: list[UploadFile],
    student_photo_paths: dict[int, list[str]],
    similarity_threshold: float = SIMILARITY_THRESHOLD,
) -> set[int]:
    present_ids: set[int] = set()

    # --- Build embedding database from registered photos ---
    student_embeddings: dict[int, list[np.ndarray]] = {}
    for student_id, paths in student_photo_paths.items():
        embeddings: list[np.ndarray] = []
        for path in paths:
            if not Path(path).exists():
                continue
            emb = _get_embedding(path)
            if emb is not None:
                embeddings.append(emb)
        if embeddings:
            student_embeddings[student_id] = embeddings

    if not student_embeddings:
        return present_ids

    # --- Process each uploaded group photo ---
    for image_file in group_files:
        safe_filename = image_file.filename or f"{uuid4().hex}.jpg"
        group_target = GROUP_IMAGES_DIR / safe_filename
        _save_upload(image_file, group_target)

        face_embeddings = _group_image_embeddings(str(group_target))

        for face_emb in face_embeddings:
            for student_id, registered_embeddings in student_embeddings.items():
                if student_id in present_ids:
                    continue  # already marked — skip further comparisons
                for reg_emb in registered_embeddings:
                    if _cosine_similarity(face_emb, reg_emb) >= similarity_threshold:
                        present_ids.add(student_id)
                        break

    return present_ids
