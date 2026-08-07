"""Classic static Mousehair crosshair effect."""

from .base import CrosshairEffect


class StaticCrosshairEffect(CrosshairEffect):
    """Render the ordinary two-colour static crosshair."""

    name = "static"

    def _draw_lines(
        self,
        painter,
        mx,
        my,
        pen,
    ):
        """Draw one colour pass of the four crosshair arms."""
        host = self.host
        gap = host.gap

        painter.setPen(pen)

        painter.drawLine(
            0,
            my,
            max(0, mx - gap),
            my,
        )

        painter.drawLine(
            mx + gap,
            my,
            host.width(),
            my,
        )

        painter.drawLine(
            mx,
            0,
            mx,
            max(0, my - gap),
        )

        painter.drawLine(
            mx,
            my + gap,
            mx,
            host.height(),
        )

    def render(
        self,
        painter,
        mx,
        my,
        outer_pen,
        inner_pen,
    ):
        """Draw the broad outer pass, then the narrow inner pass."""
        self._draw_lines(
            painter,
            mx,
            my,
            outer_pen,
        )

        self._draw_lines(
            painter,
            mx,
            my,
            inner_pen,
        )
