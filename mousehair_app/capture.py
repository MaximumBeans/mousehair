"""Capture-provider interfaces for Mousehair."""

from __future__ import annotations
from typing import Optional
from PyQt5 import QtGui


class CaptureProvider:
    """Abstract source of image frames for the ring magnifier."""

    def capture(self, *, cursor_x: int, cursor_y: int, radius: int, magnification: float) -> Optional[QtGui.QImage]:
        raise NotImplementedError


class NullCaptureProvider(CaptureProvider):
    """No-op provider used until the XComposite backend is implemented."""

    def capture(self, *, cursor_x: int, cursor_y: int, radius: int, magnification: float) -> Optional[QtGui.QImage]:
        return None
