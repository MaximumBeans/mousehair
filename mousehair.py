#!/usr/bin/env python3
import sys
import json
import os
from PyQt5 import QtWidgets, QtGui, QtCore
from Xlib import X, XK, display

CONFIG_PATH = os.path.expanduser('~/.config/mousehair/config.json')

class GlobalHotkey(QtCore.QObject):
    activated = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()
        self.dpy = display.Display()
        self.root = self.dpy.screen().root
        self.root.change_attributes(event_mask=X.KeyPressMask)

        self.keycode = self.dpy.keysym_to_keycode(XK.string_to_keysym('M'))
        self.modifiers = X.Mod4Mask | X.ShiftMask

        for mod in [self.modifiers, self.modifiers | X.LockMask, self.modifiers | X.Mod2Mask, self.modifiers | X.LockMask | X.Mod2Mask]:
            self.root.grab_key(self.keycode, mod, True, X.GrabModeAsync, X.GrabModeAsync)

        self.notifier = QtCore.QSocketNotifier(self.dpy.fileno(), QtCore.QSocketNotifier.Read)
        self.notifier.activated.connect(self.process_events)

    def process_events(self):
        while self.dpy.pending_events():
            event = self.dpy.next_event()
            if event.type == X.KeyPress and event.detail == self.keycode:
                self.activated.emit()
                self.dpy.allow_events(X.AsyncKeyboard, event.time)

