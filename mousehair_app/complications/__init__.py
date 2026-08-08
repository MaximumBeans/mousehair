"""Mousehair pointer-HUD complications."""

from .base import (
    Complication,
    ComplicationSetting,
)

from .manager import ComplicationManager

from .pomodoro import (
    PHASE_BREAK,
    PHASE_FOCUS,
    STATE_IDLE,
    STATE_PAUSED,
    STATE_RUNNING,
    PomodoroComplication,
    PomodoroSnapshot,
)

from .placement import (
    COLLISION_POLICIES,
    NAMED_ARC_REGIONS,
    NAMED_POINT_ANGLES,
    RADIAL_ZONES,
    ComplicationPlacement,
    arc_placement,
    normalise_angle,
    point_placement,
    polar_point,
)

__all__ = [
    "ComplicationManager",
    "PHASE_BREAK",
    "PHASE_FOCUS",
    "STATE_IDLE",
    "STATE_PAUSED",
    "STATE_RUNNING",
    "PomodoroComplication",
    "PomodoroSnapshot",
    "COLLISION_POLICIES",
    "NAMED_ARC_REGIONS",
    "NAMED_POINT_ANGLES",
    "RADIAL_ZONES",
    "Complication",
    "ComplicationPlacement",
    "ComplicationSetting",
    "arc_placement",
    "normalise_angle",
    "point_placement",
    "polar_point",
]
