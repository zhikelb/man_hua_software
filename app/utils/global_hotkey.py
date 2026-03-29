from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Callable

from PyQt6.QtCore import QAbstractNativeEventFilter
from PyQt6.QtWidgets import QApplication


WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008


class WindowsGlobalHotkeyManager(QAbstractNativeEventFilter):
    def __init__(self) -> None:
        super().__init__()
        self._callbacks: dict[int, Callable[[], None]] = {}
        self._next_hotkey_id = 1
        self._enabled = sys.platform == "win32"
        self._user32 = ctypes.windll.user32 if self._enabled else None

        app = QApplication.instance()
        if app is not None:
            app.installNativeEventFilter(self)

    def nativeEventFilter(self, eventType, message):
        if not self._enabled:
            return False, 0

        if eventType not in ("windows_generic_MSG", "windows_dispatcher_MSG"):
            return False, 0

        msg = wintypes.MSG.from_address(int(message))
        if msg.message != WM_HOTKEY:
            return False, 0

        hotkey_id = int(msg.wParam)
        callback = self._callbacks.get(hotkey_id)
        if callback is not None:
            callback()
            return True, 0

        return False, 0

    def register_shortcut(self, shortcut: str, callback: Callable[[], None]) -> bool:
        if not self._enabled or self._user32 is None:
            return False

        parsed = self._parse_shortcut(shortcut)
        if parsed is None:
            return False

        modifiers, vk = parsed
        hotkey_id = self._next_hotkey_id
        self._next_hotkey_id += 1

        ok = bool(self._user32.RegisterHotKey(None, hotkey_id, modifiers, vk))
        if not ok:
            return False

        self._callbacks[hotkey_id] = callback
        return True

    def unregister_all(self) -> None:
        if not self._enabled or self._user32 is None:
            return

        ids = list(self._callbacks.keys())
        for hotkey_id in ids:
            self._user32.UnregisterHotKey(None, hotkey_id)
            self._callbacks.pop(hotkey_id, None)

    def _parse_shortcut(self, shortcut: str) -> tuple[int, int] | None:
        parts = [p.strip().lower() for p in shortcut.split("+") if p.strip()]
        if not parts:
            return None

        modifiers = 0
        key_part: str | None = None
        for part in parts:
            if part in ("ctrl", "control"):
                modifiers |= MOD_CONTROL
            elif part == "alt":
                modifiers |= MOD_ALT
            elif part == "shift":
                modifiers |= MOD_SHIFT
            elif part in ("win", "meta", "super"):
                modifiers |= MOD_WIN
            else:
                key_part = part

        if not key_part:
            return None

        vk = self._to_virtual_key(key_part)
        if vk is None:
            return None

        return modifiers, vk

    def _to_virtual_key(self, key: str) -> int | None:
        named: dict[str, int] = {
            "esc": 0x1B,
            "escape": 0x1B,
            "space": 0x20,
            "left": 0x25,
            "up": 0x26,
            "right": 0x27,
            "down": 0x28,
            "pgup": 0x21,
            "pageup": 0x21,
            "pgdn": 0x22,
            "pagedown": 0x22,
            "home": 0x24,
            "end": 0x23,
            "insert": 0x2D,
            "delete": 0x2E,
            "tab": 0x09,
            "enter": 0x0D,
            "return": 0x0D,
        }
        if key in named:
            return named[key]

        if len(key) == 1 and key.isalpha():
            return ord(key.upper())

        if len(key) == 1 and key.isdigit():
            return ord(key)

        if key.startswith("f") and key[1:].isdigit():
            idx = int(key[1:])
            if 1 <= idx <= 24:
                return 0x6F + idx

        return None