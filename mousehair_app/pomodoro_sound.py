"""Non-blocking sound presentation for Pomodoro events."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

SOUND_ROOT = (
    PROJECT_ROOT
    / "assets"
    / "sounds"
)


class PomodoroSoundController:
    """Translate Pomodoro transition events into short audio cues."""

    DEFAULT_SOUNDS = {
        "focus_started": (
            SOUND_ROOT
            / "focus-start.wav"
        ),

        "focus_finished": (
            SOUND_ROOT
            / "focus-finished.wav"
        ),

        "short_break_started": (
            SOUND_ROOT
            / "break-start.wav"
        ),

        "long_break_started": (
            SOUND_ROOT
            / "break-start.wav"
        ),

        "short_break_finished": (
            SOUND_ROOT
            / "break-finished.wav"
        ),

        "long_break_finished": (
            SOUND_ROOT
            / "break-finished.wav"
        ),
    }

    def __init__(
        self,
        host,
    ):
        self.host = host

        self._player = (
            self._find_player()
        )

    def _find_player(self):
        """Return the first suitable non-interactive audio player."""
        candidates = (
            (
                "paplay",
                lambda path: [
                    "paplay",
                    str(path),
                ],
            ),
            (
                "pw-play",
                lambda path: [
                    "pw-play",
                    str(path),
                ],
            ),
            (
                "aplay",
                lambda path: [
                    "aplay",
                    "-q",
                    str(path),
                ],
            ),
            (
                "ffplay",
                lambda path: [
                    "ffplay",
                    "-nodisp",
                    "-autoexit",
                    "-loglevel",
                    "quiet",
                    str(path),
                ],
            ),
        )

        for executable, builder in candidates:
            if shutil.which(
                executable
            ):
                return builder

        return None

    def enabled(self):
        """Return whether Pomodoro sound cues are enabled."""
        return bool(
            getattr(
                self.host,
                "pomodoro_sound_enabled",
                True,
            )
        )

    def sound_for_event(
        self,
        event_name,
    ):
        """Return the configured or built-in sound path for an event."""
        return self.DEFAULT_SOUNDS.get(
            str(event_name)
        )

    def play(
        self,
        path,
    ):
        """Play a WAV asynchronously without blocking Mousehair rendering."""
        if self._player is None:
            return False

        path = Path(path)

        if not path.is_file():
            return False

        try:
            subprocess.Popen(
                self._player(
                    path
                ),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

        except OSError:
            return False

        return True

    def handle_pomodoro_event(
        self,
        event_name,
        _timer,
    ):
        """Pomodoro listener callback."""
        if not self.enabled():
            return

        sound = self.sound_for_event(
            event_name
        )

        if sound is not None:
            self.play(
                sound
            )
