from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.config import COVER_ROOT

DISPLAY_CACHE_ROOT = COVER_ROOT / "_scaled"
SOURCE_CACHE_ROOT = DISPLAY_CACHE_ROOT / "_source"
MAX_COVER_WIDTH = 1200
MAX_COVER_HEIGHT = 1800
LIBRARY_COVER_MAX_WIDTH = 199


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
    SOURCE_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    token = hashlib.sha1(f"{series_id}|{name}|{author}".encode("utf-8")).hexdigest()[:16]
    path = SOURCE_CACHE_ROOT / f"source_name_author_{token}.png"

    image = Image.new("RGB", (900, 1200), color=(40, 48, 72))
    draw = ImageDraw.Draw(image)

    draw.rectangle((70, 90, 830, 1110), outline=(240, 198, 116), width=6)

    title_font = _load_font(72)
    author_font = _load_font(42)

    draw.text((120, 240), name or "未命名漫画", fill=(248, 248, 238), font=title_font)
    draw.text((120, 760), f"作者: {author or '未知'}", fill=(214, 214, 214), font=author_font)

    image.save(path, optimize=True)
    return path


def store_cover_image(series_id: int, source_path: Path) -> Path:
    # 新策略：不再强制复制到 data/covers 根目录，仅保留来源索引。
    return source_path


def _source_token(cover_path: Path) -> str:
    try:
        resolved = str(cover_path.resolve())
    except Exception:
        resolved = str(cover_path)
    return hashlib.sha1(resolved.encode("utf-8")).hexdigest()[:12]


def get_cover_source_token(cover_path: Path) -> str:
    return _source_token(cover_path)


def _safe_mtime_ns(path: Path) -> int:
    try:
        return int(path.stat().st_mtime_ns)
    except Exception:
        return 0


def get_library_cover_cache_path(cover_path: Path, max_width: int = LIBRARY_COVER_MAX_WIDTH) -> Path:
    """生成书架封面缓存（宽度严格小于200px）。"""
    COVER_ROOT.mkdir(parents=True, exist_ok=True)
    DISPLAY_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    target_width = max(1, min(int(max_width), LIBRARY_COVER_MAX_WIDTH))
    size_root = DISPLAY_CACHE_ROOT / f"library_w{target_width}"
    size_root.mkdir(parents=True, exist_ok=True)

    source_token = _source_token(cover_path)
    mtime_ns = _safe_mtime_ns(cover_path)
    target = size_root / f"cover_{source_token}_{mtime_ns}.png"
    if target.exists():
        return target

    for stale in size_root.glob(f"cover_{source_token}_*.png"):
        if stale == target:
            continue
        try:
            stale.unlink()
        except Exception:
            continue

    with Image.open(cover_path) as img:
        image = img.convert("RGBA") if "A" in img.getbands() else img.convert("RGB")
        if image.width > target_width:
            ratio = target_width / float(max(image.width, 1))
            target_height = max(1, int(image.height * ratio))
            image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
        image.save(target, optimize=True)

    return target


def get_cover_display_path(cover_path: Path, width: int, height: int) -> Path:
    COVER_ROOT.mkdir(parents=True, exist_ok=True)
    DISPLAY_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    size_root = DISPLAY_CACHE_ROOT / f"{width}x{height}"
    size_root.mkdir(parents=True, exist_ok=True)

    mtime_ns = cover_path.stat().st_mtime_ns
    source_token = _source_token(cover_path)
    target = size_root / f"cover_{source_token}_{mtime_ns}.png"
    if target.exists():
        return target

    # 同一封面同一尺寸下仅保留最新版本缓存，避免旧缓存持续累积。
    stale_pattern = f"cover_{source_token}_*.png"
    for stale in size_root.glob(stale_pattern):
        if stale == target:
            continue
        try:
            stale.unlink()
        except Exception:
            continue

    with Image.open(cover_path) as img:
        image = img.convert("RGBA") if "A" in img.getbands() else img.convert("RGB")
        target_width = max(width, 1)
        if image.width != target_width:
            ratio = target_width / float(max(image.width, 1))
            target_height = max(1, int(image.height * ratio))
            image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
        image.save(target, optimize=True)

    return target


def get_existing_cover_cache_for_source(cover_path: Path) -> Path | None:
    if not DISPLAY_CACHE_ROOT.exists():
        return None

    source_token = _source_token(cover_path)
    pattern = f"cover_{source_token}_*.png"
    matches = [p for p in DISPLAY_CACHE_ROOT.rglob(pattern) if p.is_file()]
    if not matches:
        return None
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0]


def clear_cover_display_cache() -> int:
    if not DISPLAY_CACHE_ROOT.exists():
        return 0

    removed = 0
    for cached_file in DISPLAY_CACHE_ROOT.rglob("cover_*.png"):
        try:
            if not cached_file.is_file():
                continue
            cached_file.unlink()
            removed += 1
        except Exception:
            continue

    return removed


def clear_cover_display_cache_for_source(cover_path: Path) -> int:
    if not DISPLAY_CACHE_ROOT.exists():
        return 0

    removed = 0
    source_token = _source_token(cover_path)
    pattern = f"cover_{source_token}_*.png"
    for cached_file in DISPLAY_CACHE_ROOT.rglob(pattern):
        try:
            if not cached_file.is_file():
                continue
            cached_file.unlink()
            removed += 1
        except Exception:
            continue

    return removed


def has_cover_cache_for_source(cover_path: Path) -> bool:
    if not DISPLAY_CACHE_ROOT.exists():
        return False
    source_token = _source_token(cover_path)
    return any(DISPLAY_CACHE_ROOT.rglob(f"cover_{source_token}_*.png"))


def delete_managed_cover_source(cover_path: Path) -> bool:
    if not cover_path.exists() or not cover_path.is_file():
        return False
    try:
        resolved = cover_path.resolve()
        if resolved.is_relative_to(SOURCE_CACHE_ROOT.resolve()):
            pass
        elif resolved.is_relative_to(COVER_ROOT.resolve()) and cover_path.name.startswith("cover_"):
            # 兼容旧版 data/covers/cover_*.png
            pass
        else:
            return False
    except Exception:
        return False

    try:
        cover_path.unlink()
        return True
    except Exception:
        return False
