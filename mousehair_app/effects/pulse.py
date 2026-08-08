"""Pulsing Mousehair crosshair effect."""

import math

from PyQt5 import QtGui

from .base import CrosshairEffect, EffectSetting


class PulseCrosshairEffect(CrosshairEffect):
    """Render a gently breathing two-colour crosshair."""

    name = "pulse"
    display_name = "Pulse"

    settings = (
        EffectSetting(
            key="pulse_strength",
            label="Pulse strength",
            kind="float",
            default=0.15,
            minimum=0.0,
            maximum=0.75,
            step=0.05,
            decimals=2,
        ),
        EffectSetting(
            key="pulse_period",
            label="Pulse period",
            kind="float",
            default=1.5,
            minimum=0.25,
            maximum=10.0,
            step=0.25,
            decimals=2,
            suffix=" s",
        ),
    )

    def _pulse_scale(self):
        """Return a smooth thickness multiplier.

        Mousehair already maintains ``animation_phase`` continuously. Reusing it
        means Pulse needs no additional timer or state of its own.
        """
        phase = float(self.host.animation_phase)

        # animation_phase advances using Mousehair's animation-speed
        # clock. Convert the configured period into the equivalent phase span.
        pulse_period = max(
            0.05,
            float(
                getattr(
                    self.host,
                    "pulse_period",
                    1.5,
                )
            ),
        )

        animation_speed = max(
            1.0,
            float(
                getattr(
                    self.host,
                    "animate_speed",
                    180.0,
                )
            ),
        )

        phase_span = (
            pulse_period
            * animation_speed
        )

        radians = (
            phase / phase_span
        ) * math.tau

        strength = max(
            0.0,
            min(
                0.95,
                float(
                    getattr(
                        self.host,
                        "pulse_strength",
                        0.15,
                    )
                ),
            ),
        )

        return (
            1.0
            + strength * math.sin(radians)
        )

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
