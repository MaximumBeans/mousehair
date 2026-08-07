"""Mousehair overlay rendering pipeline."""

from PyQt5 import QtCore, QtGui

from .effects import (
    ArrowCrosshairEffect,
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
        """Return Mousehair's built-in Effects Engine registry.

        The registry maps stable effect names directly to effect classes.
        RenderPipelineMixin therefore does not need effect-specific wrapper
        methods and does not need to know how an individual effect draws.
        """
        return {
            "static": StaticCrosshairEffect,
            "sliding": SlidingCrosshairEffect,
            "arrows": ArrowCrosshairEffect,
        }

    def draw_crosshair(self, painter, mx, my, outer_pen, inner_pen):
        """Instantiate and render the currently selected crosshair effect."""
        effects = self._crosshair_renderers()

        effect_class = effects.get(
            self._crosshair_renderer_name(),
            StaticCrosshairEffect,
        )

        effect = effect_class(self)

        effect.render(
            painter,
            mx,
            my,
            outer_pen,
            inner_pen,
        )

