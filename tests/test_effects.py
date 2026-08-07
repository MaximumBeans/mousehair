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


class SlidingEffectTests(unittest.TestCase):

    def test_sliding_effect_draws_outer_and_inner_passes(self):
        from mousehair_app.effects import SlidingCrosshairEffect

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
        from mousehair_app.effects import SlidingCrosshairEffect

        self.assertEqual(
            SlidingCrosshairEffect.name,
            "sliding",
        )


class ArrowEffectTests(unittest.TestCase):

    def test_arrow_effect_delegates_to_arrow_renderer(self):
        from mousehair_app.effects import ArrowCrosshairEffect

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
        from mousehair_app.effects import ArrowCrosshairEffect

        self.assertEqual(
            ArrowCrosshairEffect.name,
            "arrows",
        )
