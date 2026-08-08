"""Capture-provider interfaces for Mousehair."""

from __future__ import annotations
from typing import Optional

from PyQt5 import QtGui
from Xlib import display as xdisplay
from Xlib.ext import composite


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
    """XComposite-backed image source for the ring magnifier.

    At this stage the class only establishes the X11 connection and confirms
    that the extensions required by the eventual capture path are available.
    Pixel capture is deliberately left for a later, isolated change.
    """

    def __init__(self) -> None:
        self.available = False
        self.last_error: Optional[str] = None
        self.display: Optional[xdisplay.Display] = None
        self.root = None
        self.composite_version: Optional[tuple[int, int]] = None

        try:
            self.display = xdisplay.Display()
            self.root = self.display.screen().root

            if not self.display.has_extension(composite.extname):
                self.last_error = "The XComposite extension is unavailable."
                return

            version = self.display.composite_query_version()
            self.composite_version = (
                version.major_version,
                version.minor_version,
            )
            self.available = True

        except Exception as exc:
            self.last_error = (
                f"Could not initialise the XComposite capture backend: {exc}"
            )
            self.close()

    def close(self) -> None:
        """Close the backend's private X11 connection, if it was opened."""

        if self.display is None:
            return

        try:
            self.display.close()
        except Exception:
            pass
        finally:
            self.display = None
            self.root = None
            self.composite_version = None
            self.available = False

    def capture(
        self,
        *,
        cursor_x: int,
        cursor_y: int,
        radius: int,
        magnification: float
    ) -> Optional[QtGui.QImage]:
        return None
