"""Tests for Mousehair's shared reticle geometry."""

import unittest

from mousehair_app.geometry import ReticleGeometry


class ReticleGeometryTests(unittest.TestCase):
    def test_current_example_geometry(self):
        geometry = ReticleGeometry.from_values(
            gap=100,
            outer_thickness=12,
            inner_thickness=4,
        )

        self.assertEqual(geometry.ring_centreline_radius, 100.0)
        self.assertEqual(geometry.ring_outer_edge_radius, 106.0)
        self.assertEqual(geometry.ring_inner_edge_radius, 94.0)
        self.assertEqual(geometry.cinnamon_lens_radius, 94.0)
        self.assertEqual(geometry.full_visible_diameter, 212.0)

    def test_negative_widths_are_sanitized(self):
        geometry = ReticleGeometry.from_values(
            gap=0,
            outer_thickness=-10,
            inner_thickness=-5,
        )

        self.assertEqual(geometry.gap, 0.5)
        self.assertEqual(geometry.outer_thickness, 0.0)
        self.assertEqual(geometry.inner_thickness, 0.0)
        self.assertEqual(geometry.cinnamon_lens_radius, 1.0)


if __name__ == "__main__":
    unittest.main()