class MousehairOverlay(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.load_settings()

        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.WindowStaysOnTopHint |
            QtCore.Qt.X11BypassWindowManagerHint |
            QtCore.Qt.WindowTransparentForInput
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)

        desktop = QtWidgets.QApplication.primaryScreen().geometry()
        self.setGeometry(desktop)

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(16)

        self.fade_timer = QtCore.QTimer()
        self.fade_timer.timeout.connect(self.update_fade)
        self.fade_timer.start(16)
        self.last_mouse_pos = QtGui.QCursor.pos()
        self.last_move_time = QtCore.QElapsedTimer()
        self.last_move_time.start()

        self.visible = True

        self.hotkey = GlobalHotkey()
        self.hotkey.activated.connect(self.toggle_visibility)

        self.tray_menu = QtWidgets.QMenu()
        self.toggle_action = self.tray_menu.addAction("Disable Mousehair")
        self.toggle_action.triggered.connect(self.toggle_visibility)
        settings_action = self.tray_menu.addAction("Settings")
        settings_action.triggered.connect(self.show_settings_dialog)
        quit_action = self.tray_menu.addAction("Quit")
        quit_action.triggered.connect(QtWidgets.qApp.quit)

        self.tray = QtWidgets.QSystemTrayIcon(QtGui.QIcon.fromTheme("input-mouse"), self)
        if self.tray.icon().isNull():
            self.tray.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_ComputerIcon))
        self.tray.setToolTip("Mousehair")
        self.tray.setContextMenu(self.tray_menu)
        self.tray.show()

    def toggle_visibility(self):
        self.visible = not self.visible
        if self.visible:
            self.show()
            self.toggle_action.setText("Disable Mousehair")
        else:
            self.hide()
            self.toggle_action.setText("Enable Mousehair")

    def load_settings(self):
        defaults = {
            'start_with_system': False,
            'hotkey_key': 'M',
            'hotkey_modifiers': ['SUPER', 'SHIFT'],
            'alpha': 1.0,
            'gap': 100,
            'outer_thickness': 4,
            'inner_thickness': 2,
            'outer_color': '#FF0000',
            'inner_color': '#FFFFFF',
            'fade_enabled': False,
            'fade_out_delay': 500,
            'fade_in_delay': 0,
            'fade_duration': 300,
            'animate_enabled': False,
            'animation_style': 'sliding',
            'animate_speed': 180,
            'animate_spacing': 32,
            'animate_segment_length': 14,
            'arrow_first_offset': 20,
            'arrow_spacing': 40,
            'arrow_length': 14,
            'arrow_width': 12
        }
        self.start_with_system = defaults['start_with_system']
        self.alpha = defaults['alpha']
        self.gap = defaults['gap']
        self.outer_thickness = defaults['outer_thickness']
        self.inner_thickness = defaults['inner_thickness']
        self.outer_color = defaults['outer_color']
        self.inner_color = defaults['inner_color']
        self.fade_enabled = defaults['fade_enabled']
        self.fade_out_delay = defaults['fade_out_delay']
        self.fade_in_delay = defaults['fade_in_delay']
        self.fade_duration = defaults['fade_duration']
        self.animate_enabled = defaults['animate_enabled']
        self.animation_style = defaults['animation_style']
        self.animate_speed = defaults['animate_speed']
        self.animate_spacing = defaults['animate_spacing']
        self.animate_segment_length = defaults['animate_segment_length']
        self.arrow_first_offset = defaults['arrow_first_offset']
        self.arrow_spacing = defaults['arrow_spacing']
        self.arrow_length = defaults['arrow_length']
        self.arrow_width = defaults['arrow_width']
        self.animation_phase = 0.0
        self.animation_clock = QtCore.QElapsedTimer()
        self.animation_clock.start()
        self.current_alpha = self.alpha
        self.hotkey_key = defaults['hotkey_key']
        self.hotkey_modifiers = defaults['hotkey_modifiers']

        valid = True
        data = {}
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, 'r') as f:
                    data = json.load(f)
            except:
                valid = False
        else:
            valid = False

        try:
            self.start_with_system = bool(data.get('start_with_system', self.start_with_system))
            self.alpha = float(data.get('alpha', self.alpha))
            self.gap = int(data.get('gap', self.gap))
            self.outer_thickness = int(data.get('outer_thickness', self.outer_thickness))
            self.inner_thickness = int(data.get('inner_thickness', self.inner_thickness))
            self.outer_color = str(data.get('outer_color', self.outer_color))
            self.inner_color = str(data.get('inner_color', self.inner_color))
            self.fade_enabled = bool(data.get('fade_enabled', self.fade_enabled))
            self.fade_out_delay = int(data.get('fade_out_delay', self.fade_out_delay))
            self.fade_in_delay = int(data.get('fade_in_delay', self.fade_in_delay))
            self.fade_duration = int(data.get('fade_duration', self.fade_duration))
            self.animate_enabled = bool(data.get('animate_enabled', self.animate_enabled))
            self.animation_style = str(data.get('animation_style', self.animation_style))
            self.animate_speed = int(data.get('animate_speed', self.animate_speed))
            self.animate_spacing = int(data.get('animate_spacing', self.animate_spacing))
            self.animate_segment_length = int(data.get('animate_segment_length', self.animate_segment_length))
            self.arrow_first_offset = int(data.get('arrow_first_offset', self.arrow_first_offset))
            self.arrow_spacing = int(data.get('arrow_spacing', self.arrow_spacing))
            self.arrow_length = int(data.get('arrow_length', self.arrow_length))
            self.arrow_width = int(data.get('arrow_width', self.arrow_width))
            self.hotkey_key = str(data.get('hotkey_key', self.hotkey_key))
            self.hotkey_modifiers = list(data.get('hotkey_modifiers', self.hotkey_modifiers))
        except:
            valid = False

        if not valid:
            self.save_settings()

    def save_settings(self):
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, 'w') as f:
            json.dump({
                'start_with_system': self.start_with_system,
                'alpha': self.alpha,
                'gap': self.gap,
                'outer_thickness': self.outer_thickness,
                'inner_thickness': self.inner_thickness,
                'outer_color': self.outer_color,
                'inner_color': self.inner_color,
                'fade_enabled': self.fade_enabled,
                'fade_out_delay': self.fade_out_delay,
                'fade_in_delay': self.fade_in_delay,
                'fade_duration': self.fade_duration,
                'animate_enabled': self.animate_enabled,
                'animation_style': self.animation_style,
                'animate_speed': self.animate_speed,
                'animate_spacing': self.animate_spacing,
                'animate_segment_length': self.animate_segment_length,
                'arrow_first_offset': self.arrow_first_offset,
                'arrow_spacing': self.arrow_spacing,
                'arrow_length': self.arrow_length,
                'arrow_width': self.arrow_width,
                'hotkey_key': self.hotkey_key,
                'hotkey_modifiers': self.hotkey_modifiers
            }, f)

    def show_settings_dialog(self):
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Mousehair Settings")
        dialog.setMinimumWidth(480)
        layout = QtWidgets.QFormLayout(dialog)

        start_with_system_chk = QtWidgets.QCheckBox("Start with system")
        start_with_system_chk.setChecked(self.start_with_system)

        alpha_spin = QtWidgets.QDoubleSpinBox()
        alpha_spin.setRange(0.0, 1.0)
        alpha_spin.setSingleStep(0.05)
        alpha_spin.setValue(self.alpha)

        gap_spin = QtWidgets.QSpinBox()
        gap_spin.setRange(0, 500)
        gap_spin.setValue(self.gap)

        outer_thick_spin = QtWidgets.QSpinBox()
        outer_thick_spin.setRange(1, 20)
        outer_thick_spin.setValue(self.outer_thickness)

        inner_thick_spin = QtWidgets.QSpinBox()
        inner_thick_spin.setRange(1, 20)
        inner_thick_spin.setValue(self.inner_thickness)

        pending_outer_color = self.outer_color
        pending_inner_color = self.inner_color

        outer_color_btn = QtWidgets.QPushButton()
        outer_color_btn.setStyleSheet(f"background-color: {pending_outer_color}")
        def pick_outer():
            nonlocal pending_outer_color
            color = QtWidgets.QColorDialog.getColor(
                QtGui.QColor(pending_outer_color),
                dialog,
                "Select Outer Color"
            )
            if color.isValid():
                pending_outer_color = color.name()
                outer_color_btn.setStyleSheet(
                    f"background-color: {pending_outer_color}"
                )
        outer_color_btn.clicked.connect(pick_outer)

        inner_color_btn = QtWidgets.QPushButton()
        inner_color_btn.setStyleSheet(f"background-color: {pending_inner_color}")
        def pick_inner():
            nonlocal pending_inner_color
            color = QtWidgets.QColorDialog.getColor(
                QtGui.QColor(pending_inner_color),
                dialog,
                "Select Inner Color"
            )
            if color.isValid():
                pending_inner_color = color.name()
                inner_color_btn.setStyleSheet(
                    f"background-color: {pending_inner_color}"
                )
        inner_color_btn.clicked.connect(pick_inner)

        fade_chk = QtWidgets.QCheckBox("Enable fade")
        fade_chk.setChecked(self.fade_enabled)
        fade_chk.setVisible(True)

        fade_out_spin = QtWidgets.QSpinBox()
        fade_out_spin.setRange(0, 5000)
        fade_out_spin.setValue(self.fade_out_delay)

        fade_in_spin = QtWidgets.QSpinBox()
        fade_in_spin.setRange(0, 5000)
        fade_in_spin.setValue(self.fade_in_delay)

        fade_duration_spin = QtWidgets.QSpinBox()
        fade_duration_spin.setRange(0, 5000)
        fade_duration_spin.setValue(self.fade_duration)

        animate_chk = QtWidgets.QCheckBox("Enable crawling line animation")
        animate_chk.setChecked(self.animate_enabled)
        animation_style_combo = QtWidgets.QComboBox()
        animation_style_combo.addItem("Sliding inward", "sliding")
        animation_style_combo.addItem("Direction arrows", "arrows")

        animation_style_index = animation_style_combo.findData(self.animation_style)
        if animation_style_index >= 0:
            animation_style_combo.setCurrentIndex(animation_style_index)

        animate_speed_spin = QtWidgets.QSpinBox()
        animate_speed_spin.setRange(10, 1000)
        animate_speed_spin.setValue(self.animate_speed)
        animate_speed_spin.setSuffix(" px/s")

        animate_spacing_spin = QtWidgets.QSpinBox()
        animate_spacing_spin.setRange(8, 200)
        animate_spacing_spin.setValue(self.animate_spacing)
        animate_spacing_spin.setSuffix(" px")

        animate_segment_spin = QtWidgets.QSpinBox()
        animate_segment_spin.setRange(2, 100)
        animate_segment_spin.setValue(self.animate_segment_length)
        animate_segment_spin.setSuffix(" px")

        arrow_first_spin = QtWidgets.QSpinBox()
        arrow_first_spin.setRange(0, 500)
        arrow_first_spin.setValue(self.arrow_first_offset)
        arrow_first_spin.setSuffix(" px")

        arrow_spacing_spin = QtWidgets.QSpinBox()
        arrow_spacing_spin.setRange(1, 500)
        arrow_spacing_spin.setValue(self.arrow_spacing)
        arrow_spacing_spin.setSuffix(" px")

        arrow_length_spin = QtWidgets.QSpinBox()
        arrow_length_spin.setRange(2, 200)
        arrow_length_spin.setValue(self.arrow_length)
        arrow_length_spin.setSuffix(" px")

        arrow_width_spin = QtWidgets.QSpinBox()
        arrow_width_spin.setRange(2, 200)
        arrow_width_spin.setValue(self.arrow_width)
        arrow_width_spin.setSuffix(" px")

        layout.addRow(start_with_system_chk)
        layout.addRow("Alpha:", alpha_spin)
        layout.addRow("Gap:", gap_spin)
        layout.addRow("Outer thickness:", outer_thick_spin)
        layout.addRow("Inner thickness:", inner_thick_spin)
        layout.addRow("Outer color:", outer_color_btn)
        layout.addRow("Inner color:", inner_color_btn)
        layout.addRow(fade_chk)
        layout.addRow("Fade out delay:", fade_out_spin)
        layout.addRow("Fade in delay:", fade_in_spin)
        layout.addRow("Fade duration:", fade_duration_spin)
        layout.addRow(animate_chk)
        layout.addRow("Animation style:", animation_style_combo)
        layout.addRow("Animation speed:", animate_speed_spin)
        layout.addRow("Animation spacing:", animate_spacing_spin)
        layout.addRow("Animation segment length:", animate_segment_spin)
        layout.addRow("First arrow at:", arrow_first_spin)
        layout.addRow("Arrow spacing:", arrow_spacing_spin)
        layout.addRow("Arrow length:", arrow_length_spin)
        layout.addRow("Arrow width:", arrow_width_spin)


        def update_effect_controls():
            arrows_selected = animation_style_combo.currentData() == "arrows"
            animate_speed_spin.setVisible(not arrows_selected)
            animate_spacing_spin.setVisible(not arrows_selected)
            animate_segment_spin.setVisible(not arrows_selected)
            layout.labelForField(animate_speed_spin).setVisible(not arrows_selected)
            layout.labelForField(animate_spacing_spin).setVisible(not arrows_selected)
            layout.labelForField(animate_segment_spin).setVisible(not arrows_selected)

            arrow_first_spin.setVisible(arrows_selected)
            arrow_spacing_spin.setVisible(arrows_selected)
            arrow_length_spin.setVisible(arrows_selected)
            arrow_width_spin.setVisible(arrows_selected)
            layout.labelForField(arrow_first_spin).setVisible(arrows_selected)
            layout.labelForField(arrow_spacing_spin).setVisible(arrows_selected)
            layout.labelForField(arrow_length_spin).setVisible(arrows_selected)
            layout.labelForField(arrow_width_spin).setVisible(arrows_selected)

        animation_style_combo.currentIndexChanged.connect(update_effect_controls)
        update_effect_controls()

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok |
            QtWidgets.QDialogButtonBox.Apply |
            QtWidgets.QDialogButtonBox.Cancel
        )
        layout.addRow(buttons)

        def apply_settings():
            self.start_with_system = start_with_system_chk.isChecked()
            self.alpha = alpha_spin.value()
            self.current_alpha = self.alpha
            self.gap = gap_spin.value()
            self.outer_thickness = outer_thick_spin.value()
            self.inner_thickness = inner_thick_spin.value()
            self.outer_color = pending_outer_color
            self.inner_color = pending_inner_color
            self.fade_enabled = fade_chk.isChecked()
            self.fade_out_delay = fade_out_spin.value()
            self.fade_in_delay = fade_in_spin.value()
            self.fade_duration = fade_duration_spin.value()
            self.animate_enabled = animate_chk.isChecked()
            self.animation_style = animation_style_combo.currentData()
            self.animate_speed = animate_speed_spin.value()
            self.animate_spacing = animate_spacing_spin.value()
            self.animate_segment_length = animate_segment_spin.value()
            self.arrow_first_offset = arrow_first_spin.value()
            self.arrow_spacing = arrow_spacing_spin.value()
            self.arrow_length = arrow_length_spin.value()
            self.arrow_width = arrow_width_spin.value()
            self.save_settings()
            self.update()

        def accept_settings():
            apply_settings()
            dialog.accept()

        buttons.accepted.connect(accept_settings)
        buttons.button(
            QtWidgets.QDialogButtonBox.Apply
        ).clicked.connect(apply_settings)
        buttons.rejected.connect(dialog.reject)
        dialog.exec_()

    def update_fade(self):
        if not self.fade_enabled:
            return

        now = QtGui.QCursor.pos()
        if now != self.last_mouse_pos:
            self.last_mouse_pos = now
            self.last_move_time.restart()
        elapsed = self.last_move_time.elapsed()

        if elapsed > self.fade_out_delay:
            t = min(1.0, (elapsed - self.fade_out_delay) / self.fade_duration)
            self.current_alpha = max(0.0, self.alpha * (1.0 - t))
        else:
            self.current_alpha = self.alpha

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

    def paintEvent(self, event):
        if self.animate_enabled:
            elapsed = self.animation_clock.restart()
            self.animation_phase += (elapsed / 1000.0) * self.animate_speed

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        mx, my = QtGui.QCursor.pos().x(), QtGui.QCursor.pos().y()

        outer_color = QtGui.QColor(self.outer_color)
        outer_color.setAlphaF(self.current_alpha)
        outer_pen = QtGui.QPen(outer_color)
        outer_pen.setWidth(self.outer_thickness)

        inner_color = QtGui.QColor(self.inner_color)
        inner_color.setAlphaF(self.current_alpha)
        inner_pen = QtGui.QPen(inner_color)
        inner_pen.setWidth(self.inner_thickness)

        self.draw_crosshair(painter, mx, my, outer_pen, inner_pen)

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    overlay = MousehairOverlay()
    overlay.show()
    sys.exit(app.exec_())
