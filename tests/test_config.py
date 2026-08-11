"""Tests for shared Mousehair configuration handling."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import mousehair_app.config as config_module


class ConfigTests(unittest.TestCase):

    def test_default_config_returns_independent_copy(self):
        first = config_module.default_config()
        second = config_module.default_config()

        first["hotkey_modifiers"].append(
            "CTRL"
        )

        self.assertNotEqual(
            first["hotkey_modifiers"],
            second["hotkey_modifiers"],
        )

    def test_missing_config_returns_defaults_and_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = (
                Path(directory)
                / "config.json"
            )

            with mock.patch.object(
                config_module,
                "CONFIG_PATH",
                config_path,
            ):
                result, valid = (
                    config_module.load_config(
                        valid_effect_names={
                            "static",
                            "sliding",
                        }
                    )
                )

        self.assertFalse(
            valid
        )

        self.assertEqual(
            result["gap"],
            config_module.DEFAULT_CONFIG[
                "gap"
            ],
        )

    def test_legacy_animation_settings_migrate(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = (
                Path(directory)
                / "config.json"
            )

            config_path.write_text(
                json.dumps(
                    {
                        "animate_enabled": True,
                        "animation_style": "sliding",
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.object(
                config_module,
                "CONFIG_PATH",
                config_path,
            ):
                result, valid = (
                    config_module.load_config(
                        valid_effect_names={
                            "static",
                            "sliding",
                        }
                    )
                )

        self.assertTrue(
            valid
        )

        self.assertEqual(
            result["crosshair_effect"],
            "sliding",
        )

    def test_old_break_duration_migrates(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = (
                Path(directory)
                / "config.json"
            )

            config_path.write_text(
                json.dumps(
                    {
                        "pomodoro_break_minutes": 9,
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.object(
                config_module,
                "CONFIG_PATH",
                config_path,
            ):
                result, valid = (
                    config_module.load_config()
                )

        self.assertTrue(
            valid
        )

        self.assertEqual(
            result[
                "pomodoro_short_break_minutes"
            ],
            9,
        )

    def test_save_and_reload_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = (
                Path(directory)
                / "config.json"
            )

            data = (
                config_module.default_config()
            )

            data["gap"] = 143
            data["pomodoro_timer_text_size"] = 24

            with mock.patch.object(
                config_module,
                "CONFIG_PATH",
                config_path,
            ):
                config_module.save_config(
                    data
                )

                result, valid = (
                    config_module.load_config()
                )

        self.assertTrue(
            valid
        )

        self.assertEqual(
            result["gap"],
            143,
        )

        self.assertEqual(
            result["pomodoro_timer_text_size"],
            24,
        )


if __name__ == "__main__":
    unittest.main()
