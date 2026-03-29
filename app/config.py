from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "manga.db"
CONFIG_PATH = DATA_DIR / "config.json"
IMPORT_COPY_ROOT = DATA_DIR / "imports"
COVER_ROOT = DATA_DIR / "covers"

DEFAULT_CONFIG: dict[str, Any] = {
    "import": {
        "default_storage_mode": "reference",
        "hash_check_on_duplicate": True,
        "duplicate_content_policy": "skip",
    },
    "reader": {
        "zoom_levels": [50, 75, 100, 125, 150, 200],
        "default_zoom": "fit",
        "preload_count": 2,
        "key_bindings": {
            "toggle_window": ["Ctrl+Shift+S"],
            "global_toggle_window": ["Ctrl+Alt+M"],
            "reader_toggle_fullscreen": ["F"],
            # 兼容旧版本字段
            "hide_window": ["Ctrl+Shift+S"],
            "show_window": ["Ctrl+Shift+S"],
            "global_show_window": ["Ctrl+Alt+M"],
            "reader_fullscreen": ["F"],
            "reader_windowed": ["F"],
        },
    },
    "ui": {
        "icon_size": 140,  # 图标大小，宽度
        "grid_cell_width": 180,  # 漫画网格单元宽度
        "grid_cell_height": 290,  # 漫画网格单元高度
        "sort_by": "updated_at",  # updated_at, name, author, episodes
        "sort_order": "desc",  # desc, asc
    },
}


def _deep_merge(default: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key, value in default.items():
        if key in override:
            override_value = override[key]
            if isinstance(value, dict) and isinstance(override_value, dict):
                merged[key] = _deep_merge(value, override_value)
            else:
                merged[key] = override_value
        else:
            merged[key] = value

    for key, value in override.items():
        if key not in merged:
            merged[key] = value
    return merged


def ensure_data_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMPORT_COPY_ROOT.mkdir(parents=True, exist_ok=True)
    COVER_ROOT.mkdir(parents=True, exist_ok=True)


def load_config() -> dict[str, Any]:
    ensure_data_dirs()
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        loaded = json.load(f)

    if not isinstance(loaded, dict):
        return DEFAULT_CONFIG.copy()

    return _deep_merge(DEFAULT_CONFIG, loaded)


def save_config(config: dict[str, Any]) -> None:
    ensure_data_dirs()
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
