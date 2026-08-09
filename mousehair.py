#!/usr/bin/env python3
import sys
import json
import os
import signal
import subprocess
from PyQt5 import QtWidgets, QtGui, QtCore
from Xlib import X, XK, display, error
from mousehair_app import (
    CinnamonLensBridge,
    CompositeCapture,
    RenderPipelineMixin,
    ReticleGeometry,
)

from mousehair_app.complications import (
    ComplicationManager,
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

        # Complications are persistent runtime objects. Timer state therefore
        # survives ordinary repaint cycles rather than being recreated every
        # frame.
        self.complications = ComplicationManager(
            self
        )

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
        pomodoro_menu = self.tray_menu.addMenu(
            "Pomodoro"
        )

        pomodoro_start_action = pomodoro_menu.addAction(
            "Start / Resume"
        )
        pomodoro_start_action.triggered.connect(
            self.complications.pomodoro.start
        )

        pomodoro_pause_action = pomodoro_menu.addAction(
            "Pause"
        )
        pomodoro_pause_action.triggered.connect(
            self.complications.pomodoro.pause
        )

        pomodoro_reset_action = pomodoro_menu.addAction(
            "Reset"
        )
        pomodoro_reset_action.triggered.connect(
            self.complications.pomodoro.reset
        )

        pomodoro_skip_action = pomodoro_menu.addAction(
            "Skip phase"
        )
        pomodoro_skip_action.triggered.connect(
            self.complications.pomodoro.skip
        )

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
        """Refresh Cinnamon with Mousehair's complete current state.

        The timer doubles as a self-healing synchronisation mechanism. If
        Cinnamon has restarted since the previous tick, the freshly loaded
        extension receives enough state to rebuild the ring and lens without
        requiring Mousehair to restart.
        """
        geometry = self._reticle_geometry()

        self.cinnamon_lens.synchronise_state(
            lens_radius=geometry.cinnamon_lens_radius,
            magnification=self.magnification,
            ring_radius=geometry.ring_centreline_radius,
            outer_thickness=geometry.outer_thickness,
            inner_thickness=geometry.inner_thickness,
            outer_colour=self.outer_color,
            inner_colour=self.inner_color,
            opacity=self._cinnamon_lens_opacity(),
        )

        pomodoro = self.complications.pomodoro
        pomodoro.update()
        pomodoro_snapshot = pomodoro.snapshot()

        self.cinnamon_lens.set_pomodoro_state(
            enabled=(
                self.pomodoro_enabled
                and self.magnifier_enabled
            ),
            phase=pomodoro_snapshot.phase,
            progress=pomodoro_snapshot.progress,
            remaining_seconds=(
                pomodoro_snapshot.remaining_seconds
            ),
            focus_colour=self.pomodoro_focus_colour,
            break_colour=self.pomodoro_break_colour,
            timer_text_size=self.pomodoro_timer_text_size,
            ring_thickness=self.pomodoro_ring_thickness,
            icon_size=self.pomodoro_icon_size,
        )

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

    def _reticle_geometry(self):
        """Return the shared geometry derived from current settings."""
        return ReticleGeometry.from_values(
            gap=self.gap,
            outer_thickness=self.outer_thickness,
            inner_thickness=self.inner_thickness,
        )

    def _ring_radius(self):
        """Return the common centreline radius for both visible ring strokes."""
        return self._reticle_geometry().ring_centreline_radius

    def _cinnamon_lens_radius(self):
        """Return the clear radius available inside the complete ring."""
        return self._reticle_geometry().cinnamon_lens_radius

    def _sync_cinnamon_ring_style(self):
        """Send shared reticle geometry and colours to Cinnamon."""
        geometry = self._reticle_geometry()

        self.cinnamon_lens.set_ring_style(
            radius=geometry.ring_centreline_radius,
            outer_thickness=geometry.outer_thickness,
            inner_thickness=geometry.inner_thickness,
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
            # ``crosshair_effect`` is the canonical Effects Engine
            # setting. The two older animation fields are retained so old
            # configuration files can still be interpreted correctly.
            'crosshair_effect': 'static',
            'animate_enabled': False,
            'animation_style': 'sliding',
            'animate_speed': 180,
            'animate_spacing': 32,
            'animate_segment_length': 14,
            'pulse_strength': 0.15,
            'pulse_period': 1.5,
            'arrow_first_offset': 20,
            'arrow_spacing': 40,
            'arrow_length': 14,
            'arrow_width': 12,
            'arrow_border_over_line': True,
            'ring_enabled': False,
            'magnifier_enabled': False,
            'magnification': 2.0,
            'pomodoro_enabled': True,
            'pomodoro_focus_minutes': 25,
            'pomodoro_short_break_minutes': 5,
            'pomodoro_long_break_minutes': 15,
            'pomodoro_focuses_before_long_break': 4,
            'pomodoro_auto_start_break': False,
            'pomodoro_auto_start_focus': False,
            'pomodoro_pause_after_cycle': True,
            'pomodoro_focus_colour': '#E53935',
            'pomodoro_break_colour': '#43A047',
            'pomodoro_timer_text_size': 16,
            'pomodoro_ring_thickness': 5.0,
            'pomodoro_icon_size': 14.0
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
        self.crosshair_effect = defaults['crosshair_effect']

        # Legacy aliases. These remain available while older code and config
        # files are phased out.
        self.animate_enabled = defaults['animate_enabled']
        self.animation_style = defaults['animation_style']
        self.animate_speed = defaults['animate_speed']
        self.animate_spacing = defaults['animate_spacing']
        self.animate_segment_length = defaults['animate_segment_length']
        self.pulse_strength = defaults['pulse_strength']
        self.pulse_period = defaults['pulse_period']
        self.arrow_first_offset = defaults['arrow_first_offset']
        self.arrow_spacing = defaults['arrow_spacing']
        self.arrow_length = defaults['arrow_length']
        self.arrow_border_over_line = defaults['arrow_border_over_line']
        self.arrow_width = defaults['arrow_width']
        self.ring_enabled = defaults['ring_enabled']
        self.magnifier_enabled = defaults['magnifier_enabled']
        self.magnification = defaults['magnification']
        self.pomodoro_enabled = defaults['pomodoro_enabled']
        self.pomodoro_focus_minutes = defaults['pomodoro_focus_minutes']
        self.pomodoro_short_break_minutes = defaults['pomodoro_short_break_minutes']
        self.pomodoro_long_break_minutes = defaults['pomodoro_long_break_minutes']
        self.pomodoro_focuses_before_long_break = defaults['pomodoro_focuses_before_long_break']
        self.pomodoro_auto_start_break = defaults['pomodoro_auto_start_break']
        self.pomodoro_auto_start_focus = defaults['pomodoro_auto_start_focus']
        self.pomodoro_pause_after_cycle = defaults['pomodoro_pause_after_cycle']
        self.pomodoro_focus_colour = defaults['pomodoro_focus_colour']
        self.pomodoro_break_colour = defaults['pomodoro_break_colour']
        self.pomodoro_timer_text_size = defaults['pomodoro_timer_text_size']
        self.pomodoro_ring_thickness = defaults['pomodoro_ring_thickness']
        self.pomodoro_icon_size = defaults['pomodoro_icon_size']
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
            legacy_animate_enabled = bool(
                data.get(
                    'animate_enabled',
                    self.animate_enabled,
                )
            )

            legacy_animation_style = str(
                data.get(
                    'animation_style',
                    self.animation_style,
                )
            )

            if 'crosshair_effect' in data:
                # New-format configuration.
                requested_effect = str(
                    data.get(
                        'crosshair_effect',
                        self.crosshair_effect,
                    )
                )
            else:
                # Migration from the pre-Effects-Engine configuration model.
                # animate_enabled=False historically meant Static regardless
                # of the stored animation_style value.
                requested_effect = (
                    legacy_animation_style
                    if legacy_animate_enabled
                    else "static"
                )

            requested_effect = (
                requested_effect
                .strip()
                .lower()
            )

            if requested_effect not in self._crosshair_renderers():
                requested_effect = "static"

            self.crosshair_effect = requested_effect

            # Keep the old attributes as derived aliases so older code remains
            # harmless while the migration is completed incrementally.
            self.animation_style = self.crosshair_effect
            self.animate_enabled = (
                self.crosshair_effect != "static"
            )
            self.animate_speed = int(data.get('animate_speed', self.animate_speed))
            self.animate_spacing = int(data.get('animate_spacing', self.animate_spacing))
            self.animate_segment_length = int(data.get('animate_segment_length', self.animate_segment_length))
            self.pulse_strength = float(data.get('pulse_strength', self.pulse_strength))
            self.pulse_period = float(data.get('pulse_period', self.pulse_period))
            self.arrow_first_offset = int(data.get('arrow_first_offset', self.arrow_first_offset))
            self.arrow_spacing = int(data.get('arrow_spacing', self.arrow_spacing))
            self.arrow_length = int(data.get('arrow_length', self.arrow_length))
            self.arrow_border_over_line = bool(data.get('arrow_border_over_line', self.arrow_border_over_line))
            self.arrow_width = int(data.get('arrow_width', self.arrow_width))
            self.ring_enabled = bool(data.get('ring_enabled', self.ring_enabled))
            self.magnifier_enabled = bool(data.get('magnifier_enabled', self.magnifier_enabled))
            self.magnification = float(data.get('magnification', self.magnification))
            self.pomodoro_enabled = bool(data.get('pomodoro_enabled', self.pomodoro_enabled))
            self.pomodoro_focus_minutes = int(
                data.get(
                    'pomodoro_focus_minutes',
                    self.pomodoro_focus_minutes,
                )
            )

            self.pomodoro_short_break_minutes = int(
                data.get(
                    'pomodoro_short_break_minutes',
                    data.get(
                        'pomodoro_break_minutes',
                        self.pomodoro_short_break_minutes,
                    ),
                )
            )

            self.pomodoro_long_break_minutes = int(
                data.get(
                    'pomodoro_long_break_minutes',
                    self.pomodoro_long_break_minutes,
                )
            )

            self.pomodoro_focuses_before_long_break = max(
                1,
                int(
                    data.get(
                        'pomodoro_focuses_before_long_break',
                        self.pomodoro_focuses_before_long_break,
                    )
                ),
            )

            legacy_auto_start = bool(
                data.get(
                    'pomodoro_auto_start',
                    False,
                )
            )

            self.pomodoro_auto_start_break = bool(
                data.get(
                    'pomodoro_auto_start_break',
                    legacy_auto_start,
                )
            )

            self.pomodoro_auto_start_focus = bool(
                data.get(
                    'pomodoro_auto_start_focus',
                    legacy_auto_start,
                )
            )

            self.pomodoro_pause_after_cycle = bool(
                data.get(
                    'pomodoro_pause_after_cycle',
                    self.pomodoro_pause_after_cycle,
                )
            )

            self.pomodoro_focus_colour = str(
                data.get(
                    'pomodoro_focus_colour',
                    self.pomodoro_focus_colour,
                )
            )

            self.pomodoro_break_colour = str(
                data.get(
                    'pomodoro_break_colour',
                    self.pomodoro_break_colour,
                )
            )

            self.pomodoro_timer_text_size = int(
                data.get(
                    'pomodoro_timer_text_size',
                    self.pomodoro_timer_text_size,
                )
            )
            self.pomodoro_ring_thickness = float(data.get('pomodoro_ring_thickness', self.pomodoro_ring_thickness))
            self.pomodoro_icon_size = float(data.get('pomodoro_icon_size', self.pomodoro_icon_size))
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
                'crosshair_effect': self.crosshair_effect,

                # Compatibility fields for older Mousehair builds.
                'animate_enabled': (
                    self.crosshair_effect != 'static'
                ),
                'animation_style': self.crosshair_effect,
                'animate_speed': self.animate_speed,
                'animate_spacing': self.animate_spacing,
                'animate_segment_length': self.animate_segment_length,
                'pulse_strength': self.pulse_strength,
                'pulse_period': self.pulse_period,
                'arrow_first_offset': self.arrow_first_offset,
                'arrow_spacing': self.arrow_spacing,
                'arrow_length': self.arrow_length,
                'arrow_border_over_line': self.arrow_border_over_line,
                'arrow_width': self.arrow_width,
                'ring_enabled': self.ring_enabled,
                'magnifier_enabled': self.magnifier_enabled,
                'magnification': self.magnification,
                'pomodoro_enabled': self.pomodoro_enabled,
                'pomodoro_focus_minutes': self.pomodoro_focus_minutes,
                'pomodoro_short_break_minutes': self.pomodoro_short_break_minutes,
                'pomodoro_long_break_minutes': self.pomodoro_long_break_minutes,
                'pomodoro_focuses_before_long_break': self.pomodoro_focuses_before_long_break,
                'pomodoro_auto_start_break': self.pomodoro_auto_start_break,
                'pomodoro_auto_start_focus': self.pomodoro_auto_start_focus,
                'pomodoro_pause_after_cycle': self.pomodoro_pause_after_cycle,
                'pomodoro_focus_colour': self.pomodoro_focus_colour,
                'pomodoro_break_colour': self.pomodoro_break_colour,
                'pomodoro_timer_text_size': self.pomodoro_timer_text_size,
                'pomodoro_ring_thickness': self.pomodoro_ring_thickness,
                'pomodoro_icon_size': self.pomodoro_icon_size,
                'hotkey_key': self.hotkey_key,
                'hotkey_modifiers': self.hotkey_modifiers
            }, f)

    def _gsettings_get(self, schema, key):
        """Read one Cinnamon setting through the gsettings command."""
        try:
            result = subprocess.run(
                [
                    "gsettings",
                    "get",
                    schema,
                    key,
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            return result.stdout.strip()

        except (
            OSError,
            subprocess.CalledProcessError,
        ) as exc:
            print(
                "Mousehair warning: could not read "
                f"{schema} {key}: {exc}",
                file=sys.stderr,
            )

            return None

    def _gsettings_set(self, schema, key, value):
        """Write one Cinnamon setting through the gsettings command."""
        try:
            subprocess.run(
                [
                    "gsettings",
                    "set",
                    schema,
                    key,
                    str(value),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            return True

        except (
            OSError,
            subprocess.CalledProcessError,
        ) as exc:
            print(
                "Mousehair warning: could not set "
                f"{schema} {key}: {exc}",
                file=sys.stderr,
            )

            return False

    def _begin_settings_magnifier_session(self):
        """Temporarily hand magnification to Cinnamon while Settings is open.

        The Mousehair Cinnamon extension already suppresses its pointer lens
        whenever Cinnamon's own full-screen magnifier is active.

        Preserve the user's original Cinnamon accessibility settings so they
        can be restored exactly when the Settings dialog closes.
        """
        applications_schema = (
            "org.cinnamon.desktop.a11y.applications"
        )

        magnifier_schema = (
            "org.cinnamon.desktop.a11y.magnifier"
        )

        enabled_key = (
            "screen-magnifier-enabled"
        )

        factor_key = (
            "mag-factor"
        )

        previous_enabled = self._gsettings_get(
            applications_schema,
            enabled_key,
        )

        previous_factor = self._gsettings_get(
            magnifier_schema,
            factor_key,
        )

        state = {
            "enabled": previous_enabled,
            "factor": previous_factor,
        }

        # Use approximately the same zoom level as Mousehair's pointer lens.
        # Cinnamon expects a floating-point GSettings value.
        self._gsettings_set(
            magnifier_schema,
            factor_key,
            float(self.magnification),
        )

        self._gsettings_set(
            applications_schema,
            enabled_key,
            "true",
        )

        return state

    def _end_settings_magnifier_session(self, state):
        """Restore Cinnamon magnification after Settings closes."""
        if not state:
            return

        applications_schema = (
            "org.cinnamon.desktop.a11y.applications"
        )

        magnifier_schema = (
            "org.cinnamon.desktop.a11y.magnifier"
        )

        enabled_key = (
            "screen-magnifier-enabled"
        )

        factor_key = (
            "mag-factor"
        )

        previous_factor = state.get(
            "factor"
        )

        previous_enabled = state.get(
            "enabled"
        )

        # Restore the factor first so Cinnamon never briefly reappears at the
        # temporary Mousehair zoom level.
        if previous_factor is not None:
            self._gsettings_set(
                magnifier_schema,
                factor_key,
                previous_factor,
            )

        if previous_enabled is not None:
            self._gsettings_set(
                applications_schema,
                enabled_key,
                previous_enabled,
            )

    def show_settings_dialog(self):
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Mousehair Settings")
        dialog.setMinimumWidth(520)

        dialog_layout = QtWidgets.QVBoxLayout(dialog)

        tabs = QtWidgets.QTabWidget()
        dialog_layout.addWidget(tabs)

        # ============================================================
        # GENERAL TAB
        # ============================================================

        general_scroll = QtWidgets.QScrollArea()
        general_scroll.setWidgetResizable(True)
        general_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        general_scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarAlwaysOff
        )

        general_widget = QtWidgets.QWidget()
        general_layout = QtWidgets.QFormLayout(general_widget)
        general_layout.setContentsMargins(12, 12, 12, 12)

        general_scroll.setWidget(general_widget)
        tabs.addTab(general_scroll, "General")

        start_with_system_chk = QtWidgets.QCheckBox(
            "Start with system"
        )
        start_with_system_chk.setChecked(
            self.start_with_system
        )

        alpha_spin = QtWidgets.QDoubleSpinBox()
        alpha_spin.setRange(0.0, 1.0)
        alpha_spin.setSingleStep(0.05)
        alpha_spin.setValue(self.alpha)

        gap_spin = QtWidgets.QSpinBox()
        gap_spin.setRange(0, 500)
        gap_spin.setValue(self.gap)

        outer_thick_spin = QtWidgets.QSpinBox()
        outer_thick_spin.setRange(1, 20)
        outer_thick_spin.setValue(
            self.outer_thickness
        )

        inner_thick_spin = QtWidgets.QSpinBox()
        inner_thick_spin.setRange(1, 20)
        inner_thick_spin.setValue(
            self.inner_thickness
        )

        pending_outer_color = self.outer_color
        pending_inner_color = self.inner_color

        outer_color_btn = QtWidgets.QPushButton()
        outer_color_btn.setStyleSheet(
            f"background-color: {pending_outer_color}"
        )

        def pick_outer():
            nonlocal pending_outer_color

            color = QtWidgets.QColorDialog.getColor(
                QtGui.QColor(
                    pending_outer_color
                ),
                dialog,
                "Select Outer Color",
            )

            if color.isValid():
                pending_outer_color = color.name()

                outer_color_btn.setStyleSheet(
                    f"background-color: {pending_outer_color}"
                )

        outer_color_btn.clicked.connect(
            pick_outer
        )

        inner_color_btn = QtWidgets.QPushButton()
        inner_color_btn.setStyleSheet(
            f"background-color: {pending_inner_color}"
        )

        def pick_inner():
            nonlocal pending_inner_color

            color = QtWidgets.QColorDialog.getColor(
                QtGui.QColor(
                    pending_inner_color
                ),
                dialog,
                "Select Inner Color",
            )

            if color.isValid():
                pending_inner_color = color.name()

                inner_color_btn.setStyleSheet(
                    f"background-color: {pending_inner_color}"
                )

        inner_color_btn.clicked.connect(
            pick_inner
        )

        ring_chk = QtWidgets.QCheckBox(
            "Enable ring reticule"
        )
        ring_chk.setChecked(
            self.ring_enabled
        )

        magnifier_chk = QtWidgets.QCheckBox(
            "Enable magnification inside ring"
        )
        magnifier_chk.setChecked(
            self.magnifier_enabled
        )

        magnification_spin = QtWidgets.QDoubleSpinBox()
        magnification_spin.setRange(
            1.25,
            5.0,
        )
        magnification_spin.setSingleStep(
            0.25
        )
        magnification_spin.setDecimals(2)
        magnification_spin.setValue(
            self.magnification
        )
        magnification_spin.setSuffix("x")

        fade_chk = QtWidgets.QCheckBox(
            "Enable fade"
        )
        fade_chk.setChecked(
            self.fade_enabled
        )

        fade_out_spin = QtWidgets.QSpinBox()
        fade_out_spin.setRange(
            0,
            5000,
        )
        fade_out_spin.setValue(
            self.fade_out_delay
        )
        fade_out_spin.setSuffix(" ms")

        fade_in_spin = QtWidgets.QSpinBox()
        fade_in_spin.setRange(
            0,
            5000,
        )
        fade_in_spin.setValue(
            self.fade_in_delay
        )
        fade_in_spin.setSuffix(" ms")

        fade_duration_spin = QtWidgets.QSpinBox()
        fade_duration_spin.setRange(
            0,
            5000,
        )
        fade_duration_spin.setValue(
            self.fade_duration
        )
        fade_duration_spin.setSuffix(" ms")

        general_layout.addRow(
            start_with_system_chk
        )
        general_layout.addRow(
            "Alpha:",
            alpha_spin,
        )
        general_layout.addRow(
            "Gap:",
            gap_spin,
        )
        general_layout.addRow(
            "Outer thickness:",
            outer_thick_spin,
        )
        general_layout.addRow(
            "Inner thickness:",
            inner_thick_spin,
        )
        general_layout.addRow(
            "Outer colour:",
            outer_color_btn,
        )
        general_layout.addRow(
            "Inner colour:",
            inner_color_btn,
        )
        general_layout.addRow(
            ring_chk
        )
        general_layout.addRow(
            magnifier_chk
        )
        general_layout.addRow(
            "Magnification:",
            magnification_spin,
        )
        general_layout.addRow(
            fade_chk
        )
        general_layout.addRow(
            "Fade out delay:",
            fade_out_spin,
        )
        general_layout.addRow(
            "Fade in delay:",
            fade_in_spin,
        )
        general_layout.addRow(
            "Fade duration:",
            fade_duration_spin,
        )

        # ============================================================
        # EFFECTS TAB
        # ============================================================

        effects_scroll = QtWidgets.QScrollArea()
        effects_scroll.setWidgetResizable(True)
        effects_scroll.setFrameShape(
            QtWidgets.QFrame.NoFrame
        )
        effects_scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarAlwaysOff
        )

        effects_widget = QtWidgets.QWidget()
        effects_layout = QtWidgets.QFormLayout(
            effects_widget
        )
        effects_layout.setContentsMargins(
            12,
            12,
            12,
            12,
        )

        effects_scroll.setWidget(
            effects_widget
        )
        tabs.addTab(
            effects_scroll,
            "Effects",
        )

        animation_style_combo = QtWidgets.QComboBox()

        for effect_class in self._crosshair_effect_classes():
            animation_style_combo.addItem(
                effect_class.display_name,
                effect_class.name,
            )

        animation_style_index = (
            animation_style_combo.findData(
                self.crosshair_effect
            )
        )

        if animation_style_index >= 0:
            animation_style_combo.setCurrentIndex(
                animation_style_index
            )

        effects_layout.addRow(
            "Crosshair effect:",
            animation_style_combo,
        )

        effect_settings_box = QtWidgets.QGroupBox(
            "Effect settings"
        )

        effect_settings_layout = QtWidgets.QFormLayout(
            effect_settings_box
        )

        effects_layout.addRow(
            effect_settings_box
        )

        effect_pending_values = {}

        for effect_class in self._crosshair_effect_classes():
            for setting in effect_class.settings:
                effect_pending_values.setdefault(
                    setting.key,
                    getattr(
                        self,
                        setting.key,
                        setting.default,
                    ),
                )

        effect_setting_widgets = {}

        def effect_widget_value(
            widget,
            setting,
        ):
            if setting.kind == "bool":
                return widget.isChecked()

            if setting.kind == "int":
                return int(
                    widget.value()
                )

            if setting.kind == "float":
                return float(
                    widget.value()
                )

            raise ValueError(
                "Unsupported effect setting kind: "
                f"{setting.kind}"
            )

        def capture_effect_settings():
            for key, item in (
                effect_setting_widgets.items()
            ):
                setting, widget = item

                effect_pending_values[key] = (
                    effect_widget_value(
                        widget,
                        setting,
                    )
                )

        def clear_effect_settings():
            while effect_settings_layout.rowCount():
                effect_settings_layout.removeRow(
                    0
                )

            effect_setting_widgets.clear()

        def create_effect_setting_widget(
            setting,
        ):
            value = effect_pending_values.get(
                setting.key,
                setting.default,
            )

            if setting.kind == "bool":
                widget = QtWidgets.QCheckBox()
                widget.setChecked(
                    bool(value)
                )
                return widget

            if setting.kind == "int":
                widget = QtWidgets.QSpinBox()

                widget.setRange(
                    int(
                        setting.minimum
                        if setting.minimum is not None
                        else -2147483647
                    ),
                    int(
                        setting.maximum
                        if setting.maximum is not None
                        else 2147483647
                    ),
                )

                if setting.step is not None:
                    widget.setSingleStep(
                        int(setting.step)
                    )

                if setting.suffix:
                    widget.setSuffix(
                        setting.suffix
                    )

                widget.setValue(
                    int(value)
                )

                return widget

            if setting.kind == "float":
                widget = QtWidgets.QDoubleSpinBox()

                widget.setRange(
                    float(
                        setting.minimum
                        if setting.minimum is not None
                        else -1000000.0
                    ),
                    float(
                        setting.maximum
                        if setting.maximum is not None
                        else 1000000.0
                    ),
                )

                widget.setDecimals(
                    max(
                        0,
                        int(
                            setting.decimals
                        ),
                    )
                )

                if setting.step is not None:
                    widget.setSingleStep(
                        float(setting.step)
                    )

                if setting.suffix:
                    widget.setSuffix(
                        setting.suffix
                    )

                widget.setValue(
                    float(value)
                )

                return widget

            raise ValueError(
                "Unsupported effect setting kind: "
                f"{setting.kind}"
            )

        def rebuild_effect_settings():
            capture_effect_settings()
            clear_effect_settings()

            effect_name = (
                animation_style_combo.currentData()
                or "static"
            )

            effect_class = (
                self._crosshair_renderers().get(
                    effect_name
                )
            )

            settings = (
                effect_class.settings
                if effect_class is not None
                else ()
            )

            for setting in settings:
                widget = (
                    create_effect_setting_widget(
                        setting
                    )
                )

                effect_setting_widgets[
                    setting.key
                ] = (
                    setting,
                    widget,
                )

                if setting.kind == "bool":
                    widget.setText(
                        setting.label
                    )
                    effect_settings_layout.addRow(
                        widget
                    )

                else:
                    effect_settings_layout.addRow(
                        f"{setting.label}:",
                        widget,
                    )

            effect_settings_box.setVisible(
                bool(settings)
            )

        animation_style_combo.currentIndexChanged.connect(
            rebuild_effect_settings
        )

        rebuild_effect_settings()

        # ============================================================
        # COMPLICATIONS TAB
        # ============================================================

        complications_widget = QtWidgets.QWidget()

        complications_layout = QtWidgets.QHBoxLayout(
            complications_widget
        )
        complications_layout.setContentsMargins(
            8,
            8,
            8,
            8,
        )

        tabs.addTab(
            complications_widget,
            "Complications",
        )

        # ------------------------------------------------------------
        # Navigation tree
        # ------------------------------------------------------------

        complications_tree = QtWidgets.QTreeWidget()
        complications_tree.setHeaderHidden(True)
        complications_tree.setRootIsDecorated(True)
        complications_tree.setMinimumWidth(170)
        complications_tree.setMaximumWidth(240)

        complications_pages = QtWidgets.QStackedWidget()

        complications_layout.addWidget(
            complications_tree
        )
        complications_layout.addWidget(
            complications_pages,
            1,
        )

        pomodoro_item = QtWidgets.QTreeWidgetItem(
            ["Pomodoro"]
        )

        pomodoro_timer_item = QtWidgets.QTreeWidgetItem(
            ["Timer"]
        )

        pomodoro_appearance_item = QtWidgets.QTreeWidgetItem(
            ["Appearance"]
        )

        pomodoro_sounds_item = QtWidgets.QTreeWidgetItem(
            ["Sounds"]
        )

        pomodoro_hotkeys_item = QtWidgets.QTreeWidgetItem(
            ["Hotkeys"]
        )

        pomodoro_placement_item = QtWidgets.QTreeWidgetItem(
            ["Placement"]
        )

        pomodoro_item.addChildren(
            [
                pomodoro_timer_item,
                pomodoro_appearance_item,
                pomodoro_sounds_item,
                pomodoro_hotkeys_item,
                pomodoro_placement_item,
            ]
        )

        complications_tree.addTopLevelItem(
            pomodoro_item
        )

        pomodoro_item.setExpanded(True)

        # ------------------------------------------------------------
        # Pomodoro overview
        # ------------------------------------------------------------

        pomodoro_overview_page = QtWidgets.QWidget()

        pomodoro_layout = QtWidgets.QFormLayout(
            pomodoro_overview_page
        )
        pomodoro_layout.setContentsMargins(
            16,
            16,
            16,
            16,
        )

        complications_pages.addWidget(
            pomodoro_overview_page
        )

        # ------------------------------------------------------------
        # Timer page
        # ------------------------------------------------------------

        pomodoro_timer_page = QtWidgets.QWidget()

        pomodoro_timer_layout = QtWidgets.QFormLayout(
            pomodoro_timer_page
        )
        pomodoro_timer_layout.setContentsMargins(
            16,
            16,
            16,
            16,
        )

        complications_pages.addWidget(
            pomodoro_timer_page
        )

        # ------------------------------------------------------------
        # Appearance page
        # ------------------------------------------------------------

        pomodoro_appearance_page = QtWidgets.QWidget()

        pomodoro_appearance_layout = QtWidgets.QFormLayout(
            pomodoro_appearance_page
        )
        pomodoro_appearance_layout.setContentsMargins(
            16,
            16,
            16,
            16,
        )

        complications_pages.addWidget(
            pomodoro_appearance_page
        )

        # ------------------------------------------------------------
        # Future Pomodoro sections
        # ------------------------------------------------------------

        def make_future_complication_page(title, description):
            page = QtWidgets.QWidget()

            layout = QtWidgets.QVBoxLayout(page)
            layout.setContentsMargins(
                16,
                16,
                16,
                16,
            )

            heading = QtWidgets.QLabel(
                f"<b>{title}</b>"
            )

            label = QtWidgets.QLabel(
                description
            )
            label.setWordWrap(True)

            layout.addWidget(heading)
            layout.addWidget(label)
            layout.addStretch(1)

            complications_pages.addWidget(
                page
            )

            return page

        pomodoro_sounds_page = (
            make_future_complication_page(
                "Pomodoro sounds",
                "Work and break start/end sounds will be configured here.",
            )
        )

        pomodoro_hotkeys_page = (
            make_future_complication_page(
                "Pomodoro hotkeys",
                "Global Pomodoro controls will be configured here.",
            )
        )

        pomodoro_placement_page = (
            make_future_complication_page(
                "Pomodoro placement",
                "Ring, countdown and icon placement controls will live here.",
            )
        )

        # Store the stacked-page index directly on each tree item.
        # QTreeWidgetItem is not hashable, so it cannot safely be used
        # as a dictionary key.
        page_role = (
            QtCore.Qt.UserRole
        )

        pomodoro_item.setData(
            0,
            page_role,
            0,
        )

        pomodoro_timer_item.setData(
            0,
            page_role,
            1,
        )

        pomodoro_appearance_item.setData(
            0,
            page_role,
            2,
        )

        pomodoro_sounds_item.setData(
            0,
            page_role,
            3,
        )

        pomodoro_hotkeys_item.setData(
            0,
            page_role,
            4,
        )

        pomodoro_placement_item.setData(
            0,
            page_role,
            5,
        )

        def select_complication_page(
            current,
            _previous,
        ):
            if current is None:
                return

            page_index = current.data(
                0,
                page_role,
            )

            if page_index is None:
                page_index = 0

            complications_pages.setCurrentIndex(
                int(page_index)
            )

        complications_tree.currentItemChanged.connect(
            select_complication_page
        )

        complications_tree.setCurrentItem(
            pomodoro_item
        )

        pomodoro_enabled_chk = QtWidgets.QCheckBox(
            "Enable Pomodoro complication"
        )
        pomodoro_enabled_chk.setChecked(
            self.pomodoro_enabled
        )

        pomodoro_focus_spin = QtWidgets.QSpinBox()
        pomodoro_focus_spin.setRange(
            1,
            180,
        )
        pomodoro_focus_spin.setValue(
            self.pomodoro_focus_minutes
        )
        pomodoro_focus_spin.setSuffix(
            " min"
        )

        pomodoro_short_break_spin = QtWidgets.QSpinBox()
        pomodoro_short_break_spin.setRange(
            1,
            60,
        )
        pomodoro_short_break_spin.setValue(
            self.pomodoro_short_break_minutes
        )
        pomodoro_short_break_spin.setSuffix(
            " min"
        )

        pomodoro_long_break_spin = QtWidgets.QSpinBox()
        pomodoro_long_break_spin.setRange(
            1,
            120,
        )
        pomodoro_long_break_spin.setValue(
            self.pomodoro_long_break_minutes
        )
        pomodoro_long_break_spin.setSuffix(
            " min"
        )

        pomodoro_cycle_spin = QtWidgets.QSpinBox()
        pomodoro_cycle_spin.setRange(
            1,
            20,
        )
        pomodoro_cycle_spin.setValue(
            self.pomodoro_focuses_before_long_break
        )

        pomodoro_auto_start_break_chk = QtWidgets.QCheckBox(
            "Automatically start breaks"
        )
        pomodoro_auto_start_break_chk.setChecked(
            self.pomodoro_auto_start_break
        )

        pomodoro_auto_start_focus_chk = QtWidgets.QCheckBox(
            "Automatically start next focus"
        )
        pomodoro_auto_start_focus_chk.setChecked(
            self.pomodoro_auto_start_focus
        )

        pomodoro_pause_after_cycle_chk = QtWidgets.QCheckBox(
            "Pause after a complete Pomodoro cycle"
        )
        pomodoro_pause_after_cycle_chk.setChecked(
            self.pomodoro_pause_after_cycle
        )

        pending_pomodoro_focus_colour = (
            self.pomodoro_focus_colour
        )

        pending_pomodoro_break_colour = (
            self.pomodoro_break_colour
        )

        pomodoro_focus_colour_btn = QtWidgets.QPushButton()
        pomodoro_focus_colour_btn.setStyleSheet(
            "background-color: "
            f"{pending_pomodoro_focus_colour}"
        )

        def pick_pomodoro_focus_colour():
            nonlocal pending_pomodoro_focus_colour

            colour = QtWidgets.QColorDialog.getColor(
                QtGui.QColor(
                    pending_pomodoro_focus_colour
                ),
                dialog,
                "Select Pomodoro Focus Colour",
            )

            if colour.isValid():
                pending_pomodoro_focus_colour = colour.name()

                pomodoro_focus_colour_btn.setStyleSheet(
                    "background-color: "
                    f"{pending_pomodoro_focus_colour}"
                )

        pomodoro_focus_colour_btn.clicked.connect(
            pick_pomodoro_focus_colour
        )

        pomodoro_break_colour_btn = QtWidgets.QPushButton()
        pomodoro_break_colour_btn.setStyleSheet(
            "background-color: "
            f"{pending_pomodoro_break_colour}"
        )

        def pick_pomodoro_break_colour():
            nonlocal pending_pomodoro_break_colour

            colour = QtWidgets.QColorDialog.getColor(
                QtGui.QColor(
                    pending_pomodoro_break_colour
                ),
                dialog,
                "Select Pomodoro Break Colour",
            )

            if colour.isValid():
                pending_pomodoro_break_colour = colour.name()

                pomodoro_break_colour_btn.setStyleSheet(
                    "background-color: "
                    f"{pending_pomodoro_break_colour}"
                )

        pomodoro_break_colour_btn.clicked.connect(
            pick_pomodoro_break_colour
        )

        pomodoro_timer_text_size_spin = QtWidgets.QSpinBox()
        pomodoro_timer_text_size_spin.setRange(
            8,
            72,
        )
        pomodoro_timer_text_size_spin.setValue(
            self.pomodoro_timer_text_size
        )
        pomodoro_timer_text_size_spin.setSuffix(
            " px"
        )

        pomodoro_ring_thickness_spin = QtWidgets.QSpinBox()
        pomodoro_ring_thickness_spin.setRange(
            1,
            60,
        )
        pomodoro_ring_thickness_spin.setSingleStep(
            1
        )
        pomodoro_ring_thickness_spin.setValue(
            int(round(self.pomodoro_ring_thickness))
        )
        pomodoro_ring_thickness_spin.setSuffix(
            " px"
        )

        pomodoro_icon_size_spin = QtWidgets.QSpinBox()
        pomodoro_icon_size_spin.setRange(
            6,
            120,
        )
        pomodoro_icon_size_spin.setSingleStep(
            1
        )
        pomodoro_icon_size_spin.setValue(
            int(round(self.pomodoro_icon_size))
        )
        pomodoro_icon_size_spin.setSuffix(
            " px"
        )

        # Overview
        pomodoro_layout.addRow(
            pomodoro_enabled_chk
        )

        pomodoro_description = QtWidgets.QLabel(
            "A pointer-centred focus timer with short and long breaks."
        )
        pomodoro_description.setWordWrap(True)

        pomodoro_layout.addRow(
            pomodoro_description
        )

        # Timer
        pomodoro_timer_layout.addRow(
            "Focus duration:",
            pomodoro_focus_spin,
        )

        pomodoro_timer_layout.addRow(
            "Short break duration:",
            pomodoro_short_break_spin,
        )

        pomodoro_timer_layout.addRow(
            "Long break duration:",
            pomodoro_long_break_spin,
        )

        pomodoro_timer_layout.addRow(
            "Focuses before long break:",
            pomodoro_cycle_spin,
        )

        pomodoro_timer_layout.addRow(
            pomodoro_auto_start_break_chk
        )

        pomodoro_timer_layout.addRow(
            pomodoro_auto_start_focus_chk
        )

        # User-facing wording describes behaviour rather than implementation.
        pomodoro_pause_after_cycle_chk.setText(
            "Stop after a full Pomodoro cycle"
        )

        pomodoro_timer_layout.addRow(
            pomodoro_pause_after_cycle_chk
        )

        # Appearance
        pomodoro_appearance_layout.addRow(
            "Focus ring colour:",
            pomodoro_focus_colour_btn,
        )

        pomodoro_appearance_layout.addRow(
            "Break ring colour:",
            pomodoro_break_colour_btn,
        )

        pomodoro_appearance_layout.addRow(
            "Countdown text size:",
            pomodoro_timer_text_size_spin,
        )

        pomodoro_appearance_layout.addRow(
            "Ring thickness:",
            pomodoro_ring_thickness_spin,
        )

        pomodoro_appearance_layout.addRow(
            "Tomato icon size:",
            pomodoro_icon_size_spin,
        )

        def update_pomodoro_controls():
            enabled = (
                pomodoro_enabled_chk.isChecked()
            )

            pomodoro_focus_spin.setEnabled(
                enabled
            )
            pomodoro_short_break_spin.setEnabled(
                enabled
            )
            pomodoro_long_break_spin.setEnabled(
                enabled
            )
            pomodoro_cycle_spin.setEnabled(
                enabled
            )
            pomodoro_auto_start_break_chk.setEnabled(
                enabled
            )
            pomodoro_auto_start_focus_chk.setEnabled(
                enabled
            )
            pomodoro_pause_after_cycle_chk.setEnabled(
                enabled
            )
            pomodoro_focus_colour_btn.setEnabled(
                enabled
            )
            pomodoro_break_colour_btn.setEnabled(
                enabled
            )
            pomodoro_timer_text_size_spin.setEnabled(
                enabled
            )
            pomodoro_ring_thickness_spin.setEnabled(
                enabled
            )
            pomodoro_icon_size_spin.setEnabled(
                enabled
            )

        pomodoro_enabled_chk.toggled.connect(
            update_pomodoro_controls
        )

        update_pomodoro_controls()

        # ============================================================
        # SHARED CONTROL LOGIC
        # ============================================================

        def update_ring_controls():
            ring_selected = (
                ring_chk.isChecked()
            )

            magnifier_chk.setEnabled(
                ring_selected
            )

            magnification_spin.setEnabled(
                ring_selected
                and magnifier_chk.isChecked()
            )

        ring_chk.toggled.connect(
            update_ring_controls
        )
        magnifier_chk.toggled.connect(
            update_ring_controls
        )

        update_ring_controls()

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok
            | QtWidgets.QDialogButtonBox.Apply
            | QtWidgets.QDialogButtonBox.Cancel
        )

        dialog_layout.addWidget(
            buttons
        )

        def apply_settings():
            self.start_with_system = (
                start_with_system_chk.isChecked()
            )

            self.alpha = alpha_spin.value()
            self.current_alpha = self.alpha

            self.gap = gap_spin.value()

            self.outer_thickness = (
                outer_thick_spin.value()
            )

            self.inner_thickness = (
                inner_thick_spin.value()
            )

            self.outer_color = (
                pending_outer_color
            )

            self.inner_color = (
                pending_inner_color
            )

            self.ring_enabled = (
                ring_chk.isChecked()
            )

            self.magnifier_enabled = (
                self.ring_enabled
                and magnifier_chk.isChecked()
            )

            self.magnification = (
                magnification_spin.value()
            )

            self.fade_enabled = (
                fade_chk.isChecked()
            )

            self.fade_out_delay = (
                fade_out_spin.value()
            )

            self.fade_in_delay = (
                fade_in_spin.value()
            )

            self.fade_duration = (
                fade_duration_spin.value()
            )

            self.crosshair_effect = (
                animation_style_combo.currentData()
                or "static"
            )

            self.animation_style = (
                self.crosshair_effect
            )

            self.animate_enabled = (
                self.crosshair_effect
                != "static"
            )

            capture_effect_settings()

            for key, value in (
                effect_pending_values.items()
            ):
                setattr(
                    self,
                    key,
                    value,
                )

            self.pomodoro_enabled = (
                pomodoro_enabled_chk.isChecked()
            )

            self.pomodoro_focus_minutes = (
                pomodoro_focus_spin.value()
            )

            self.pomodoro_short_break_minutes = (
                pomodoro_short_break_spin.value()
            )

            self.pomodoro_long_break_minutes = (
                pomodoro_long_break_spin.value()
            )

            self.pomodoro_focuses_before_long_break = (
                pomodoro_cycle_spin.value()
            )

            self.pomodoro_auto_start_break = (
                pomodoro_auto_start_break_chk.isChecked()
            )

            self.pomodoro_auto_start_focus = (
                pomodoro_auto_start_focus_chk.isChecked()
            )

            self.pomodoro_pause_after_cycle = (
                pomodoro_pause_after_cycle_chk.isChecked()
            )

            self.pomodoro_focus_colour = (
                pending_pomodoro_focus_colour
            )

            self.pomodoro_break_colour = (
                pending_pomodoro_break_colour
            )

            self.pomodoro_timer_text_size = (
                pomodoro_timer_text_size_spin.value()
            )

            self.pomodoro_ring_thickness = (
                pomodoro_ring_thickness_spin.value()
            )

            self.pomodoro_icon_size = (
                pomodoro_icon_size_spin.value()
            )

            self.save_settings()

            self.cinnamon_lens.set_geometry(
                self._cinnamon_lens_radius(),
                self.magnification,
            )

            self._sync_cinnamon_ring_style()
            self._sync_cinnamon_lens(
                force=True
            )

            self.update()

        def accept_settings():
            apply_settings()
            dialog.accept()

        buttons.accepted.connect(
            accept_settings
        )

        buttons.button(
            QtWidgets.QDialogButtonBox.Apply
        ).clicked.connect(
            apply_settings
        )

        buttons.rejected.connect(
            dialog.reject
        )

        screen = (
            QtWidgets.QApplication.primaryScreen()
        )

        if screen is not None:
            available_height = (
                screen.availableGeometry().height()
            )

            preferred_height = min(
                720,
                int(
                    available_height
                    * 0.9
                ),
            )

            dialog.resize(
                max(
                    520,
                    dialog.sizeHint().width(),
                ),
                preferred_height,
            )

        # Mousehair's compositor lens clones the desktop scene rather than
        # the final composited framebuffer. That means transient top-level
        # windows such as this Settings dialog can otherwise appear transparent
        # or "X-ray" through the lens.
        #
        # While Settings is open, use Cinnamon's true full-screen magnifier.
        # The Mousehair Cinnamon extension detects that state and suppresses
        # its own lens automatically while keeping the reticule available.
        settings_magnifier_state = (
            self._begin_settings_magnifier_session()
        )

        try:
            dialog.exec_()

        finally:
            self._end_settings_magnifier_session(
                settings_magnifier_state
            )

            # Force Mousehair's compositor state back across D-Bus immediately
            # rather than waiting for the next heartbeat after Cinnamon zoom
            # has been restored.
            self._sync_cinnamon_lens(
                force=True
            )

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

        # Complications paint last so they can deliberately sit above the
        # ordinary reticule where their placement policy calls for it.
        self.draw_complications(
            painter,
            mx,
            my,
        )

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    overlay = MousehairOverlay()
    overlay.show()
    sys.exit(app.exec_())
