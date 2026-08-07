"""Sliding-segment Mousehair crosshair effect."""

from .base import CrosshairEffect


class SlidingCrosshairEffect(CrosshairEffect):
    """Render the inward-moving segmented crosshair."""

    name = "sliding"

    def render(
        self,
        painter,
        mx,
        my,
        outer_pen,
        inner_pen,
    ):
        """Draw both colour passes of the sliding line animation."""
        self.host.draw_animated_lines(
            painter,
            mx,
            my,
            outer_pen,
        )

        self.host.draw_animated_lines(
            painter,
            mx,
            my,
            inner_pen,
        )
