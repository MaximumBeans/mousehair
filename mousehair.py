#!/usr/bin/env python3
import sys
import json
import os
import signal
from PyQt5 import QtWidgets, QtGui, QtCore
from Xlib import X, XK, display, error
from mousehair_app import (
    CinnamonLensBridge,
    CompositeCapture,
    RenderPipelineMixin,
)

CONFIG_PATH = os.path.expanduser('~/.config/mousehair/config.json')

class GlobalHotkey(QtCore.QObject):
    """Register and receive Mousehair's global X11 keyboard shortcut."""

    activated = QtCore.pyqtSignal()

    MODIFIER_MASKS = {
        "SHIFT": X.ShiftMask,
        "CTRL": X.ControlMask,
        "CONTROL": X.ControlMask,
        "ALT": X.Mod1Mask,
        "SUPER": X.Mod4Mask,
        "META": X.Mod4Mask,
    }

    def __init__(self, key="M", modifiers=None, parent=None):
        super().__init__(parent)

        self.dpy = display.Display()
        self.root = self.dpy.screen().root

        self.key_name = str(key or "M").upper()
        self.modifier_names = list(modifiers or ["SUPER", "SHIFT"])

        keysym = XK.string_to_keysym(self.key_name.lower())
        self.keycode = self.dpy.keysym_to_keycode(keysym)

        if not self.keycode:
            raise RuntimeError(
                f"Mousehair could not resolve hotkey key {self.key_name!r}."
            )

        self.modifiers = 0
        for name in self.modifier_names:
            mask = self.MODIFIER_MASKS.get(str(name).upper())
            if mask is not None:
                self.modifiers |= mask

        self._grabbed_masks = []
        self._register_grabs()

        # QSocketNotifier proved unreliable for this passive X11 key grab on
        # Cinnamon. A lightweight Qt timer keeps all event processing inside
        # the ordinary Qt event loop instead.
        #
        # Ten milliseconds is quick enough for the shortcut to feel immediate
        # while remaining negligible compared with Mousehair's 16 ms drawing
        # and fade timers.
        self.event_timer = QtCore.QTimer(self)
        self.event_timer.setInterval(10)
        self.event_timer.timeout.connect(self.process_events)
        self.event_timer.start()

    def _register_grabs(self):
        """Grab the shortcut with common lock-key combinations ignored.

        Caps Lock, Num Lock, and Scroll Lock can appear as extra modifier bits
        in X11 key events. Registering each combination keeps the shortcut
        working regardless of those lock states.
        """
        ignored_locks = [
            X.LockMask,
            X.Mod2Mask,
            X.Mod5Mask,
        ]

        lock_combinations = {0}
        for lock_mask in ignored_locks:
            lock_combinations |= {
                existing | lock_mask
                for existing in tuple(lock_combinations)
            }

        failed_masks = []

        for lock_mask in sorted(lock_combinations):
            grab_mask = self.modifiers | lock_mask
            catcher = error.CatchError(error.BadAccess)

            self.root.grab_key(
                self.keycode,
                grab_mask,
                False,
                X.GrabModeAsync,
                X.GrabModeAsync,
                onerror=catcher,
            )
            self.dpy.sync()

            if catcher.get_error() is None:
                self._grabbed_masks.append(grab_mask)
            else:
                failed_masks.append(grab_mask)

        if not self._grabbed_masks:
            shortcut = "+".join(
                [*self.modifier_names, self.key_name]
            )
            raise RuntimeError(
                f"Mousehair could not register {shortcut}. "
                "Another application or Cinnamon shortcut is already using it."
            )

        if failed_masks:
            print(
                "Mousehair warning: some lock-state variants of the global "
                "hotkey could not be registered.",
                file=sys.stderr,
            )

    def process_events(self):
        """Drain pending X11 events and emit the shortcut activation signal."""
        while self.dpy.pending_events():
            event = self.dpy.next_event()

            if (
                event.type == X.KeyPress
                and event.detail == self.keycode
            ):
                self.activated.emit()

    def close(self):
        """Release every passive key grab owned by this object."""
        if self.event_timer.isActive():
            self.event_timer.stop()

        for grab_mask in self._grabbed_masks:
            self.root.ungrab_key(self.keycode, grab_mask)

        self._grabbed_masks.clear()
        self.dpy.sync()

