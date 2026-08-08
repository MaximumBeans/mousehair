"""Polar placement geometry for Mousehair complications."""

from dataclasses import dataclass
import math


RADIAL_ZONES = {
    "inside",
    "ring",
    "outside",
    "custom",
}

COLLISION_POLICIES = {
    "overlay",
    "reserve",
    "ignore",
    "mask",
}


NAMED_POINT_ANGLES = {
    # Mousehair uses screen-friendly polar coordinates:
    #
    #       0°
    #        |
    # 270° --+-- 90°
    #        |
    #      180°
    #
    # Angles therefore increase clockwise.
    "top": 0.0,
    "right": 90.0,
    "bottom": 180.0,
    "left": 270.0,
}


NAMED_ARC_REGIONS = {
    "full": (0.0, 360.0),

    "upper_right": (
        0.0,
        90.0,
    ),

    "lower_right": (
        90.0,
        90.0,
    ),

    "lower_left": (
        180.0,
        90.0,
    ),

    "upper_left": (
        270.0,
        90.0,
    ),
}


def normalise_angle(angle):
    """Return an angle constrained to the range 0 <= angle < 360."""
    return float(angle) % 360.0


def polar_point(
    center_x,
    center_y,
    radius,
    angle,
):
    """Return the screen position at a polar angle around a centre point.

    Mousehair's convention is:

        0°   = top
        90°  = right
        180° = bottom
        270° = left

    This differs from mathematical Cartesian angles but is much more natural
    for a pointer-centred screen HUD.
    """
    radians = math.radians(
        normalise_angle(angle)
    )

    x = (
        float(center_x)
        + math.sin(radians)
        * float(radius)
    )

    y = (
        float(center_y)
        - math.cos(radians)
        * float(radius)
    )

    return (
        x,
        y,
    )


@dataclass(frozen=True)
class ComplicationPlacement:
    """Describe where one complication belongs around the Mousehair ring.

    ``radial_zone`` is semantic. The renderer will later decide the precise
    pixel spacing appropriate for the contents being drawn.

    ``radial_offset`` provides a user-controlled adjustment after the zone's
    normal radius is calculated.

    ``angle`` is the clockwise start or point angle.

    ``span`` is zero for point-like complications such as icons and labels,
    and greater than zero for arcs. A full-ring complication uses 360 degrees.
    """

    radial_zone: str = "ring"
    radial_offset: float = 0.0

    angle: float = 0.0
    span: float = 0.0

    anchor: str = "centre"
    collision: str = "overlay"

    def __post_init__(self):
        if self.radial_zone not in RADIAL_ZONES:
            raise ValueError(
                f"Unknown radial zone: {self.radial_zone}"
            )

        if self.collision not in COLLISION_POLICIES:
            raise ValueError(
                f"Unknown collision policy: {self.collision}"
            )

        if not 0.0 <= float(self.span) <= 360.0:
            raise ValueError(
                "Complication span must be between 0 and 360 degrees."
            )

    @property
    def normalised_angle(self):
        """Return the start/point angle in canonical form."""
        return normalise_angle(
            self.angle
        )

    @property
    def end_angle(self):
        """Return the normalised end angle of an arc."""
        return normalise_angle(
            self.normalised_angle
            + float(self.span)
        )

    @property
    def is_full_ring(self):
        """Return whether the complication occupies a complete ring."""
        return math.isclose(
            float(self.span),
            360.0,
        )

    @property
    def is_point(self):
        """Return whether this is a point-positioned complication."""
        return math.isclose(
            float(self.span),
            0.0,
        )

    def resolve_radius(
        self,
        ring_radius,
        zone_spacing,
    ):
        """Resolve the complication's radius around the main ring.

        ``zone_spacing`` is deliberately supplied by the eventual renderer.
        That keeps this geometry class independent of line thickness, icon
        size, text height, and other rendering details.

        Inside:
            one spacing unit inward.

        Ring:
            centred on the reticule ring.

        Outside:
            one spacing unit outward.

        Custom:
            starts from the ring centreline and relies entirely on
            ``radial_offset``.
        """
        ring_radius = float(
            ring_radius
        )

        zone_spacing = max(
            0.0,
            float(zone_spacing),
        )

        base_radius = ring_radius

        if self.radial_zone == "inside":
            base_radius -= zone_spacing

        elif self.radial_zone == "outside":
            base_radius += zone_spacing

        elif self.radial_zone in {
            "ring",
            "custom",
        }:
            pass

        return max(
            0.0,
            base_radius
            + float(self.radial_offset),
        )

    def point(
        self,
        center_x,
        center_y,
        radius,
    ):
        """Return the screen point for this placement's angle."""
        return polar_point(
            center_x,
            center_y,
            radius,
            self.normalised_angle,
        )


def point_placement(
    name,
    *,
    radial_zone="outside",
    radial_offset=0.0,
    collision="overlay",
):
    """Create a placement from a friendly cardinal point name."""
    try:
        angle = NAMED_POINT_ANGLES[
            name
        ]
    except KeyError as exc:
        raise ValueError(
            f"Unknown named point placement: {name}"
        ) from exc

    return ComplicationPlacement(
        radial_zone=radial_zone,
        radial_offset=radial_offset,
        angle=angle,
        span=0.0,
        collision=collision,
    )


def arc_placement(
    name,
    *,
    radial_zone="outside",
    radial_offset=0.0,
    collision="overlay",
):
    """Create a placement from a friendly named arc region."""
    try:
        angle, span = NAMED_ARC_REGIONS[
            name
        ]
    except KeyError as exc:
        raise ValueError(
            f"Unknown named arc placement: {name}"
        ) from exc

    return ComplicationPlacement(
        radial_zone=radial_zone,
        radial_offset=radial_offset,
        angle=angle,
        span=span,
        collision=collision,
    )
