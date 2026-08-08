"""Mousehair overlay rendering pipeline."""

from PyQt5 import QtCore, QtGui

from .effects import (
    ArrowCrosshairEffect,
    PulseCrosshairEffect,
    SlidingCrosshairEffect,
    StaticCrosshairEffect,
)


class RenderPipelineMixin:
    """Drawing methods mixed into the main overlay widget."""

    def draw_magnifier(self, painter, mx, my):
        """Draw a frame supplied by the configured capture provider."""
        frame = self.capture_provider.capture(
            cursor_x=mx,
            cursor_y=my,
            radius=self.gap,
            magnification=self.magnification,
        )
        if frame is None:
            return

        destination_diameter = float(self.gap * 2)
        destination = QtCore.QRectF(
            mx - self.gap,
            my - self.gap,
            destination_diameter,
            destination_diameter,
        )

        painter.save()
        if self.alpha > 0.0:
            painter.setOpacity(max(0.0, min(1.0, self.current_alpha / self.alpha)))
        else:
            painter.setOpacity(0.0)

        clip_path = QtGui.QPainterPath()
        clip_path.addEllipse(destination)
        painter.setClipPath(clip_path, QtCore.Qt.IntersectClip)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
        painter.drawImage(destination, frame, QtCore.QRectF(frame.rect()))
        painter.restore()

    def draw_ring(self, painter, mx, my, outer_pen, inner_pen):
        """Draw the optional two-colour PyQt fallback ring.

        The Cinnamon compositor extension supplies the visible ring whenever
        its native magnifier is active. This PyQt ring remains useful when the
        compositor lens is disabled or unavailable.
        """
        if not self.ring_enabled or self.gap <= 0:
            return

        # Cinnamon draws the visible ring above its compositor-native lens.
        # Drawing the PyQt ring simultaneously creates duplicate concentric
        # outlines.
        if self.magnifier_enabled:
            return

        geometry = self._reticle_geometry()
        radius = geometry.ring_centreline_radius
        diameter = geometry.ring_centreline_diameter

        ring_rect = QtCore.QRectF(
            float(mx) - radius,
            float(my) - radius,
            diameter,
            diameter,
        )

        painter.setBrush(QtCore.Qt.NoBrush)

        painter.setPen(outer_pen)
        painter.drawEllipse(ring_rect)

        painter.setPen(inner_pen)
        painter.drawEllipse(ring_rect)

    def _crosshair_renderer_name(self):
        """Return the renderer selected by the current settings."""
        if not self.animate_enabled:
            return "static"

        return str(
            self.animation_style or "static"
        ).strip().lower()

    def _crosshair_renderers(self):
        """Return Mousehair's built-in Effects Engine class registry."""
        return {
            effect_class.name: effect_class
            for effect_class in self._crosshair_effect_classes()
        }

    def _crosshair_effect_instances(self):
        """Return one persistent instance of every built-in effect.

        Paint events can occur many times per second. Effects are therefore
        instantiated once for this overlay and then reused instead of creating
        short-lived Python objects for every frame.

        Persistent instances also give future effects somewhere appropriate to
        keep lightweight animation state without leaking it into the main
        Mousehair widget.
        """
        instances = getattr(
            self,
            "_effect_instance_cache",
            None,
        )

        if instances is None:
            instances = {
                name: effect_class(self)
                for name, effect_class
                in self._crosshair_renderers().items()
            }

            self._effect_instance_cache = instances

        return instances

    def _crosshair_effect_classes(self):
        """Return built-in effects in their preferred UI order."""
        return (
            StaticCrosshairEffect,
            SlidingCrosshairEffect,
            ArrowCrosshairEffect,
            PulseCrosshairEffect,
        )

    def draw_crosshair(self, painter, mx, my, outer_pen, inner_pen):
        """Render the selected effect using its persistent instance."""
        effects = self._crosshair_effect_instances()

        effect = effects.get(
            self._crosshair_renderer_name(),
            effects["static"],
        )

        effect.render(
            painter,
            mx,
            my,
            outer_pen,
            inner_pen,
        )

