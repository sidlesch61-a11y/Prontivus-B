import os
import uuid
from typing import Tuple

ALLOWED_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "application/dicom",
    "application/dicom+json",
}

MAX_SIZE = 10 * 1024 * 1024  # 10MB


def validate_file(filename: str, content_type: str, size: int) -> None:
    if content_type not in ALLOWED_TYPES:
        raise ValueError("Tipo de arquivo não suportado")
    if size > MAX_SIZE:
        raise ValueError("Tamanho máximo excedido (10MB)")


def store_file(base_dir: str, clinic_id: int, patient_id: int, filename: str, content: bytes) -> str:
    safe_dir = os.path.join(base_dir, str(clinic_id), str(patient_id))
    os.makedirs(safe_dir, exist_ok=True)
    ext = os.path.splitext(filename)[1]
    name = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(safe_dir, name)
    with open(path, "wb") as f:
        f.write(content)
    return path


