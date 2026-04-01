from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.config import COVER_ROOT


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for font_path in candidates:
        if Path(font_path).exists():
            try:
                return ImageFont.truetype(font_path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def render_name_author_cover(series_id: int, name: str, author: str) -> Path:
    COVER_ROOT.mkdir(parents=True, exist_ok=True)
    token = hashlib.sha1(f"{series_id}|{name}|{author}".encode("utf-8")).hexdigest()[:16]
    path = COVER_ROOT / f"cover_{token}.png"

    image = Image.new("RGB", (900, 1200), color=(40, 48, 72))
    draw = ImageDraw.Draw(image)

    draw.rectangle((70, 90, 830, 1110), outline=(240, 198, 116), width=6)

    title_font = _load_font(72)
    author_font = _load_font(42)

    draw.text((120, 240), name or "未命名漫画", fill=(248, 248, 238), font=title_font)
    draw.text((120, 760), f"作者: {author or '未知'}", fill=(214, 214, 214), font=author_font)

    image.save(path)
    return path


def store_cover_image(series_id: int, source_path: Path) -> Path:
    COVER_ROOT.mkdir(parents=True, exist_ok=True)
    suffix = source_path.suffix.lower() if source_path.suffix else ".png"
    digest = hashlib.sha1(source_path.read_bytes()).hexdigest()[:16]
    target = COVER_ROOT / f"cover_{digest}{suffix}"
    try:
        if source_path.resolve() == target.resolve():
            return target
    except Exception:
        pass
    shutil.copy2(source_path, target)
    return target
