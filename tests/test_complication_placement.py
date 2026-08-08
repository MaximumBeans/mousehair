"""Tests for Mousehair complication placement geometry."""

import unittest

from mousehair_app.complications import (
    ComplicationPlacement,
    arc_placement,
    normalise_angle,
    point_placement,
    polar_point,
)


class AngleTests(unittest.TestCase):

    def test_normalise_angle_wraps_positive_values(self):
        self.assertEqual(
            normalise_angle(450),
            90.0,
        )

    def test_normalise_angle_wraps_negative_values(self):
        self.assertEqual(
            normalise_angle(-90),
            270.0,
        )


class PolarPointTests(unittest.TestCase):

    def assertPointAlmostEqual(
        self,
        actual,
        expected,
    ):
        self.assertAlmostEqual(
            actual[0],
            expected[0],
            places=6,
        )

        self.assertAlmostEqual(
            actual[1],
            expected[1],
            places=6,
        )

    def test_zero_degrees_is_top(self):
        self.assertPointAlmostEqual(
            polar_point(
                100,
                100,
                20,
                0,
            ),
            (
                100,
                80,
            ),
        )

    def test_ninety_degrees_is_right(self):
        self.assertPointAlmostEqual(
            polar_point(
                100,
                100,
                20,
                90,
            ),
            (
                120,
                100,
            ),
        )

    def test_180_degrees_is_bottom(self):
        self.assertPointAlmostEqual(
            polar_point(
                100,
                100,
                20,
                180,
            ),
            (
                100,
                120,
            ),
        )

    def test_270_degrees_is_left(self):
        self.assertPointAlmostEqual(
            polar_point(
                100,
                100,
                20,
                270,
            ),
            (
                80,
                100,
            ),
        )


class PlacementTests(unittest.TestCase):

    def test_full_ring(self):
        placement = arc_placement(
            "full",
            radial_zone="inside",
        )

        self.assertTrue(
            placement.is_full_ring
        )

        self.assertEqual(
            placement.span,
            360.0,
        )

    def test_upper_right_quadrant(self):
        placement = arc_placement(
            "upper_right"
        )

        self.assertEqual(
            placement.normalised_angle,
            0.0,
        )

        self.assertEqual(
            placement.span,
            90.0,
        )

    def test_named_bottom_point(self):
        placement = point_placement(
            "bottom"
        )

        self.assertTrue(
            placement.is_point
        )

        self.assertEqual(
            placement.normalised_angle,
            180.0,
        )

    def test_custom_angle(self):
        placement = ComplicationPlacement(
            radial_zone="outside",
            angle=37.5,
            collision="reserve",
        )

        self.assertEqual(
            placement.normalised_angle,
            37.5,
        )

        self.assertEqual(
            placement.collision,
            "reserve",
        )

    def test_inside_radius(self):
        placement = ComplicationPlacement(
            radial_zone="inside",
        )

        self.assertEqual(
            placement.resolve_radius(
                ring_radius=100,
                zone_spacing=12,
            ),
            88.0,
        )

    def test_outside_radius(self):
        placement = ComplicationPlacement(
            radial_zone="outside",
            radial_offset=3,
        )

        self.assertEqual(
            placement.resolve_radius(
                ring_radius=100,
                zone_spacing=12,
            ),
            115.0,
        )

    def test_invalid_zone_rejected(self):
        with self.assertRaises(
            ValueError
        ):
            ComplicationPlacement(
                radial_zone="somewhere-weird",
            )

    def test_invalid_collision_policy_rejected(self):
        with self.assertRaises(
            ValueError
        ):
            ComplicationPlacement(
                collision="explode",
            )

    def test_span_above_full_circle_rejected(self):
        with self.assertRaises(
            ValueError
        ):
            ComplicationPlacement(
                span=361,
            )


if __name__ == "__main__":
    unittest.main()
