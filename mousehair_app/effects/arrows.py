"""Direction-arrow Mousehair crosshair effect."""

from PyQt5 import QtCore, QtGui

from .base import CrosshairEffect


class ArrowCrosshairEffect(CrosshairEffect):
    """Render Mousehair's inward-pointing outlined arrow reticule."""

    name = "arrows"

    def _draw_arrow_line(
        self,
        painter,
        start_x,
        start_y,
        end_x,
        end_y,
    ):
        """Draw one solid reticule arm with cursor-anchored outlined arrows."""
        host = self.host

        dx = end_x - start_x
        dy = end_y - start_y

        length = (
            dx * dx
            + dy * dy
        ) ** 0.5

        if length <= 0:
            return

        unit_x = dx / length
        unit_y = dy / length

        perpendicular_x = -unit_y
        perpendicular_y = unit_x

        outer_color = QtGui.QColor(
            host.outer_color
        )
        outer_color.setAlphaF(
            host.current_alpha
        )

        inner_color = QtGui.QColor(
            host.inner_color
        )
        inner_color.setAlphaF(
            host.current_alpha
        )

        outer_pen = QtGui.QPen(
            outer_color
        )
        outer_pen.setWidth(
            host.outer_thickness
        )
        outer_pen.setJoinStyle(
            QtCore.Qt.MiterJoin
        )

        inner_pen = QtGui.QPen(
            inner_color
        )
        inner_pen.setWidth(
            host.inner_thickness
        )

        # This pen is used when the centre line should be redrawn over the
        # arrow outline without protruding beyond the arrow tip.
        arrow_join_pen = QtGui.QPen(
            inner_pen
        )
        arrow_join_pen.setCapStyle(
            QtCore.Qt.FlatCap
        )

        # Match the arrow outline to the visible border around the centre line.
        arrow_outline_width = max(
            1.0,
            (
                float(host.outer_thickness)
                - float(host.inner_thickness)
            )
            / 2.0,
        )

        arrow_outline_pen = QtGui.QPen(
            outer_color
        )
        arrow_outline_pen.setWidthF(
            arrow_outline_width
        )
        arrow_outline_pen.setJoinStyle(
            QtCore.Qt.MiterJoin
        )

        painter.save()

        # Draw the solid dual-colour line first.
        painter.setPen(
            outer_pen
        )
        painter.setBrush(
            QtCore.Qt.NoBrush
        )
        painter.drawLine(
            QtCore.QPointF(
                start_x,
                start_y,
            ),
            QtCore.QPointF(
                end_x,
                end_y,
            ),
        )

        painter.setPen(
            inner_pen
        )
        painter.drawLine(
            QtCore.QPointF(
                start_x,
                start_y,
            ),
            QtCore.QPointF(
                end_x,
                end_y,
            ),
        )

        arrow_length = max(
            2.0,
            float(host.arrow_length),
        )

        arrow_half_width = max(
            1.0,
            float(host.arrow_width) / 2.0,
        )

        spacing = max(
            1.0,
            float(host.arrow_spacing),
        )

        first_offset = max(
            0.0,
            float(host.arrow_first_offset),
        )

        distance_from_cursor = first_offset

        painter.setPen(
            arrow_outline_pen
        )
        painter.setBrush(
            QtGui.QBrush(inner_color)
        )

        while distance_from_cursor < length:
            position = (
                length
                - distance_from_cursor
            )

            tip_x = (
                start_x
                + unit_x * position
            )
            tip_y = (
                start_y
                + unit_y * position
            )

            base_x = (
                tip_x
                - unit_x * arrow_length
            )
            base_y = (
                tip_y
                - unit_y * arrow_length
            )

            triangle = QtGui.QPolygonF([
                QtCore.QPointF(
                    tip_x,
                    tip_y,
                ),
                QtCore.QPointF(
                    base_x
                    + perpendicular_x * arrow_half_width,
                    base_y
                    + perpendicular_y * arrow_half_width,
                ),
                QtCore.QPointF(
                    base_x
                    - perpendicular_x * arrow_half_width,
                    base_y
                    - perpendicular_y * arrow_half_width,
                ),
            ])

            painter.drawPolygon(
                triangle
            )

            distance_from_cursor += spacing

        if not host.arrow_border_over_line:
            join_end_x = end_x
            join_end_y = end_y

            if first_offset <= 0.0:
                join_inset = max(
                    float(host.inner_thickness),
                    arrow_length * 0.45,
                )

                join_end_x -= (
                    unit_x * join_inset
                )
                join_end_y -= (
                    unit_y * join_inset
                )

            painter.setPen(
                arrow_join_pen
            )
            painter.setBrush(
                QtCore.Qt.NoBrush
            )
            painter.drawLine(
                QtCore.QPointF(
                    start_x,
                    start_y,
                ),
                QtCore.QPointF(
                    join_end_x,
                    join_end_y,
                ),
            )

        painter.restore()

    def _draw_lines(
        self,
        painter,
        mx,
        my,
    ):
        """Draw all four arrow-decorated reticule arms."""
        host = self.host
        gap = host.gap

        self._draw_arrow_line(
            painter,
            0,
            my,
            max(
                0,
                mx - gap,
            ),
            my,
        )

        self._draw_arrow_line(
            painter,
            host.width(),
            my,
            min(
                host.width(),
                mx + gap,
            ),
            my,
        )

        self._draw_arrow_line(
            painter,
            mx,
            0,
            mx,
            max(
                0,
                my - gap,
            ),
        )

        self._draw_arrow_line(
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
        """Draw all four direction-arrow arms.

        Generic outer and inner pens are unused because this effect creates
        specialised pens for arrow outlines, joins, and line redraws.
        """
        del outer_pen
        del inner_pen

        self._draw_lines(
            painter,
            mx,
            my,
        )
