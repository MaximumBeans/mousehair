"""Shared configuration handling for Mousehair.

Both the Mousehair runtime and the standalone GTK settings application use
this module. Keeping defaults, migration and persistence here prevents the
two programs from slowly developing incompatible ideas about the config file.

The on-disk JSON format deliberately remains flat for now so this refactor
does not itself change user configuration files.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path


CONFIG_PATH = Path(
    os.path.expanduser(
        "~/.config/mousehair/config.json"
    )
)


DEFAULT_CONFIG = {
    "start_with_system": False,

    "hotkey_key": "M",
    "hotkey_modifiers": [
        "SUPER",
        "SHIFT",
    ],

    "alpha": 1.0,
    "gap": 100,

    "outer_thickness": 4,
    "inner_thickness": 2,

    "outer_color": "#FF0000",
    "inner_color": "#FFFFFF",

    "fade_enabled": False,
    "fade_out_delay": 500,
    "fade_in_delay": 0,
    "fade_duration": 300,

    # Canonical Effects Engine setting.
    "crosshair_effect": "static",

    # Legacy compatibility fields.
    "animate_enabled": False,
    "animation_style": "sliding",

    "animate_speed": 180,
    "animate_spacing": 32,
    "animate_segment_length": 14,

    "pulse_strength": 0.15,
    "pulse_period": 1.5,

    "arrow_first_offset": 20,
    "arrow_spacing": 40,
    "arrow_length": 14,
    "arrow_width": 12,
    "arrow_border_over_line": True,

    "ring_enabled": False,

    "magnifier_enabled": False,
    "magnification": 2.0,

    "pomodoro_enabled": True,

    "pomodoro_focus_minutes": 25,
    "pomodoro_short_break_minutes": 5,
    "pomodoro_long_break_minutes": 15,

    "pomodoro_focuses_before_long_break": 4,

    "pomodoro_auto_start_break": False,
    "pomodoro_auto_start_focus": False,

    "pomodoro_pause_after_cycle": True,

    "pomodoro_focus_colour": "#E53935",
    "pomodoro_break_colour": "#43A047",

    "pomodoro_timer_text_size": 16,
    "pomodoro_ring_thickness": 5.0,
    "pomodoro_icon_size": 14.0,
}


def default_config():
    """Return an independent copy of the default configuration."""
    return copy.deepcopy(
        DEFAULT_CONFIG
    )


def _read_raw_config():
    """Read the JSON object without applying defaults or migration."""
    try:
        with CONFIG_PATH.open(
            "r",
            encoding="utf-8",
        ) as handle:
            data = json.load(
                handle
            )

    except (
        OSError,
        ValueError,
        TypeError,
    ):
        return None

    if not isinstance(
        data,
        dict,
    ):
        return None

    return data


def load_config(
    *,
    valid_effect_names=None,
):
    """Load, migrate and validate Mousehair configuration.

    ``valid_effect_names`` is supplied by the runtime because the Effects
    Engine owns the authoritative list of installed renderer names.

    Returns:

        (config, valid)

    ``valid`` is False when the source file was missing or malformed. The
    caller may then save the returned repaired/default configuration.
    """
    defaults = default_config()

    raw = _read_raw_config()

    if raw is None:
        return defaults, False

    config = default_config()

    try:
        config["start_with_system"] = bool(
            raw.get(
                "start_with_system",
                config["start_with_system"],
            )
        )

        config["alpha"] = float(
            raw.get(
                "alpha",
                config["alpha"],
            )
        )

        config["gap"] = int(
            raw.get(
                "gap",
                config["gap"],
            )
        )

        config["outer_thickness"] = int(
            raw.get(
                "outer_thickness",
                config["outer_thickness"],
            )
        )

        config["inner_thickness"] = int(
            raw.get(
                "inner_thickness",
                config["inner_thickness"],
            )
        )

        config["outer_color"] = str(
            raw.get(
                "outer_color",
                config["outer_color"],
            )
        )

        config["inner_color"] = str(
            raw.get(
                "inner_color",
                config["inner_color"],
            )
        )

        config["fade_enabled"] = bool(
            raw.get(
                "fade_enabled",
                config["fade_enabled"],
            )
        )

        config["fade_out_delay"] = int(
            raw.get(
                "fade_out_delay",
                config["fade_out_delay"],
            )
        )

        config["fade_in_delay"] = int(
            raw.get(
                "fade_in_delay",
                config["fade_in_delay"],
            )
        )

        config["fade_duration"] = int(
            raw.get(
                "fade_duration",
                config["fade_duration"],
            )
        )

        # ------------------------------------------------------------
        # Effects Engine migration
        # ------------------------------------------------------------

        legacy_animate_enabled = bool(
            raw.get(
                "animate_enabled",
                config["animate_enabled"],
            )
        )

        legacy_animation_style = str(
            raw.get(
                "animation_style",
                config["animation_style"],
            )
        )

        if "crosshair_effect" in raw:
            requested_effect = str(
                raw.get(
                    "crosshair_effect",
                    config["crosshair_effect"],
                )
            )

        else:
            requested_effect = (
                legacy_animation_style
                if legacy_animate_enabled
                else "static"
            )

        requested_effect = (
            requested_effect
            .strip()
            .lower()
        )

        if valid_effect_names is not None:
            valid_effect_names = set(
                valid_effect_names
            )

            if (
                requested_effect
                not in valid_effect_names
            ):
                requested_effect = "static"

        config["crosshair_effect"] = (
            requested_effect
        )

        # Legacy aliases now derive from the canonical selected effect.
        config["animation_style"] = (
            requested_effect
        )

        config["animate_enabled"] = (
            requested_effect != "static"
        )

        config["animate_speed"] = int(
            raw.get(
                "animate_speed",
                config["animate_speed"],
            )
        )

        config["animate_spacing"] = int(
            raw.get(
                "animate_spacing",
                config["animate_spacing"],
            )
        )

        config["animate_segment_length"] = int(
            raw.get(
                "animate_segment_length",
                config["animate_segment_length"],
            )
        )

        config["pulse_strength"] = float(
            raw.get(
                "pulse_strength",
                config["pulse_strength"],
            )
        )

        config["pulse_period"] = float(
            raw.get(
                "pulse_period",
                config["pulse_period"],
            )
        )

        config["arrow_first_offset"] = int(
            raw.get(
                "arrow_first_offset",
                config["arrow_first_offset"],
            )
        )

        config["arrow_spacing"] = int(
            raw.get(
                "arrow_spacing",
                config["arrow_spacing"],
            )
        )

        config["arrow_length"] = int(
            raw.get(
                "arrow_length",
                config["arrow_length"],
            )
        )

        config["arrow_width"] = int(
            raw.get(
                "arrow_width",
                config["arrow_width"],
            )
        )

        config["arrow_border_over_line"] = bool(
            raw.get(
                "arrow_border_over_line",
                config["arrow_border_over_line"],
            )
        )

        # ------------------------------------------------------------
        # Reticle and magnifier
        # ------------------------------------------------------------

        config["ring_enabled"] = bool(
            raw.get(
                "ring_enabled",
                config["ring_enabled"],
            )
        )

        config["magnifier_enabled"] = bool(
            raw.get(
                "magnifier_enabled",
                config["magnifier_enabled"],
            )
        )

        config["magnification"] = float(
            raw.get(
                "magnification",
                config["magnification"],
            )
        )

        # ------------------------------------------------------------
        # Pomodoro
        # ------------------------------------------------------------

        config["pomodoro_enabled"] = bool(
            raw.get(
                "pomodoro_enabled",
                config["pomodoro_enabled"],
            )
        )

        config["pomodoro_focus_minutes"] = int(
            raw.get(
                "pomodoro_focus_minutes",
                config["pomodoro_focus_minutes"],
            )
        )

        # Migration from the older generic break-duration key.
        config["pomodoro_short_break_minutes"] = int(
            raw.get(
                "pomodoro_short_break_minutes",
                raw.get(
                    "pomodoro_break_minutes",
                    config[
                        "pomodoro_short_break_minutes"
                    ],
                ),
            )
        )

        config["pomodoro_long_break_minutes"] = int(
            raw.get(
                "pomodoro_long_break_minutes",
                config[
                    "pomodoro_long_break_minutes"
                ],
            )
        )

        config[
            "pomodoro_focuses_before_long_break"
        ] = max(
            1,
            int(
                raw.get(
                    "pomodoro_focuses_before_long_break",
                    config[
                        "pomodoro_focuses_before_long_break"
                    ],
                )
            ),
        )

        legacy_auto_start = bool(
            raw.get(
                "pomodoro_auto_start",
                False,
            )
        )

        config["pomodoro_auto_start_break"] = bool(
            raw.get(
                "pomodoro_auto_start_break",
                legacy_auto_start,
            )
        )

        config["pomodoro_auto_start_focus"] = bool(
            raw.get(
                "pomodoro_auto_start_focus",
                legacy_auto_start,
            )
        )

        config["pomodoro_pause_after_cycle"] = bool(
            raw.get(
                "pomodoro_pause_after_cycle",
                config[
                    "pomodoro_pause_after_cycle"
                ],
            )
        )

        config["pomodoro_focus_colour"] = str(
            raw.get(
                "pomodoro_focus_colour",
                config["pomodoro_focus_colour"],
            )
        )

        config["pomodoro_break_colour"] = str(
            raw.get(
                "pomodoro_break_colour",
                config["pomodoro_break_colour"],
            )
        )

        config["pomodoro_timer_text_size"] = int(
            raw.get(
                "pomodoro_timer_text_size",
                config[
                    "pomodoro_timer_text_size"
                ],
            )
        )

        config["pomodoro_ring_thickness"] = float(
            raw.get(
                "pomodoro_ring_thickness",
                config[
                    "pomodoro_ring_thickness"
                ],
            )
        )

        config["pomodoro_icon_size"] = float(
            raw.get(
                "pomodoro_icon_size",
                config["pomodoro_icon_size"],
            )
        )

        # ------------------------------------------------------------
        # Hotkey
        # ------------------------------------------------------------

        config["hotkey_key"] = str(
            raw.get(
                "hotkey_key",
                config["hotkey_key"],
            )
        )

        config["hotkey_modifiers"] = list(
            raw.get(
                "hotkey_modifiers",
                config["hotkey_modifiers"],
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        return defaults, False

    return config, True


def save_config(config):
    """Persist a complete Mousehair configuration dictionary."""
    CONFIG_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    data = default_config()

    # Preserve only settings Mousehair actually knows about.
    for key in data:
        if key in config:
            data[key] = config[key]

    # These remain intentionally derived compatibility fields.
    selected_effect = str(
        data.get(
            "crosshair_effect",
            "static",
        )
    )

    data["animate_enabled"] = (
        selected_effect != "static"
    )

    data["animation_style"] = (
        selected_effect
    )

    temporary_path = CONFIG_PATH.with_suffix(
        ".json.tmp"
    )

    with temporary_path.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            data,
            handle,
            indent=2,
            sort_keys=True,
        )

        handle.write(
            "\n"
        )

    os.replace(
        temporary_path,
        CONFIG_PATH,
    )
