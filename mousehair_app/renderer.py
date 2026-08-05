"""Mousehair overlay rendering pipeline."""

from PyQt5 import QtCore, QtGui


class RenderPipelineMixin:
    """Drawing methods mixed into the main overlay widget."""

    def draw_static_lines(self, painter, mx, my, pen):
        painter.setPen(pen)
        painter.drawLine(0, my, max(0, mx - self.gap), my)
        painter.drawLine(mx + self.gap, my, self.width(), my)
        painter.drawLine(mx, 0, mx, max(0, my - self.gap))
        painter.drawLine(mx, my + self.gap, mx, self.height())

    def draw_animated_segment_line(self, painter, start_x, start_y, end_x, end_y, toward_mouse_sign):
        dx = end_x - start_x
        dy = end_y - start_y
        length = int((dx * dx + dy * dy) ** 0.5)
        if length <= 0:
            return

        unit_x = dx / length
        unit_y = dy / length
        spacing = max(1, self.animate_spacing)
        segment_length = max(1, min(self.animate_segment_length, spacing))
        phase = self.animation_phase % spacing

        pos = phase - spacing
        while pos < length:
            seg_start = max(0, pos)
            seg_end = min(length, pos + segment_length)
            if seg_end > 0 and seg_start < length:
                x1 = start_x + unit_x * seg_start
                y1 = start_y + unit_y * seg_start
                x2 = start_x + unit_x * seg_end
                y2 = start_y + unit_y * seg_end
                painter.drawLine(int(x1), int(y1), int(x2), int(y2))
            pos += spacing

    def draw_animated_lines(self, painter, mx, my, pen):
        painter.setPen(pen)
        self.draw_animated_segment_line(painter, 0, my, max(0, mx - self.gap), my, 1)
        self.draw_animated_segment_line(painter, self.width(), my, min(self.width(), mx + self.gap), my, 1)
        self.draw_animated_segment_line(painter, mx, 0, mx, max(0, my - self.gap), 1)
        self.draw_animated_segment_line(painter, mx, self.height(), mx, min(self.height(), my + self.gap), 1)

    def draw_arrow_line(self, painter, start_x, start_y, end_x, end_y):
        """Draw one solid reticule arm with cursor-anchored outlined arrows."""
        dx = end_x - start_x
        dy = end_y - start_y
        length = (dx * dx + dy * dy) ** 0.5
        if length <= 0:
            return

        unit_x = dx / length
        unit_y = dy / length
        perpendicular_x = -unit_y
        perpendicular_y = unit_x

        outer_color = QtGui.QColor(self.outer_color)
        outer_color.setAlphaF(self.current_alpha)
        inner_color = QtGui.QColor(self.inner_color)
        inner_color.setAlphaF(self.current_alpha)

        outer_pen = QtGui.QPen(outer_color)
        outer_pen.setWidth(self.outer_thickness)
        outer_pen.setJoinStyle(QtCore.Qt.MiterJoin)

        inner_pen = QtGui.QPen(inner_color)
        inner_pen.setWidth(self.inner_thickness)

        # This separate pen is used only when the arrow border should not cross
        # the line. FlatCap prevents the redrawn line from projecting past the
        # arrow tip when the first arrow offset is zero.
        arrow_join_pen = QtGui.QPen(inner_pen)
        arrow_join_pen.setCapStyle(QtCore.Qt.FlatCap)

        # Match the arrow outline to the visible outer border around the
        # central line, rather than using the full outer-line thickness.
        arrow_outline_width = max(
            1.0,
            (float(self.outer_thickness) - float(self.inner_thickness)) / 2.0
        )
        arrow_outline_pen = QtGui.QPen(outer_color)
        arrow_outline_pen.setWidthF(arrow_outline_width)
        arrow_outline_pen.setJoinStyle(QtCore.Qt.MiterJoin)

        painter.save()

        # Draw the dual-colour solid line first.
        painter.setPen(outer_pen)
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawLine(
            QtCore.QPointF(start_x, start_y),
            QtCore.QPointF(end_x, end_y)
        )
        painter.setPen(inner_pen)
        painter.drawLine(
            QtCore.QPointF(start_x, start_y),
            QtCore.QPointF(end_x, end_y)
        )

        arrow_length = max(2.0, float(self.arrow_length))
        arrow_half_width = max(1.0, float(self.arrow_width) / 2.0)
        spacing = max(1.0, float(self.arrow_spacing))
        first_offset = max(0.0, float(self.arrow_first_offset))

        # Measure every arrow from the cursor-side line start. This keeps the
        # complete arrow pattern attached to the pointer and centre gap.
        distance_from_cursor = first_offset

        painter.setPen(arrow_outline_pen)
        painter.setBrush(QtGui.QBrush(inner_color))

        while distance_from_cursor < length:
            position = length - distance_from_cursor
            tip_x = start_x + unit_x * position
            tip_y = start_y + unit_y * position

            base_x = tip_x - unit_x * arrow_length
            base_y = tip_y - unit_y * arrow_length

            triangle = QtGui.QPolygonF([
                QtCore.QPointF(tip_x, tip_y),
                QtCore.QPointF(
                    base_x + perpendicular_x * arrow_half_width,
                    base_y + perpendicular_y * arrow_half_width
                ),
                QtCore.QPointF(
                    base_x - perpendicular_x * arrow_half_width,
                    base_y - perpendicular_y * arrow_half_width
                )
            ])
            painter.drawPolygon(triangle)
            distance_from_cursor += spacing

        if not self.arrow_border_over_line:
            # Redraw the centre line once after all arrowheads have been drawn.
            #
            # When the first arrow offset is zero, its sharp tip sits exactly
            # at the cursor-side end of the arm. Drawing the centre line all
            # the way to that point makes the rectangular line remain visible
            # beyond the narrowing white triangle. End the redraw safely inside
            # that first arrowhead instead.
            join_end_x = end_x
            join_end_y = end_y

            if first_offset <= 0.0:
                join_inset = max(
                    float(self.inner_thickness),
                    arrow_length * 0.45
                )
                join_end_x -= unit_x * join_inset
                join_end_y -= unit_y * join_inset

            painter.setPen(arrow_join_pen)
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawLine(
                QtCore.QPointF(start_x, start_y),
                QtCore.QPointF(join_end_x, join_end_y)
            )

        painter.restore()

    def draw_arrow_lines(self, painter, mx, my):
        """Draw all four solid arrow reticule arms."""
        self.draw_arrow_line(
            painter, 0, my, max(0, mx - self.gap), my
        )
        self.draw_arrow_line(
            painter, self.width(), my, min(self.width(), mx + self.gap), my
        )
        self.draw_arrow_line(
            painter, mx, 0, mx, max(0, my - self.gap)
        )
        self.draw_arrow_line(
            painter, mx, self.height(), mx, min(self.height(), my + self.gap)
        )

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

        diameter = float(self.gap * 2)

        ring_rect = QtCore.QRectF(
            float(mx) - float(self.gap),
            float(my) - float(self.gap),
            diameter,
            diameter,
        )

        painter.setBrush(QtCore.Qt.NoBrush)

        painter.setPen(outer_pen)
        painter.drawEllipse(ring_rect)

        painter.setPen(inner_pen)
        painter.drawEllipse(ring_rect)

    def draw_crosshair(self, painter, mx, my, outer_pen, inner_pen):
        """Draw the currently selected crosshair style.

        Keeping the style-selection logic in one method prevents paintEvent()
        from becoming a long chain of effect-specific conditions as more
        rendering styles are added.
        """
        if not self.animate_enabled:
            self.draw_static_lines(painter, mx, my, outer_pen)
            self.draw_static_lines(painter, mx, my, inner_pen)
            return

        if self.animation_style == "sliding":
            self.draw_animated_lines(painter, mx, my, outer_pen)
            self.draw_animated_lines(painter, mx, my, inner_pen)
            return

        if self.animation_style == "arrows":
            self.draw_arrow_lines(painter, mx, my)
            return

        # Fall back to the ordinary static crosshair if a configuration file
        # contains an unknown or no-longer-supported animation style.
        self.draw_static_lines(painter, mx, my, outer_pen)
        self.draw_static_lines(painter, mx, my, inner_pen)

