"""Tests for Mousehair's visual Effects Engine."""

import unittest

from mousehair_app.effects import (
    ArrowCrosshairEffect,
    SlidingCrosshairEffect,
    StaticCrosshairEffect,
)


class FakePainter:
    """Minimal painter that records line drawing operations."""

    def __init__(self):
        self.pen = None
        self.lines = []

    def setPen(self, pen):
        self.pen = pen

    def drawLine(self, *args):
        self.lines.append(
            (self.pen, args)
        )


class StaticHost:
    """Minimal host supplying the dimensions required by Static."""

    gap = 20

    def width(self):
        return 800

    def height(self):
        return 600


class StaticEffectTests(unittest.TestCase):

    def test_static_effect_draws_four_arms_twice(self):
        host = StaticHost()
        effect = StaticCrosshairEffect(host)

        painter = FakePainter()

        effect.render(
            painter,
            400,
            300,
            "outer",
            "inner",
        )

        self.assertEqual(
            len(painter.lines),
            8,
        )

        self.assertEqual(
            [entry[0] for entry in painter.lines[:4]],
            ["outer"] * 4,
        )

        self.assertEqual(
            [entry[0] for entry in painter.lines[4:]],
            ["inner"] * 4,
        )

    def test_static_effect_respects_gap(self):
        host = StaticHost()
        effect = StaticCrosshairEffect(host)

        painter = FakePainter()

        effect.render(
            painter,
            400,
            300,
            "outer",
            "inner",
        )

        outer_lines = [
            args
            for pen, args in painter.lines[:4]
        ]

        self.assertIn(
            (0, 300, 380, 300),
            outer_lines,
        )

        self.assertIn(
            (420, 300, 800, 300),
            outer_lines,
        )

        self.assertIn(
            (400, 0, 400, 280),
            outer_lines,
        )

        self.assertIn(
            (400, 320, 400, 600),
            outer_lines,
        )

    def test_static_effect_has_stable_name(self):
        self.assertEqual(
            StaticCrosshairEffect.name,
            "static",
        )


class SlidingEffectTests(unittest.TestCase):

    def test_sliding_effect_draws_outer_and_inner_passes(self):
        class SlidingHost:
            def __init__(self):
                self.calls = []

            def draw_animated_lines(
                self,
                painter,
                mx,
                my,
                pen,
            ):
                self.calls.append(
                    (painter, mx, my, pen)
                )

        host = SlidingHost()
        effect = SlidingCrosshairEffect(host)

        painter = object()
        outer_pen = object()
        inner_pen = object()

        effect.render(
            painter,
            50,
            75,
            outer_pen,
            inner_pen,
        )

        self.assertEqual(
            host.calls,
            [
                (painter, 50, 75, outer_pen),
                (painter, 50, 75, inner_pen),
            ],
        )

    def test_sliding_effect_has_stable_name(self):
        self.assertEqual(
            SlidingCrosshairEffect.name,
            "sliding",
        )


class ArrowEffectTests(unittest.TestCase):

    def test_arrow_effect_delegates_to_arrow_renderer(self):
        class ArrowHost:
            def __init__(self):
                self.calls = []

            def draw_arrow_lines(
                self,
                painter,
                mx,
                my,
            ):
                self.calls.append(
                    (painter, mx, my)
                )

        host = ArrowHost()
        effect = ArrowCrosshairEffect(host)

        painter = object()

        effect.render(
            painter,
            120,
            240,
            object(),
            object(),
        )

        self.assertEqual(
            host.calls,
            [
                (painter, 120, 240),
            ],
        )

    def test_arrow_effect_has_stable_name(self):
        self.assertEqual(
            ArrowCrosshairEffect.name,
            "arrows",
        )


if __name__ == "__main__":
    unittest.main()
