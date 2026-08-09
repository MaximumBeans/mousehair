"""
Asynchronous bridge to Mousehair's Cinnamon compositor magnifier extension.

The Cinnamon extension owns the actual compositor-native lens. The Python
application remains the authority for whether that lens should be visible and
how opaque it should be.

This module intentionally contains no fade calculation of its own. It merely
forwards Mousehair's already-computed ``current_alpha`` value over D-Bus.
"""

import subprocess

from PyQt5 import QtCore


class CinnamonLensBridge(QtCore.QObject):
    """Send non-blocking lens opacity updates to the Cinnamon extension."""

    DBUS_DESTINATION = "org.maximumbeans.Mousehair.Cinnamon"
    DBUS_OBJECT_PATH = "/org/maximumbeans/Mousehair/Cinnamon"
    DBUS_INTERFACE = "org.maximumbeans.Mousehair.Cinnamon"
    DBUS_OPACITY_METHOD = f"{DBUS_INTERFACE}.SetOpacity"
    DBUS_GEOMETRY_METHOD = f"{DBUS_INTERFACE}.SetGeometry"
    DBUS_RING_STYLE_METHOD = f"{DBUS_INTERFACE}.SetRingStyle"
    DBUS_HEARTBEAT_METHOD = f"{DBUS_INTERFACE}.Heartbeat"
    DBUS_POMODORO_STATE_METHOD = (
        f"{DBUS_INTERFACE}.SetPomodoroState"
    )
    DBUS_SYNC_STATE_METHOD = f"{DBUS_INTERFACE}.SynchroniseState"

    def __init__(self, parent=None):
        super().__init__(parent)

        # One QProcess is reused for all calls. D-Bus updates are extremely
        # small, but creating overlapping gdbus processes every animation frame
        # would still be wasteful.
        self._process = QtCore.QProcess(self)
        self._process.setProcessChannelMode(QtCore.QProcess.MergedChannels)
        self._process.finished.connect(self._on_process_finished)

        # When a call is already running, only the newest requested opacity is
        # retained. Intermediate fade values may safely be discarded because
        # the next value supersedes them.
        self._queued_opacity = None

        # Avoid sending identical values repeatedly during stationary frames.
        self._last_sent_opacity = None

        # A very small difference is visually meaningless and would create
        # unnecessary D-Bus traffic.
        self._minimum_change = 0.005

    def set_opacity(self, opacity, force=False):
        """Request a lens opacity between 0.0 and 1.0.

        The request is asynchronous. Failure to find the Cinnamon extension is
        harmless: gdbus exits and Mousehair continues normally.
        """
        try:
            opacity = float(opacity)
        except (TypeError, ValueError):
            opacity = 0.0

        opacity = max(0.0, min(1.0, opacity))

        if (
            not force
            and self._last_sent_opacity is not None
            and abs(opacity - self._last_sent_opacity) < self._minimum_change
        ):
            return

        if self._process.state() != QtCore.QProcess.NotRunning:
            self._queued_opacity = opacity
            return

        self._start_call(opacity)

    def _start_silent_detached_call(self, method, arguments=None):
        """Run a low-frequency gdbus call without inheriting terminal output."""
        command = [
            "gdbus",
            "call",
            "--session",
            "--dest",
            self.DBUS_DESTINATION,
            "--object-path",
            self.DBUS_OBJECT_PATH,
            "--method",
            method,
        ]

        if arguments:
            command.extend(str(argument) for argument in arguments)

        try:
            subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            # Cinnamon integration is optional. Mousehair must remain usable
            # when gdbus or the extension is unavailable.
            pass

    def set_geometry(self, gap, magnification):
        """Send the compositor lens radius and zoom factor to Cinnamon.

        Geometry changes happen only when settings are applied, so they do not
        need to share the high-frequency opacity process queue. A detached
        gdbus call keeps this operation asynchronous and independent of the
        painting loop.
        """
        try:
            gap = float(gap)
        except (TypeError, ValueError):
            gap = 100.0

        try:
            magnification = float(magnification)
        except (TypeError, ValueError):
            magnification = 2.0

        gap = max(1.0, gap)
        magnification = max(1.0, magnification)

        self._start_silent_detached_call(
            self.DBUS_GEOMETRY_METHOD,
            [
                format(gap, ".6f"),
                format(magnification, ".6f"),
            ],
        )

    def set_ring_style(
        self,
        radius,
        outer_thickness,
        inner_thickness,
        outer_colour,
        inner_colour,
    ):
        """Send the visible ring geometry and colours to Cinnamon.

        Ring changes occur only at startup or when settings are applied, so a
        detached gdbus call is appropriate here. Opacity animation continues
        through the bridge's existing queued process.
        """
        try:
            radius = max(0.5, float(radius))
        except (TypeError, ValueError):
            radius = 100.0

        try:
            outer_thickness = max(0.0, float(outer_thickness))
        except (TypeError, ValueError):
            outer_thickness = 4.0

        try:
            inner_thickness = max(0.0, float(inner_thickness))
        except (TypeError, ValueError):
            inner_thickness = 2.0

        outer_colour = str(outer_colour or "#000000")
        inner_colour = str(inner_colour or "#FFFFFF")

        self._start_silent_detached_call(
            self.DBUS_RING_STYLE_METHOD,
            [
                format(radius, ".6f"),
                format(outer_thickness, ".6f"),
                format(inner_thickness, ".6f"),
                outer_colour,
                inner_colour,
            ],
        )

    def synchronise_state(
        self,
        *,
        lens_radius,
        magnification,
        ring_radius,
        outer_thickness,
        inner_thickness,
        outer_colour,
        inner_colour,
        opacity,
    ):
        """Send one complete compositor-state snapshot.

        This method is intentionally safe to call periodically. If Cinnamon has
        restarted, the new extension instance receives enough information to
        rebuild its ring, magnifier geometry, colours, opacity, and heartbeat
        state without requiring Mousehair itself to restart.
        """
        self._start_silent_detached_call(
            self.DBUS_SYNC_STATE_METHOD,
            [
                format(float(lens_radius), ".6f"),
                format(float(magnification), ".6f"),
                format(float(ring_radius), ".6f"),
                format(float(outer_thickness), ".6f"),
                format(float(inner_thickness), ".6f"),
                str(outer_colour),
                str(inner_colour),
                format(float(opacity), ".6f"),
            ],
        )

    def set_pomodoro_state(
        self,
        *,
        enabled,
        phase,
        progress,
        remaining_seconds,
        focus_colour,
        break_colour,
        timer_text_size,
        ring_thickness,
        icon_size,
    ):
        """Send compositor-visible Pomodoro presentation state."""
        self._start_silent_detached_call(
            self.DBUS_POMODORO_STATE_METHOD,
            [
                "true" if enabled else "false",
                str(phase),
                format(float(progress), ".6f"),
                format(float(remaining_seconds), ".6f"),
                str(focus_colour),
                str(break_colour),
                str(int(timer_text_size)),
                format(float(ring_thickness), ".6f"),
                format(float(icon_size), ".6f"),
            ],
        )

    def heartbeat(self):
        """Tell Cinnamon that Mousehair is still running."""
        self._start_silent_detached_call(
            self.DBUS_HEARTBEAT_METHOD,
        )

    def hide(self, force=True):
        """Hide the Cinnamon lens without changing Mousehair's own settings."""
        self.set_opacity(0.0, force=force)

    def shutdown(self):
        """Make a best-effort request to hide the lens during application exit."""
        self._queued_opacity = None

        if self._process.state() != QtCore.QProcess.NotRunning:
            self._process.kill()
            self._process.waitForFinished(100)

        # Start one final detached call. It is independent of Mousehair's event
        # loop, so the application does not have to remain alive for completion.
        QtCore.QProcess.startDetached(
            "gdbus",
            [
                "call",
                "--session",
                "--dest",
                self.DBUS_DESTINATION,
                "--object-path",
                self.DBUS_OBJECT_PATH,
                "--method",
                self.DBUS_OPACITY_METHOD,
                "0.0",
            ],
        )

    def _start_call(self, opacity):
        """Launch one asynchronous gdbus SetOpacity request."""
        self._last_sent_opacity = opacity

        self._process.start(
            "gdbus",
            [
                "call",
                "--session",
                "--dest",
                self.DBUS_DESTINATION,
                "--object-path",
                self.DBUS_OBJECT_PATH,
                "--method",
                self.DBUS_OPACITY_METHOD,
                format(opacity, ".6f"),
            ],
        )

    def _on_process_finished(self, _exit_code, _exit_status):
        """Send the newest queued value after the previous call completes."""
        if self._queued_opacity is None:
            return

        queued_opacity = self._queued_opacity
        self._queued_opacity = None

        if (
            self._last_sent_opacity is None
            or abs(queued_opacity - self._last_sent_opacity)
            >= self._minimum_change
        ):
            self._start_call(queued_opacity)
