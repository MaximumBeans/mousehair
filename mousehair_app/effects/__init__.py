"""Built-in visual effects for Mousehair."""

from .base import CrosshairEffect
from .static import StaticCrosshairEffect
from .sliding import SlidingCrosshairEffect

__all__ = [
    "CrosshairEffect",
    "StaticCrosshairEffect",
    "SlidingCrosshairEffect",
]
