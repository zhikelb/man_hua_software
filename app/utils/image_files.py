from __future__ import annotations

import hashlib
import re
from pathlib import Path

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
_DIGIT_SPLIT = re.compile(r"(\d+)")


def natural_sort_key(value: str) -> list[object]:
    parts = _DIGIT_SPLIT.split(value)
    key: list[object] = []
    for part in parts:
        if part.isdigit():
            key.append(int(part))
        else:
            key.append(part.lower())
    return key


def list_images_sorted(folder: Path) -> list[Path]:
    files = [
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    ]
    files.sort(key=lambda p: natural_sort_key(p.name))
    return files


def file_sha1(path: Path, chunk_size: int = 1024 * 1024) -> str:
    sha1 = hashlib.sha1()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            sha1.update(chunk)
    return sha1.hexdigest()
