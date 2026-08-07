"""Tests for Mousehair's visual Effects Engine."""

import unittest

from mousehair_app.effects import StaticCrosshairEffect


class DummyHost:
    """Capture drawing requests made by an effect."""

    def __init__(self):
        self.calls = []

    def draw_static_lines(
        self,
        painter,
        mx,
        my,
        pen,
    ):
        self.calls.append(
            (painter, mx, my, pen)
        )


class StaticEffectTests(unittest.TestCase):

    def test_static_effect_draws_outer_and_inner_passes(self):
        host = DummyHost()
        effect = StaticCrosshairEffect(host)

        painter = object()
        outer_pen = object()
        inner_pen = object()

        effect.render(
            painter,
            100,
            200,
            outer_pen,
            inner_pen,
        )

        self.assertEqual(
            host.calls,
            [
                (painter, 100, 200, outer_pen),
                (painter, 100, 200, inner_pen),
            ],
        )

    def test_static_effect_has_stable_name(self):
        self.assertEqual(
            StaticCrosshairEffect.name,
            "static",
        )


if __name__ == "__main__":
    unittest.main()
