"""Shared reticle geometry calculations for Mousehair.

The PyQt renderer and Cinnamon bridge both need to agree about the meaning of
the configured centre gap and stroke widths.

Mousehair draws the outer and inner ring strokes on the same centreline:

    ring centreline = configured gap

Because a pen stroke is centred on its path:

    ring outer edge = gap + outer_thickness / 2
    ring inner edge = gap - outer_thickness / 2

The compositor-native magnified image must end at the ring's inner edge so the
complete black-white-black ring remains visible above it.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ReticleGeometry:
    """Calculated dimensions for one Mousehair reticle configuration."""

    gap: float
    outer_thickness: float
    inner_thickness: float

    @classmethod
    def from_values(
        cls,
        gap,
        outer_thickness,
        inner_thickness,
    ):
        """Create a sanitized geometry object from settings values."""
        return cls(
            gap=max(0.5, float(gap)),
            outer_thickness=max(0.0, float(outer_thickness)),
            inner_thickness=max(0.0, float(inner_thickness)),
        )

    @property
    def ring_centreline_radius(self):
        """Radius on which both visible ring strokes are drawn."""
        return self.gap

    @property
    def outer_half_width(self):
        """Half the width of the broad outer stroke."""
        return self.outer_thickness / 2.0

    @property
    def ring_outer_edge_radius(self):
        """Furthest visible edge of the broad outer stroke."""
        return self.ring_centreline_radius + self.outer_half_width

    @property
    def ring_inner_edge_radius(self):
        """Clear interior radius inside the complete outer stroke."""
        return max(
            1.0,
            self.ring_centreline_radius - self.outer_half_width,
        )

    @property
    def cinnamon_lens_radius(self):
        """Radius available to the compositor-native magnified image."""
        return self.ring_inner_edge_radius

    @property
    def ring_centreline_diameter(self):
        """Diameter of the ellipse path used to draw the ring."""
        return self.ring_centreline_radius * 2.0

    @property
    def full_visible_diameter(self):
        """Diameter including the outer half of the broad stroke."""
        return self.ring_outer_edge_radius * 2.0
