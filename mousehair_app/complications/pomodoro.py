"""Pomodoro timer complication for Mousehair."""

from dataclasses import dataclass
import math
import time

from PyQt5 import QtCore, QtGui

from .base import (
    Complication,
    ComplicationSetting,
)

from .placement import ComplicationPlacement


PHASE_FOCUS = "focus"
PHASE_SHORT_BREAK = "short_break"
PHASE_LONG_BREAK = "long_break"

# Temporary compatibility alias for code/config written before long breaks
# existed. New code should use PHASE_SHORT_BREAK explicitly.
PHASE_BREAK = PHASE_SHORT_BREAK

STATE_IDLE = "idle"
STATE_RUNNING = "running"
STATE_PAUSED = "paused"


@dataclass(frozen=True)
class PomodoroSnapshot:
    """Read-only presentation state for the Pomodoro HUD."""

    phase: str
    state: str

    duration_seconds: float
    remaining_seconds: float
    progress: float

    completed_focus_sessions: int
    focuses_until_long_break: int


class PomodoroComplication(Complication):
    """Pomodoro state machine and pointer-centred HUD complication."""

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
            key="pomodoro_short_break_minutes",
            label="Short break duration",
            kind="int",
            default=5,
            minimum=1,
            maximum=60,
            step=1,
            suffix=" min",
        ),
        ComplicationSetting(
            key="pomodoro_long_break_minutes",
            label="Long break duration",
            kind="int",
            default=15,
            minimum=1,
            maximum=120,
            step=1,
            suffix=" min",
        ),
        ComplicationSetting(
            key="pomodoro_focuses_before_long_break",
            label="Focuses before long break",
            kind="int",
            default=4,
            minimum=1,
            maximum=20,
            step=1,
        ),
        ComplicationSetting(
            key="pomodoro_auto_start_break",
            label="Automatically start breaks",
            kind="bool",
            default=False,
        ),
        ComplicationSetting(
            key="pomodoro_auto_start_focus",
            label="Automatically start next focus",
            kind="bool",
            default=False,
        ),
    )

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
        return getattr(
            self.host,
            key,
            default,
        )

    def focuses_before_long_break(self):
        """Return the configured Pomodoro cycle length."""
        return max(
            1,
            int(
                self._setting(
                    "pomodoro_focuses_before_long_break",
                    4,
                )
            ),
        )

    def focuses_until_long_break(self):
        """Return how many completed focuses remain before a long break."""
        cycle_length = self.focuses_before_long_break()

        completed_in_cycle = (
            self.completed_focus_sessions
            % cycle_length
        )

        remaining = (
            cycle_length
            - completed_in_cycle
        )

        return remaining

    def phase_duration_seconds(
        self,
        phase=None,
    ):
        """Return configured duration for one phase."""
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

        elif phase == PHASE_SHORT_BREAK:
            minutes = self._setting(
                "pomodoro_short_break_minutes",
                5,
            )

        elif phase == PHASE_LONG_BREAK:
            minutes = self._setting(
                "pomodoro_long_break_minutes",
                15,
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
        duration = self.phase_duration_seconds()

        remaining = self.remaining_seconds(
            now=now,
        )

        return max(
            0.0,
            min(
                1.0,
                1.0 - remaining / duration,
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
                now - elapsed
            )

        else:
            self._started_at = now

        self._paused_remaining = None
        self.state = STATE_RUNNING

    def pause(self):
        """Pause without losing elapsed time."""
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
        if self.state == STATE_RUNNING:
            self.pause()
        else:
            self.start()

    def reset(self):
        """Return to a fresh first focus and reset the Pomodoro cycle."""
        self.phase = PHASE_FOCUS
        self.state = STATE_IDLE

        self.completed_focus_sessions = 0

        self._started_at = None
        self._paused_remaining = None

    def reset_current_phase(self):
        """Restart the current phase without resetting completed focuses."""
        self.state = STATE_IDLE

        self._started_at = None
        self._paused_remaining = None

    def _next_break_phase(self):
        """Choose short or long break after a completed focus."""
        cycle_length = self.focuses_before_long_break()

        if (
            self.completed_focus_sessions
            % cycle_length
            == 0
        ):
            return PHASE_LONG_BREAK

        return PHASE_SHORT_BREAK

    def _should_auto_start_phase(self, phase):
        """Return whether a newly entered phase should start immediately."""
        if phase in {
            PHASE_SHORT_BREAK,
            PHASE_LONG_BREAK,
        }:
            return bool(
                self._setting(
                    "pomodoro_auto_start_break",
                    False,
                )
            )

        if phase == PHASE_FOCUS:
            return bool(
                self._setting(
                    "pomodoro_auto_start_focus",
                    False,
                )
            )

        return False

    def _enter_phase(
        self,
        phase,
        *,
        allow_auto_start=True,
    ):
        """Enter a new phase and apply its auto-start policy."""
        self.phase = phase

        self._started_at = None
        self._paused_remaining = None

        should_start = (
            allow_auto_start
            and self._should_auto_start_phase(
                phase
            )
        )

        if should_start:
            self.state = STATE_RUNNING
            self._started_at = self._clock()

        else:
            self.state = STATE_IDLE

    def _advance_phase(self):
        """Advance according to the Pomodoro cycle."""
        if self.phase == PHASE_FOCUS:
            self.completed_focus_sessions += 1

            self._enter_phase(
                self._next_break_phase()
            )

        else:
            completed_full_cycle = (
                self.phase
                == PHASE_LONG_BREAK
            )

            pause_after_cycle = bool(
                self._setting(
                    "pomodoro_pause_after_cycle",
                    True,
                )
            )

            self._enter_phase(
                PHASE_FOCUS,
                allow_auto_start=not (
                    completed_full_cycle
                    and pause_after_cycle
                ),
            )

    def skip(self):
        """Immediately advance to the logically next phase."""
        self._advance_phase()

    def update(
        self,
        now=None,
    ):
        """Advance when a running phase expires."""
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

    def countdown_text(
        self,
        now=None,
    ):
        """Return remaining time as a stable MM:SS HUD string."""
        remaining = max(
            0,
            int(
                math.ceil(
                    self.remaining_seconds(
                        now=now,
                    )
                )
            ),
        )

        minutes, seconds = divmod(
            remaining,
            60,
        )

        return (
            f"{minutes:02d}:{seconds:02d}"
        )

    def phase_colour(self):
        """Return the configured progress colour for the current phase."""
        if self.phase == PHASE_FOCUS:
            return str(
                self._setting(
                    "pomodoro_focus_colour",
                    "#E53935",
                )
            )

        return str(
            self._setting(
                "pomodoro_break_colour",
                "#43A047",
            )
        )

    def phase_track_colour(self):
        """Return a darker companion colour for the unfilled timer track."""
        colour = QtGui.QColor(
            self.phase_colour()
        )

        if not colour.isValid():
            colour = QtGui.QColor(
                "#E53935"
                if self.phase == PHASE_FOCUS
                else "#43A047"
            )

        # Qt's darker() keeps the track related to the selected user colour
        # without requiring a second colour setting for every phase.
        return colour.darker(300).name()

    def snapshot(
        self,
        now=None,
    ):
        remaining = self.remaining_seconds(
            now=now,
        )

        return PomodoroSnapshot(
            phase=self.phase,
            state=self.state,
            duration_seconds=(
                self.phase_duration_seconds()
            ),
            remaining_seconds=remaining,
            progress=self.progress(
                now=now,
            ),
            completed_focus_sessions=(
                self.completed_focus_sessions
            ),
            focuses_until_long_break=(
                self.focuses_until_long_break()
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
            self.phase_track_colour()
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
            self.phase_colour()
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
        # Countdown label at 6 o'clock
        # ------------------------------------------------------------

        countdown_text = self.countdown_text()

        countdown_font = QtGui.QFont()
        countdown_font.setBold(True)
        countdown_font.setPixelSize(16)

        painter.setFont(
            countdown_font
        )

        metrics = QtGui.QFontMetricsF(
            countdown_font
        )

        text_rect = metrics.boundingRect(
            countdown_text
        )

        countdown_center_y = (
            center_y
            + progress_radius
            - 18.0
        )

        background_rect = QtCore.QRectF(
            center_x
            - text_rect.width() / 2.0
            - 6.0,
            countdown_center_y
            - text_rect.height() / 2.0
            - 3.0,
            text_rect.width()
            + 12.0,
            text_rect.height()
            + 6.0,
        )

        background_colour = QtGui.QColor(
            "#000000"
        )
        background_colour.setAlphaF(
            opacity * 0.72
        )

        painter.setPen(
            QtCore.Qt.NoPen
        )
        painter.setBrush(
            background_colour
        )

        painter.drawRoundedRect(
            background_rect,
            5.0,
            5.0,
        )

        text_colour = QtGui.QColor(
            "#FFFFFF"
        )
        text_colour.setAlphaF(
            opacity
        )

        painter.setPen(
            text_colour
        )

        painter.drawText(
            background_rect,
            QtCore.Qt.AlignCenter,
            countdown_text,
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
