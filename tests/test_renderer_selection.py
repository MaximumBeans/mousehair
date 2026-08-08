"""Tests for Mousehair's crosshair renderer registry."""

import unittest

from mousehair_app.renderer import RenderPipelineMixin
from mousehair_app.effects import (
    ArrowCrosshairEffect,
    SlidingCrosshairEffect,
    StaticCrosshairEffect,
)


class DummyRendererHost(RenderPipelineMixin):
    """Minimal RenderPipelineMixin host for selection tests."""

    def __init__(self, animate_enabled, animation_style):
        self.animate_enabled = animate_enabled
        self.animation_style = animation_style


class RendererSelectionTests(unittest.TestCase):

    def test_animation_disabled_means_static(self):
        host = DummyRendererHost(
            animate_enabled=False,
            animation_style="arrows",
        )

        self.assertEqual(
            host._crosshair_renderer_name(),
            "static",
        )

    def test_sliding_renderer_selected(self):
        host = DummyRendererHost(
            animate_enabled=True,
            animation_style="sliding",
        )

        self.assertEqual(
            host._crosshair_renderer_name(),
            "sliding",
        )

    def test_arrow_renderer_selected(self):
        host = DummyRendererHost(
            animate_enabled=True,
            animation_style="arrows",
        )

        self.assertEqual(
            host._crosshair_renderer_name(),
            "arrows",
        )

    def test_missing_style_defaults_to_static(self):
        host = DummyRendererHost(
            animate_enabled=True,
            animation_style=None,
        )

        self.assertEqual(
            host._crosshair_renderer_name(),
            "static",
        )

    def test_registry_maps_names_to_effect_classes(self):
        host = DummyRendererHost(
            animate_enabled=False,
            animation_style=None,
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

    def test_registry_contains_existing_renderers(self):
        host = DummyRendererHost(
            animate_enabled=False,
            animation_style=None,
        )

        self.assertEqual(
            set(host._crosshair_renderers()),
            {"static", "sliding", "arrows", "pulse"},
        )


if __name__ == "__main__":
    unittest.main()
