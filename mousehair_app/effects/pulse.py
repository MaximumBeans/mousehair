"""Pulsing Mousehair crosshair effect."""

import math

from PyQt5 import QtGui

from .base import CrosshairEffect


class PulseCrosshairEffect(CrosshairEffect):
    """Render a gently breathing two-colour crosshair."""

    name = "pulse"
    display_name = "Pulse"
    control_family = "none"

    def _pulse_scale(self):
        """Return a smooth thickness multiplier.

        Mousehair already maintains ``animation_phase`` continuously. Reusing it
        means Pulse needs no additional timer or state of its own.
        """
        phase = float(self.host.animation_phase)

        # One complete pulse every 120 phase units.
        radians = (
            phase / 120.0
        ) * math.tau

        # Thickness varies between 85% and 115% of the configured value.
        return 1.0 + 0.15 * math.sin(radians)

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
        """Draw a two-pass crosshair with gently pulsing line thickness."""
        scale = self._pulse_scale()

        pulsed_outer_pen = QtGui.QPen(
            outer_pen
        )
        pulsed_inner_pen = QtGui.QPen(
            inner_pen
        )

        pulsed_outer_pen.setWidthF(
            max(
                1.0,
                float(self.host.outer_thickness) * scale,
            )
        )

        pulsed_inner_pen.setWidthF(
            max(
                1.0,
                float(self.host.inner_thickness) * scale,
            )
        )

        self._draw_lines(
            painter,
            mx,
            my,
            pulsed_outer_pen,
        )

        self._draw_lines(
            painter,
            mx,
            my,
            pulsed_inner_pen,
        )
