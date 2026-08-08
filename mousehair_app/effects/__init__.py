"""Built-in visual effects for Mousehair."""

from .base import CrosshairEffect
from .static import StaticCrosshairEffect
from .sliding import SlidingCrosshairEffect
from .arrows import ArrowCrosshairEffect
from .pulse import PulseCrosshairEffect

__all__ = [
    "CrosshairEffect",
    "StaticCrosshairEffect",
    "SlidingCrosshairEffect",
    "ArrowCrosshairEffect",
    "PulseCrosshairEffect",
]
