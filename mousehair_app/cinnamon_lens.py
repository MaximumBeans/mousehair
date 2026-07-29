"""
Asynchronous bridge to Mousehair's Cinnamon compositor magnifier extension.

The Cinnamon extension owns the actual compositor-native lens. The Python
application remains the authority for whether that lens should be visible and
how opaque it should be.

This module intentionally contains no fade calculation of its own. It merely
forwards Mousehair's already-computed ``current_alpha`` value over D-Bus.
"""

from PyQt5 import QtCore


class CinnamonLensBridge(QtCore.QObject):
    """Send non-blocking lens opacity updates to the Cinnamon extension."""

    DBUS_DESTINATION = "org.maximumbeans.Mousehair.Cinnamon"
    DBUS_OBJECT_PATH = "/org/maximumbeans/Mousehair/Cinnamon"
    DBUS_METHOD = "org.maximumbeans.Mousehair.Cinnamon.SetOpacity"

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
                self.DBUS_METHOD,
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
                self.DBUS_METHOD,
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
