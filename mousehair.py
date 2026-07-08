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
            'fade_duration': 300
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

        outer_color_btn = QtWidgets.QPushButton()
        outer_color_btn.setStyleSheet(f"background-color: {self.outer_color}")
        def pick_outer():
            color = QtWidgets.QColorDialog.getColor(QtGui.QColor(self.outer_color), dialog, "Select Outer Color")
            if color.isValid():
                self.outer_color = color.name()
                outer_color_btn.setStyleSheet(f"background-color: {self.outer_color}")
        outer_color_btn.clicked.connect(pick_outer)

        inner_color_btn = QtWidgets.QPushButton()
        inner_color_btn.setStyleSheet(f"background-color: {self.inner_color}")
        def pick_inner():
            color = QtWidgets.QColorDialog.getColor(QtGui.QColor(self.inner_color), dialog, "Select Inner Color")
            if color.isValid():
                self.inner_color = color.name()
                inner_color_btn.setStyleSheet(f"background-color: {self.inner_color}")
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

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        layout.addRow(buttons)

        def apply():
            self.start_with_system = start_with_system_chk.isChecked()
            self.alpha = alpha_spin.value()
            self.gap = gap_spin.value()
            self.outer_thickness = outer_thick_spin.value()
            self.inner_thickness = inner_thick_spin.value()
            self.fade_enabled = fade_chk.isChecked()
            self.fade_out_delay = fade_out_spin.value()
            self.fade_in_delay = fade_in_spin.value()
            self.fade_duration = fade_duration_spin.value()
            self.save_settings()
            dialog.accept()

        buttons.accepted.connect(apply)
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

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        mx, my = QtGui.QCursor.pos().x(), QtGui.QCursor.pos().y()

        outer_color = QtGui.QColor(self.outer_color)
        outer_color.setAlphaF(self.current_alpha)
        pen = QtGui.QPen(outer_color)
        pen.setWidth(self.outer_thickness)
        painter.setPen(pen)
        painter.drawLine(0, my, max(0, mx - self.gap), my)
        painter.drawLine(mx + self.gap, my, self.width(), my)
        painter.drawLine(mx, 0, mx, max(0, my - self.gap))
        painter.drawLine(mx, my + self.gap, mx, self.height())

        inner_color = QtGui.QColor(self.inner_color)
        inner_color.setAlphaF(self.current_alpha)
        pen.setColor(inner_color)
        pen.setWidth(self.inner_thickness)
        painter.setPen(pen)
        painter.drawLine(0, my, max(0, mx - self.gap), my)
        painter.drawLine(mx + self.gap, my, self.width(), my)
        painter.drawLine(mx, 0, mx, max(0, my - self.gap))
        painter.drawLine(mx, my + self.gap, mx, self.height())

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    overlay = MousehairOverlay()
    overlay.show()
    sys.exit(app.exec_())
