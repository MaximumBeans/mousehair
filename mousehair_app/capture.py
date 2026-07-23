"""Capture-provider interfaces for Mousehair."""

from __future__ import annotations
from typing import Optional
from PyQt5 import QtGui


class CaptureProvider:
    """Abstract source of image frames for the ring magnifier."""

    def capture(self, *, cursor_x: int, cursor_y: int, radius: int, magnification: float) -> Optional[QtGui.QImage]:
        raise NotImplementedError


class NullCaptureProvider(CaptureProvider):
    """No-op provider used when image capture is unavailable or disabled."""

    def capture(
        self,
        *,
        cursor_x: int,
        cursor_y: int,
        radius: int,
        magnification: float
    ) -> Optional[QtGui.QImage]:
        return None


class CompositeCapture(CaptureProvider):
    """Future XComposite-backed image source for the ring magnifier.

    This first implementation intentionally returns no frame. It exists so
    Mousehair can use the final provider type before XComposite resource
    management and pixel conversion are added in later, isolated steps.
    """

    def __init__(self) -> None:
        self.available = False
        self.last_error: Optional[str] = None

    def capture(
        self,
        *,
        cursor_x: int,
        cursor_y: int,
        radius: int,
        magnification: float
    ) -> Optional[QtGui.QImage]:
        return None
