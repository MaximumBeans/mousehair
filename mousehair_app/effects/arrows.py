"""Direction-arrow Mousehair crosshair effect."""

from .base import CrosshairEffect


class ArrowCrosshairEffect(CrosshairEffect):
    """Render Mousehair's inward-pointing outlined arrow reticule."""

    name = "arrows"

    def render(
        self,
        painter,
        mx,
        my,
        outer_pen,
        inner_pen,
    ):
        """Draw all four arrow-decorated reticule arms.

        Arrow rendering creates specialised pens internally because arrow
        outlines, joins, caps, and centre-line redraws differ from the ordinary
        two-pass crosshair effects. The generic pens are therefore intentionally
        unused by this effect.
        """
        del outer_pen
        del inner_pen

        self.host.draw_arrow_lines(
            painter,
            mx,
            my,
        )
