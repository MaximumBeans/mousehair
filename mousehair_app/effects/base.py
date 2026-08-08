"""Base interfaces and settings metadata for Mousehair visual effects."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EffectSetting:
    """Describe one user-configurable setting belonging to an effect.

    The Effects Engine uses these descriptors to construct settings controls
    without the main Mousehair dialog needing effect-specific knowledge.
    """

    key: str
    label: str
    kind: str
    default: object

    minimum: float | int | None = None
    maximum: float | int | None = None
    step: float | int | None = None

    suffix: str = ""
    decimals: int = 0


class CrosshairEffect:
    """Base class for a Mousehair crosshair rendering effect."""

    name = "base"
    display_name = "Base effect"

    # Each effect may expose its own settings descriptors.
    settings = ()

    def __init__(self, host):
        self.host = host

    def render(
        self,
        painter,
        mx,
        my,
        outer_pen,
        inner_pen,
    ):
        """Render this effect."""
        raise NotImplementedError
