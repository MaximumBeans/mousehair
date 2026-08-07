"""Classic static Mousehair crosshair effect."""

from .base import CrosshairEffect


class StaticCrosshairEffect(CrosshairEffect):
    """Render the ordinary two-colour static crosshair."""

    name = "static"

    def render(
        self,
        painter,
        mx,
        my,
        outer_pen,
        inner_pen,
    ):
        """Draw both passes of the classic Mousehair crosshair."""
        self.host.draw_static_lines(
            painter,
            mx,
            my,
            outer_pen,
        )

        self.host.draw_static_lines(
            painter,
            mx,
            my,
            inner_pen,
        )
