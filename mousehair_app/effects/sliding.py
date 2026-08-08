"""Sliding-segment Mousehair crosshair effect."""

from .base import CrosshairEffect, EffectSetting


class SlidingCrosshairEffect(CrosshairEffect):
    """Render the inward-moving segmented crosshair."""

    name = "sliding"
    display_name = "Sliding inward"

    settings = (
        EffectSetting(
            key="animate_speed",
            label="Animation speed",
            kind="int",
            default=180,
            minimum=10,
            maximum=1000,
            step=10,
            suffix=" px/s",
        ),
        EffectSetting(
            key="animate_spacing",
            label="Animation spacing",
            kind="int",
            default=32,
            minimum=8,
            maximum=200,
            step=1,
            suffix=" px",
        ),
        EffectSetting(
            key="animate_segment_length",
            label="Segment length",
            kind="int",
            default=14,
            minimum=2,
            maximum=100,
            step=1,
            suffix=" px",
        ),
    )

    def _draw_segment_line(
        self,
        painter,
        start_x,
        start_y,
        end_x,
        end_y,
    ):
        """Draw one animated segmented arm.

        Segment placement is derived from the host's animation phase, spacing,
        and segment length. The same geometry is used for horizontal and
        vertical arms.
        """
        dx = end_x - start_x
        dy = end_y - start_y

        length = int(
            (dx * dx + dy * dy) ** 0.5
        )

        if length <= 0:
            return

        unit_x = dx / length
        unit_y = dy / length

        spacing = max(
            1,
            self.host.animate_spacing,
        )

        segment_length = max(
            1,
            min(
                self.host.animate_segment_length,
                spacing,
            ),
        )

        phase = (
            self.host.animation_phase
            % spacing
        )

        position = phase - spacing

        while position < length:
            segment_start = max(
                0,
                position,
            )

            segment_end = min(
                length,
                position + segment_length,
            )

            if (
                segment_end > 0
                and segment_start < length
            ):
                x1 = (
                    start_x
                    + unit_x * segment_start
                )
                y1 = (
                    start_y
                    + unit_y * segment_start
                )
                x2 = (
                    start_x
                    + unit_x * segment_end
                )
                y2 = (
                    start_y
                    + unit_y * segment_end
                )

                painter.drawLine(
                    int(x1),
                    int(y1),
                    int(x2),
                    int(y2),
                )

            position += spacing

    def _draw_lines(
        self,
        painter,
        mx,
        my,
        pen,
    ):
        """Draw one colour pass of all four sliding arms."""
        host = self.host
        gap = host.gap

        painter.setPen(pen)

        self._draw_segment_line(
            painter,
            0,
            my,
            max(0, mx - gap),
            my,
        )

        self._draw_segment_line(
            painter,
            host.width(),
            my,
            min(
                host.width(),
                mx + gap,
            ),
            my,
        )

        self._draw_segment_line(
            painter,
            mx,
            0,
            mx,
            max(0, my - gap),
        )

        self._draw_segment_line(
            painter,
            mx,
            host.height(),
            mx,
            min(
                host.height(),
                my + gap,
            ),
        )

    def render(
        self,
        painter,
        mx,
        my,
        outer_pen,
        inner_pen,
    ):
        """Draw broad and narrow colour passes of the sliding effect."""
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