class MousehairOverlay(RenderPipelineMixin, QtWidgets.QWidget):
    # Unix signals cannot directly manipulate Qt widgets safely in a
    # portable way. This Qt signal carries the request into the normal
    # application event loop before visibility is changed.
    toggle_requested = QtCore.pyqtSignal()

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

        # Keep the Cinnamon compositor extension tied to this application's
        # lifecycle. If Mousehair disappears, the extension watchdog hides the
        # lens and ring after roughly 2.5 seconds.

        self.cinnamon_heartbeat_timer = QtCore.QTimer(self)
        self.cinnamon_heartbeat_timer.setInterval(1000)
        self.cinnamon_heartbeat_timer.timeout.connect(
            self._send_cinnamon_heartbeat
        )

        self.capture_provider = CompositeCapture()

        # The Cinnamon extension renders the compositor-native lens.
        # Mousehair supplies its effective opacity and visibility state.
        self.cinnamon_lens = CinnamonLensBridge(self)

        self.last_mouse_pos = QtGui.QCursor.pos()
        self.last_move_time = QtCore.QElapsedTimer()
        self.last_move_time.start()

        self.visible = True

        # Cinnamon owns Super-key combinations and proved unreliable when
        # Mousehair attempted to grab this shortcut directly through X11.
        #
        # The Cinnamon extension now registers Super+Shift+M natively and sends
        # SIGUSR1 to this process. The Python signal handler emits a Qt signal,
        # keeping the actual widget operation inside Qt's event loop.
        self.toggle_requested.connect(self.toggle_visibility)
        signal.signal(signal.SIGUSR1, self._handle_toggle_signal)

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

        QtWidgets.qApp.aboutToQuit.connect(self.cinnamon_lens.shutdown)

        # The Cinnamon extension cannot infer later settings changes merely
        # from the opacity stream. Send its initial viewport dimensions and
        # zoom factor explicitly.
        self.cinnamon_lens.set_geometry(
            self._cinnamon_lens_radius(),
            self.magnification,
        )
        self._sync_cinnamon_ring_style()
        self._send_cinnamon_heartbeat()
        self.cinnamon_heartbeat_timer.start()
        self._sync_cinnamon_lens(force=True)

    def _send_cinnamon_heartbeat(self):
        """Keep the compositor extension associated with this process."""
        self.cinnamon_lens.heartbeat()

    def _handle_toggle_signal(self, _signal_number, _stack_frame):
        """Receive the Cinnamon extension's SIGUSR1 toggle request."""
        self.toggle_requested.emit()

    def toggle_visibility(self):
        self.visible = not self.visible
        if self.visible:
            self.show()
            self.toggle_action.setText("Disable Mousehair")
        else:
            self.hide()
            self.toggle_action.setText("Enable Mousehair")

        self._sync_cinnamon_lens(force=True)

    def _cinnamon_lens_opacity(self):
        """Return the compositor lens opacity implied by Mousehair's state."""
        if not self.visible:
            return 0.0

        if not self.ring_enabled or not self.magnifier_enabled:
            return 0.0

        return self.current_alpha

    def _ring_radius(self):
        """Return the centreline radius used to draw the visible ring.

        ``self.gap`` is the distance from the pointer to the centreline endpoint
        of each crosshair arm. The outer line stroke is centred on that endpoint,
        so half of ``outer_thickness`` extends inward into the nominal gap.

        Moving the ring centreline inward by that same half-width makes the
        ring's outer edge meet the crosshair endpoints cleanly.
        """
        half_outer_width = max(
            0.0,
            float(self.outer_thickness) / 2.0,
        )

        return max(
            0.5,
            float(self.gap) - half_outer_width,
        )

    def _cinnamon_lens_radius(self):
        """Return the radius available inside the complete visible ring.

        The lens ends at the inner edge of the ring's outer stroke:

            ring centreline - outer_thickness / 2

        Since the ring centreline is already ``gap - outer_thickness / 2``,
        this is equivalent to ``gap - outer_thickness``.
        """
        half_outer_width = max(
            0.0,
            float(self.outer_thickness) / 2.0,
        )

        return max(
            1.0,
            self._ring_radius() - half_outer_width,
        )

    def _sync_cinnamon_ring_style(self):
        """Send the visible ring appearance to the Cinnamon extension."""
        self.cinnamon_lens.set_ring_style(
            radius=float(self.gap),
            outer_thickness=float(self.outer_thickness),
            inner_thickness=float(self.inner_thickness),
            outer_colour=self.outer_color,
            inner_colour=self.inner_color,
        )

    def _sync_cinnamon_lens(self, force=False):
        """Forward Mousehair's effective opacity to the Cinnamon extension."""
        self.cinnamon_lens.set_opacity(
            self._cinnamon_lens_opacity(),
            force=force,
        )

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
            'arrow_width': 12,
            'arrow_border_over_line': True,
            'ring_enabled': False,
            'magnifier_enabled': False,
            'magnification': 2.0
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
        self.arrow_border_over_line = defaults['arrow_border_over_line']
        self.arrow_width = defaults['arrow_width']
        self.ring_enabled = defaults['ring_enabled']
        self.magnifier_enabled = defaults['magnifier_enabled']
        self.magnification = defaults['magnification']
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
            self.arrow_border_over_line = bool(data.get('arrow_border_over_line', self.arrow_border_over_line))
            self.arrow_width = int(data.get('arrow_width', self.arrow_width))
            self.ring_enabled = bool(data.get('ring_enabled', self.ring_enabled))
            self.magnifier_enabled = bool(data.get('magnifier_enabled', self.magnifier_enabled))
            self.magnification = float(data.get('magnification', self.magnification))
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
                'arrow_border_over_line': self.arrow_border_over_line,
                'arrow_width': self.arrow_width,
                'ring_enabled': self.ring_enabled,
                'magnifier_enabled': self.magnifier_enabled,
                'magnification': self.magnification,
                'hotkey_key': self.hotkey_key,
                'hotkey_modifiers': self.hotkey_modifiers
            }, f)

    def show_settings_dialog(self):
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Mousehair Settings")
        dialog.setMinimumWidth(480)

        # The settings form scrolls when the available display height is too
        # small. The action buttons remain fixed beneath the scroll area.
        dialog_layout = QtWidgets.QVBoxLayout(dialog)

        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        settings_widget = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(settings_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll_area.setWidget(settings_widget)
        dialog_layout.addWidget(scroll_area)

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

        ring_chk = QtWidgets.QCheckBox("Enable ring reticule")
        ring_chk.setChecked(self.ring_enabled)

        magnifier_chk = QtWidgets.QCheckBox("Enable magnification inside ring")
        magnifier_chk.setChecked(self.magnifier_enabled)

        magnification_spin = QtWidgets.QDoubleSpinBox()
        magnification_spin.setRange(1.25, 5.0)
        magnification_spin.setSingleStep(0.25)
        magnification_spin.setDecimals(2)
        magnification_spin.setValue(self.magnification)
        magnification_spin.setSuffix("x")

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

        arrow_border_over_line_chk = QtWidgets.QCheckBox(
            "Draw arrow border over line"
        )
        arrow_border_over_line_chk.setChecked(self.arrow_border_over_line)
        layout.addRow("Alpha:", alpha_spin)
        layout.addRow("Gap:", gap_spin)
        layout.addRow("Outer thickness:", outer_thick_spin)
        layout.addRow("Inner thickness:", inner_thick_spin)
        layout.addRow("Outer color:", outer_color_btn)
        layout.addRow("Inner color:", inner_color_btn)
        layout.addRow(ring_chk)
        layout.addRow(magnifier_chk)
        layout.addRow("Magnification:", magnification_spin)
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
        layout.addRow(arrow_border_over_line_chk)

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
            arrow_border_over_line_chk.setVisible(arrows_selected)
            layout.labelForField(arrow_first_spin).setVisible(arrows_selected)
            layout.labelForField(arrow_spacing_spin).setVisible(arrows_selected)
            layout.labelForField(arrow_length_spin).setVisible(arrows_selected)
            layout.labelForField(arrow_width_spin).setVisible(arrows_selected)

        animation_style_combo.currentIndexChanged.connect(update_effect_controls)
        update_effect_controls()

        def update_ring_controls():
            ring_selected = ring_chk.isChecked()
            magnifier_chk.setEnabled(ring_selected)
            magnification_spin.setEnabled(
                ring_selected and magnifier_chk.isChecked()
            )

        ring_chk.toggled.connect(update_ring_controls)
        magnifier_chk.toggled.connect(update_ring_controls)
        update_ring_controls()

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok |
            QtWidgets.QDialogButtonBox.Apply |
            QtWidgets.QDialogButtonBox.Cancel
        )
        dialog_layout.addWidget(buttons)

        def apply_settings():
            self.start_with_system = start_with_system_chk.isChecked()
            self.alpha = alpha_spin.value()
            self.current_alpha = self.alpha
            self.gap = gap_spin.value()
            self.outer_thickness = outer_thick_spin.value()
            self.inner_thickness = inner_thick_spin.value()
            self.outer_color = pending_outer_color
            self.inner_color = pending_inner_color
            self.ring_enabled = ring_chk.isChecked()
            self.magnifier_enabled = (
                self.ring_enabled and magnifier_chk.isChecked()
            )
            self.magnification = magnification_spin.value()
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
            self.arrow_border_over_line = arrow_border_over_line_chk.isChecked()

            self.save_settings()

            # Resize and rescale the compositor-native lens immediately. The
            # extension no longer needs to be restarted after Gap or
            # Magnification changes.
            self.cinnamon_lens.set_geometry(
                self._cinnamon_lens_radius(),
                self.magnification,
            )
            self._sync_cinnamon_ring_style()
            self._sync_cinnamon_lens(force=True)
            self.update()

        def accept_settings():
            apply_settings()
            dialog.accept()

        buttons.accepted.connect(accept_settings)
        buttons.button(
            QtWidgets.QDialogButtonBox.Apply
        ).clicked.connect(apply_settings)
        buttons.rejected.connect(dialog.reject)

        # Keep the initial window within the usable desktop area. Any excess
        # form height is handled by the vertical scrollbar.
        screen = QtWidgets.QApplication.primaryScreen()
        if screen is not None:
            available_height = screen.availableGeometry().height()
            preferred_height = (
                settings_widget.sizeHint().height()
                + buttons.sizeHint().height()
                + 40
            )
            dialog.resize(
                dialog.sizeHint().width(),
                min(preferred_height, int(available_height * 0.9))
            )

        dialog.exec_()

    def update_fade(self):
        if not self.fade_enabled:
            self.current_alpha = self.alpha
            self._sync_cinnamon_lens()
            return

        now = QtGui.QCursor.pos()
        if now != self.last_mouse_pos:
            self.last_mouse_pos = now
            self.last_move_time.restart()
        elapsed = self.last_move_time.elapsed()

        if elapsed > self.fade_out_delay:
            if self.fade_duration <= 0:
                self.current_alpha = 0.0
            else:
                t = min(
                    1.0,
                    (elapsed - self.fade_out_delay) / self.fade_duration,
                )
                self.current_alpha = max(
                    0.0,
                    self.alpha * (1.0 - t),
                )
        else:
            self.current_alpha = self.alpha

        self._sync_cinnamon_lens()

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

        self.draw_magnifier(painter, mx, my)
        self.draw_crosshair(painter, mx, my, outer_pen, inner_pen)
        self.draw_ring(painter, mx, my, outer_pen, inner_pen)

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    overlay = MousehairOverlay()
    overlay.show()
    sys.exit(app.exec_())
