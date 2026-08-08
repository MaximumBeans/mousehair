"""Tests for Mousehair's Effects Engine selection and caching."""

import unittest

from mousehair_app.renderer import RenderPipelineMixin
from mousehair_app.effects import (
    ArrowCrosshairEffect,
    PulseCrosshairEffect,
    SlidingCrosshairEffect,
    StaticCrosshairEffect,
)


class DummyRendererHost(RenderPipelineMixin):
    """Minimal RenderPipelineMixin host for selection tests."""

    def __init__(
        self,
        *,
        animation_style,
        animate_enabled=True,
    ):
        # animate_enabled remains available for backwards compatibility but is
        # no longer used by the renderer dispatcher.
        self.animate_enabled = animate_enabled
        self.animation_style = animation_style


class RendererSelectionTests(unittest.TestCase):

    def test_static_renderer_selected(self):
        host = DummyRendererHost(
            animation_style="static",
        )

        self.assertEqual(
            host._crosshair_renderer_name(),
            "static",
        )

    def test_sliding_renderer_selected(self):
        host = DummyRendererHost(
            animation_style="sliding",
        )

        self.assertEqual(
            host._crosshair_renderer_name(),
            "sliding",
        )

    def test_arrow_renderer_selected(self):
        host = DummyRendererHost(
            animation_style="arrows",
        )

        self.assertEqual(
            host._crosshair_renderer_name(),
            "arrows",
        )

    def test_pulse_renderer_selected(self):
        host = DummyRendererHost(
            animation_style="pulse",
        )

        self.assertEqual(
            host._crosshair_renderer_name(),
            "pulse",
        )

    def test_missing_style_defaults_to_static(self):
        host = DummyRendererHost(
            animation_style=None,
        )

        self.assertEqual(
            host._crosshair_renderer_name(),
            "static",
        )

    def test_unknown_style_defaults_to_static(self):
        host = DummyRendererHost(
            animation_style="definitely-not-an-effect",
        )

        self.assertEqual(
            host._crosshair_renderer_name(),
            "static",
        )

    def test_registry_contains_existing_renderers(self):
        host = DummyRendererHost(
            animation_style="static",
        )

        self.assertEqual(
            set(host._crosshair_renderers()),
            {
                "static",
                "sliding",
                "arrows",
                "pulse",
            },
        )

    def test_registry_maps_names_to_effect_classes(self):
        host = DummyRendererHost(
            animation_style="static",
        )

        registry = host._crosshair_renderers()

        self.assertIs(
            registry["static"],
            StaticCrosshairEffect,
        )

        self.assertIs(
            registry["sliding"],
            SlidingCrosshairEffect,
        )

        self.assertIs(
            registry["arrows"],
            ArrowCrosshairEffect,
        )

        self.assertIs(
            registry["pulse"],
            PulseCrosshairEffect,
        )


class EffectInstanceCacheTests(unittest.TestCase):

    def test_effect_instances_are_reused(self):
        host = DummyRendererHost(
            animation_style="pulse",
        )

        first = host._crosshair_effect_instances()
        second = host._crosshair_effect_instances()

        self.assertIs(
            first,
            second,
        )

        self.assertIs(
            first["pulse"],
            second["pulse"],
        )

    def test_effect_instances_use_host(self):
        host = DummyRendererHost(
            animation_style="static",
        )

        instances = host._crosshair_effect_instances()

        for effect in instances.values():
            self.assertIs(
                effect.host,
                host,
            )


if __name__ == "__main__":
    unittest.main()
