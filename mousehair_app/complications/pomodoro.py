"""Pomodoro timer complication for Mousehair."""

from dataclasses import dataclass
import time

from .base import (
    Complication,
    ComplicationSetting,
)

from .placement import ComplicationPlacement


PHASE_FOCUS = "focus"
PHASE_BREAK = "break"

STATE_IDLE = "idle"
STATE_RUNNING = "running"
STATE_PAUSED = "paused"


@dataclass(frozen=True)
class PomodoroSnapshot:
    """Read-only presentation state for the Pomodoro complication."""

    phase: str
    state: str

    duration_seconds: float
    remaining_seconds: float

    progress: float

    completed_focus_sessions: int


class PomodoroComplication(Complication):
    """Pointer-centred Pomodoro timer.

    Timer arithmetic deliberately lives independently from Qt rendering. This
    keeps it deterministic, testable, and suitable for both the PyQt overlay
    and the Cinnamon compositor extension.
    """

    name = "pomodoro"
    display_name = "Pomodoro"

    settings = (
        ComplicationSetting(
            key="pomodoro_focus_minutes",
            label="Focus duration",
            kind="int",
            default=25,
            minimum=1,
            maximum=180,
            step=1,
            suffix=" min",
        ),
        ComplicationSetting(
            key="pomodoro_break_minutes",
            label="Break duration",
            kind="int",
            default=5,
            minimum=1,
            maximum=60,
            step=1,
            suffix=" min",
        ),
        ComplicationSetting(
            key="pomodoro_auto_start",
            label="Automatically start next phase",
            kind="bool",
            default=False,
        ),
    )

    # A complete ring immediately inside the accessibility reticule.
    default_placement = ComplicationPlacement(
        radial_zone="inside",
        radial_offset=0.0,
        angle=0.0,
        span=360.0,
        collision="ignore",
    )

    def __init__(
        self,
        host,
        placement=None,
        clock=None,
    ):
        super().__init__(
            host,
            placement=placement,
        )

        # time.monotonic() is immune to wall-clock corrections and daylight
        # saving changes, which is exactly what a countdown timer needs.
        self._clock = (
            clock
            if clock is not None
            else time.monotonic
        )

        self.phase = PHASE_FOCUS
        self.state = STATE_IDLE

        self.completed_focus_sessions = 0

        self._started_at = None
        self._paused_remaining = None

    def _setting(
        self,
        key,
        default,
    ):
        """Read one host setting with a safe fallback."""
        return getattr(
            self.host,
            key,
            default,
        )

    def phase_duration_seconds(
        self,
        phase=None,
    ):
        """Return the configured duration of a phase in seconds."""
        phase = (
            self.phase
            if phase is None
            else phase
        )

        if phase == PHASE_FOCUS:
            minutes = self._setting(
                "pomodoro_focus_minutes",
                25,
            )

        elif phase == PHASE_BREAK:
            minutes = self._setting(
                "pomodoro_break_minutes",
                5,
            )

        else:
            raise ValueError(
                f"Unknown Pomodoro phase: {phase}"
            )

        return max(
            1.0,
            float(minutes) * 60.0,
        )

    def remaining_seconds(
        self,
        now=None,
    ):
        """Return countdown time remaining in the current phase."""
        duration = self.phase_duration_seconds()

        if self.state == STATE_IDLE:
            return duration

        if self.state == STATE_PAUSED:
            if self._paused_remaining is None:
                return duration

            return max(
                0.0,
                min(
                    duration,
                    float(self._paused_remaining),
                ),
            )

        if self._started_at is None:
            return duration

        if now is None:
            now = self._clock()

        elapsed = max(
            0.0,
            float(now)
            - float(self._started_at),
        )

        return max(
            0.0,
            duration - elapsed,
        )

    def progress(
        self,
        now=None,
    ):
        """Return elapsed phase progress in the range 0.0 to 1.0."""
        duration = self.phase_duration_seconds()

        remaining = self.remaining_seconds(
            now=now,
        )

        return max(
            0.0,
            min(
                1.0,
                1.0
                - remaining / duration,
            ),
        )

    def start(self):
        """Start or resume the current phase."""
        if self.state == STATE_RUNNING:
            return

        now = self._clock()

        if (
            self.state == STATE_PAUSED
            and self._paused_remaining is not None
        ):
            duration = self.phase_duration_seconds()

            elapsed = (
                duration
                - self._paused_remaining
            )

            self._started_at = (
                now
                - elapsed
            )

        else:
            self._started_at = now

        self._paused_remaining = None
        self.state = STATE_RUNNING

    def pause(self):
        """Pause the countdown without losing elapsed progress."""
        if self.state != STATE_RUNNING:
            return

        now = self._clock()

        self._paused_remaining = (
            self.remaining_seconds(
                now=now,
            )
        )

        self._started_at = None
        self.state = STATE_PAUSED

    def toggle(self):
        """Toggle between running and paused states."""
        if self.state == STATE_RUNNING:
            self.pause()
        else:
            self.start()

    def reset(self):
        """Reset to a fresh, idle focus session."""
        self.phase = PHASE_FOCUS
        self.state = STATE_IDLE

        self._started_at = None
        self._paused_remaining = None

    def reset_current_phase(self):
        """Reset the current phase without switching focus/break."""
        self.state = STATE_IDLE

        self._started_at = None
        self._paused_remaining = None

    def _advance_phase(self):
        """Move from focus to break or break to focus."""
        if self.phase == PHASE_FOCUS:
            self.completed_focus_sessions += 1
            self.phase = PHASE_BREAK

        else:
            self.phase = PHASE_FOCUS

        self._started_at = None
        self._paused_remaining = None

        auto_start = bool(
            self._setting(
                "pomodoro_auto_start",
                False,
            )
        )

        if auto_start:
            self.state = STATE_RUNNING
            self._started_at = self._clock()
        else:
            self.state = STATE_IDLE

    def skip(self):
        """Immediately move to the next Pomodoro phase."""
        self._advance_phase()

    def update(
        self,
        now=None,
    ):
        """Advance to the next phase when a running countdown expires."""
        if self.state != STATE_RUNNING:
            return False

        if now is None:
            now = self._clock()

        if self.remaining_seconds(
            now=now,
        ) > 0.0:
            return False

        self._advance_phase()
        return True

    def snapshot(
        self,
        now=None,
    ):
        """Return immutable state suitable for rendering or persistence."""
        remaining = self.remaining_seconds(
            now=now,
        )

        return PomodoroSnapshot(
            phase=self.phase,
            state=self.state,
            duration_seconds=self.phase_duration_seconds(),
            remaining_seconds=remaining,
            progress=self.progress(
                now=now,
            ),
            completed_focus_sessions=(
                self.completed_focus_sessions
            ),
        )

    def draw(
        self,
        painter,
        geometry,
        placement,
    ):
        """Rendering will be added once compositor layering is wired.

        The timer engine intentionally lands first.
        """
        del painter
        del geometry
        del placement
