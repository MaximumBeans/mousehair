"""Pomodoro timer complication for Mousehair."""

from dataclasses import dataclass
import time

from PyQt5 import QtCore, QtGui

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
        """Draw the Pomodoro as a tomato-red clockwise progress ring.

        The ring lives just inside the accessibility reticule. Its top marker
        is a small vector tomato rather than a font glyph, so its appearance
        does not depend on colour-emoji support.
        """
        snapshot = self.snapshot()

        center_x = float(
            geometry["center_x"]
        )

        center_y = float(
            geometry["center_y"]
        )

        ring_radius = float(
            geometry["ring_radius"]
        )

        reticle_inner_edge = float(
            geometry["ring_inner_edge"]
        )

        # Leave a small breathing space between the accessibility reticule and
        # the Pomodoro progress ring.
        progress_width = max(
            1.0,
            float(
                getattr(
                    self.host,
                    "pomodoro_ring_thickness",
                    5.0,
                )
            ),
        )

        padding = 5.0

        progress_radius = max(
            8.0,
            min(
                ring_radius,
                reticle_inner_edge
                - padding
                - progress_width / 2.0,
            ),
        )

        diameter = (
            progress_radius
            * 2.0
        )

        arc_rect = QtCore.QRectF(
            center_x - progress_radius,
            center_y - progress_radius,
            diameter,
            diameter,
        )

        painter.save()

        opacity = max(
            0.0,
            min(
                1.0,
                float(
                    getattr(
                        self.host,
                        "current_alpha",
                        1.0,
                    )
                ),
            ),
        )

        # A very dark track gives the timer a complete-circle silhouette even
        # before much progress has accumulated.
        track_colour = QtGui.QColor(
            "#401414"
        )
        track_colour.setAlphaF(
            opacity * 0.70
        )

        track_pen = QtGui.QPen(
            track_colour
        )
        track_pen.setWidthF(
            progress_width
        )
        track_pen.setCapStyle(
            QtCore.Qt.RoundCap
        )

        painter.setPen(
            track_pen
        )
        painter.setBrush(
            QtCore.Qt.NoBrush
        )
        painter.drawEllipse(
            arc_rect
        )

        # Mousehair's Pomodoro identity: proper tomato red.
        progress_colour = QtGui.QColor(
            "#E53935"
        )
        progress_colour.setAlphaF(
            opacity
        )

        progress_pen = QtGui.QPen(
            progress_colour
        )
        progress_pen.setWidthF(
            progress_width
        )
        progress_pen.setCapStyle(
            QtCore.Qt.RoundCap
        )

        painter.setPen(
            progress_pen
        )

        # QPainter uses sixteenths of a degree, with positive values travelling
        # counter-clockwise. Start at 12 o'clock and use a negative span so
        # Mousehair fills clockwise.
        start_angle = (
            90
            * 16
        )

        span_angle = int(
            -360
            * 16
            * snapshot.progress
        )

        if span_angle:
            painter.drawArc(
                arc_rect,
                start_angle,
                span_angle,
            )

        # ------------------------------------------------------------
        # Tomato marker at 12 o'clock
        # ------------------------------------------------------------

        tomato_center_x = center_x

        tomato_center_y = (
            center_y
            - progress_radius
        )

        tomato_radius = max(
            3.0,
            float(
                getattr(
                    self.host,
                    "pomodoro_icon_size",
                    14.0,
                )
            ) / 2.0,
        )

        tomato_rect = QtCore.QRectF(
            tomato_center_x
            - tomato_radius,
            tomato_center_y
            - tomato_radius,
            tomato_radius * 2.0,
            tomato_radius * 2.0,
        )

        tomato_colour = QtGui.QColor(
            "#E53935"
        )
        tomato_colour.setAlphaF(
            opacity
        )

        painter.setPen(
            QtCore.Qt.NoPen
        )
        painter.setBrush(
            tomato_colour
        )
        painter.drawEllipse(
            tomato_rect
        )

        # Draw a small green crown/stem. Keeping this geometric means the icon
        # remains crisp at any desktop scale.
        leaf_colour = QtGui.QColor(
            "#43A047"
        )
        leaf_colour.setAlphaF(
            opacity
        )

        painter.setBrush(
            leaf_colour
        )

        leaf_path = QtGui.QPainterPath()

        leaf_path.moveTo(
            tomato_center_x,
            tomato_center_y - tomato_radius - 4.0,
        )

        leaf_path.lineTo(
            tomato_center_x + 2.0,
            tomato_center_y - 3.0,
        )

        leaf_path.lineTo(
            tomato_center_x + 6.0,
            tomato_center_y - 5.0,
        )

        leaf_path.lineTo(
            tomato_center_x + 3.0,
            tomato_center_y,
        )

        leaf_path.lineTo(
            tomato_center_x,
            tomato_center_y - 2.0,
        )

        leaf_path.lineTo(
            tomato_center_x - 3.0,
            tomato_center_y,
        )

        leaf_path.lineTo(
            tomato_center_x - 6.0,
            tomato_center_y - 5.0,
        )

        leaf_path.lineTo(
            tomato_center_x - 2.0,
            tomato_center_y - 3.0,
        )

        leaf_path.closeSubpath()

        painter.drawPath(
            leaf_path
        )

        painter.restore()
