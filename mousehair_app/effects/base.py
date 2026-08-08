"""Base interfaces for Mousehair visual effects."""


class CrosshairEffect:
    """Base class for a Mousehair crosshair rendering effect."""

    name = "base"
    display_name = "Base effect"

    # Settings UI grouping. Existing controls currently fall into either the
    # segmented-animation family or the arrow family.
    control_family = "none"

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
