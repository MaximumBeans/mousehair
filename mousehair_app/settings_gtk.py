"""Standalone GTK settings application for Mousehair."""

from __future__ import annotations

import os
import signal
import subprocess

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gdk, Gtk

from .config import (
    load_config,
    save_config,
)

from .effects import (
    ArrowCrosshairEffect,
    PulseCrosshairEffect,
    SlidingCrosshairEffect,
    StaticCrosshairEffect,
)


EFFECT_CLASSES = (
    StaticCrosshairEffect,
    SlidingCrosshairEffect,
    ArrowCrosshairEffect,
    PulseCrosshairEffect,
)


class MousehairSettingsWindow(Gtk.Window):
    """Native GTK configuration window for Mousehair."""

    def __init__(self):
        super().__init__(
            title="Mousehair Settings"
        )

        self.set_default_size(
            900,
            650,
        )

        self.set_border_width(
            0
        )

        self.connect(
            "destroy",
            Gtk.main_quit,
        )

        valid_effect_names = {
            effect.name
            for effect in EFFECT_CLASSES
        }

        self.config, _valid = load_config(
            valid_effect_names=valid_effect_names,
        )

        self.controls = {}

        self._build_ui()

    # ============================================================
    # Generic helpers
    # ============================================================

    def _heading(self, text):
        label = Gtk.Label()
        label.set_markup(
            f"<span size='x-large' weight='bold'>{text}</span>"
        )
        label.set_xalign(0.0)

        return label

    def _description(self, text):
        label = Gtk.Label(
            label=text
        )

        label.set_xalign(
            0.0
        )

        label.set_line_wrap(
            True
        )

        return label

    def _page(self, title, description=None):
        outer = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=16,
        )

        outer.set_border_width(
            20
        )

        outer.pack_start(
            self._heading(title),
            False,
            False,
            0,
        )

        if description:
            outer.pack_start(
                self._description(description),
                False,
                False,
                0,
            )

        grid = Gtk.Grid(
            column_spacing=20,
            row_spacing=14,
        )

        grid.set_hexpand(
            True
        )

        outer.pack_start(
            grid,
            False,
            False,
            0,
        )

        return outer, grid

    def _add_label(
        self,
        grid,
        row,
        text,
    ):
        label = Gtk.Label(
            label=text
        )

        label.set_xalign(
            0.0
        )

        grid.attach(
            label,
            0,
            row,
            1,
            1,
        )

        return label

    def _switch(
        self,
        grid,
        row,
        key,
        label_text,
    ):
        self._add_label(
            grid,
            row,
            label_text,
        )

        switch = Gtk.Switch()

        switch.set_active(
            bool(
                self.config.get(
                    key,
                    False,
                )
            )
        )

        switch.set_halign(
            Gtk.Align.END
        )

        grid.attach(
            switch,
            1,
            row,
            1,
            1,
        )

        self.controls[key] = (
            "switch",
            switch,
        )

        return switch

    def _spin(
        self,
        grid,
        row,
        key,
        label_text,
        minimum,
        maximum,
        step=1,
        digits=0,
    ):
        self._add_label(
            grid,
            row,
            label_text,
        )

        spin = Gtk.SpinButton.new_with_range(
            minimum,
            maximum,
            step,
        )

        spin.set_digits(
            digits
        )

        spin.set_numeric(
            True
        )

        spin.set_value(
            float(
                self.config.get(
                    key,
                    minimum,
                )
            )
        )

        grid.attach(
            spin,
            1,
            row,
            1,
            1,
        )

        self.controls[key] = (
            "float" if digits else "int",
            spin,
        )

        return spin

    def _slider_with_entry(
        self,
        grid,
        row,
        key,
        label_text,
        minimum,
        maximum,
        step,
        digits=0,
    ):
        """Create a GTK slider linked bidirectionally to a numeric text box."""
        self._add_label(
            grid,
            row,
            label_text,
        )

        box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12,
        )

        adjustment = Gtk.Adjustment(
            value=float(
                self.config.get(
                    key,
                    minimum,
                )
            ),
            lower=minimum,
            upper=maximum,
            step_increment=step,
            page_increment=step * 5,
        )

        scale = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL,
            adjustment=adjustment,
        )

        scale.set_draw_value(
            False
        )

        scale.set_hexpand(
            True
        )

        spin = Gtk.SpinButton(
            adjustment=adjustment,
            climb_rate=step,
            digits=digits,
        )

        spin.set_numeric(
            True
        )

        spin.set_width_chars(
            7
        )

        box.pack_start(
            scale,
            True,
            True,
            0,
        )

        box.pack_start(
            spin,
            False,
            False,
            0,
        )

        grid.attach(
            box,
            1,
            row,
            1,
            1,
        )

        self.controls[key] = (
            "float" if digits else "int",
            spin,
        )

        return scale, spin

    def _colour(
        self,
        grid,
        row,
        key,
        label_text,
    ):
        self._add_label(
            grid,
            row,
            label_text,
        )

        button = Gtk.ColorButton()

        rgba = Gdk.RGBA()

        if not rgba.parse(
            str(
                self.config.get(
                    key,
                    "#FFFFFF",
                )
            )
        ):
            rgba.parse(
                "#FFFFFF"
            )

        button.set_rgba(
            rgba
        )

        button.set_use_alpha(
            False
        )

        grid.attach(
            button,
            1,
            row,
            1,
            1,
        )

        self.controls[key] = (
            "colour",
            button,
        )

        return button

    # ============================================================
    # Navigation
    # ============================================================

    def _build_ui(self):
        root = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0,
        )

        self.add(
            root
        )

        body = Gtk.Paned(
            orientation=Gtk.Orientation.HORIZONTAL
        )

        body.set_position(
            230
        )

        root.pack_start(
            body,
            True,
            True,
            0,
        )

        self.tree_store = Gtk.TreeStore(
            str,
            str,
        )

        self.tree = Gtk.TreeView(
            model=self.tree_store
        )

        self.tree.set_headers_visible(
            False
        )

        renderer = Gtk.CellRendererText()

        column = Gtk.TreeViewColumn(
            "Settings",
            renderer,
            text=0,
        )

        self.tree.append_column(
            column
        )

        tree_scroll = Gtk.ScrolledWindow()
        tree_scroll.set_policy(
            Gtk.PolicyType.NEVER,
            Gtk.PolicyType.AUTOMATIC,
        )

        tree_scroll.add(
            self.tree
        )

        body.pack1(
            tree_scroll,
            resize=False,
            shrink=False,
        )

        self.stack = Gtk.Stack()

        self.stack.set_transition_type(
            Gtk.StackTransitionType.CROSSFADE
        )

        content_scroll = Gtk.ScrolledWindow()

        content_scroll.set_policy(
            Gtk.PolicyType.NEVER,
            Gtk.PolicyType.AUTOMATIC,
        )

        content_scroll.add(
            self.stack
        )

        body.pack2(
            content_scroll,
            resize=True,
            shrink=False,
        )

        self._build_pages()
        self._build_tree()

        selection = (
            self.tree.get_selection()
        )

        selection.connect(
            "changed",
            self._tree_selection_changed,
        )

        # Bottom action bar.
        action_bar = Gtk.ButtonBox(
            orientation=Gtk.Orientation.HORIZONTAL
        )

        action_bar.set_layout(
            Gtk.ButtonBoxStyle.END
        )

        action_bar.set_border_width(
            10
        )

        cancel_button = Gtk.Button(
            label="Cancel"
        )

        apply_button = Gtk.Button(
            label="Apply"
        )

        ok_button = Gtk.Button(
            label="OK"
        )

        cancel_button.connect(
            "clicked",
            lambda _button: self.destroy(),
        )

        apply_button.connect(
            "clicked",
            lambda _button: self.apply(),
        )

        ok_button.connect(
            "clicked",
            self._ok_clicked,
        )

        action_bar.add(
            cancel_button
        )

        action_bar.add(
            apply_button
        )

        action_bar.add(
            ok_button
        )

        root.pack_end(
            action_bar,
            False,
            False,
            0,
        )

    def _tree_item(
        self,
        parent,
        label,
        page_name,
    ):
        return self.tree_store.append(
            parent,
            [
                label,
                page_name,
            ],
        )

    def _build_tree(self):
        general = self._tree_item(
            None,
            "General",
            "general",
        )

        appearance = self._tree_item(
            None,
            "Appearance",
            "crosshair",
        )

        self._tree_item(
            appearance,
            "Crosshair",
            "crosshair",
        )

        self._tree_item(
            appearance,
            "Magnifier",
            "magnifier",
        )

        effects = self._tree_item(
            None,
            "Effects",
            "effects",
        )

        complications = self._tree_item(
            None,
            "Complications",
            "pomodoro_timer",
        )

        pomodoro = self._tree_item(
            complications,
            "Pomodoro",
            "pomodoro_timer",
        )

        self._tree_item(
            pomodoro,
            "Timer",
            "pomodoro_timer",
        )

        self._tree_item(
            pomodoro,
            "Appearance",
            "pomodoro_appearance",
        )

        self._tree_item(
            pomodoro,
            "Sounds",
            "pomodoro_sounds",
        )

        self._tree_item(
            pomodoro,
            "Hotkeys",
            "pomodoro_hotkeys",
        )

        self._tree_item(
            pomodoro,
            "Placement",
            "pomodoro_placement",
        )

        self._tree_item(
            None,
            "Keyboard Shortcuts",
            "shortcuts",
        )

        self.tree.expand_all()

        self.tree.get_selection().select_iter(
            general
        )

    def _tree_selection_changed(
        self,
        selection,
    ):
        model, tree_iter = (
            selection.get_selected()
        )

        if tree_iter is None:
            return

        page_name = model.get_value(
            tree_iter,
            1,
        )

        self.stack.set_visible_child_name(
            page_name
        )

    # ============================================================
    # Pages
    # ============================================================

    def _build_pages(self):
        self._build_general_page()
        self._build_crosshair_page()
        self._build_effects_page()
        self._build_magnifier_page()
        self._build_pomodoro_timer_page()
        self._build_pomodoro_appearance_page()

        for name, title, text in (
            (
                "pomodoro_sounds",
                "Pomodoro Sounds",
                "Work and break start/end sounds will be configured here.",
            ),
            (
                "pomodoro_hotkeys",
                "Pomodoro Hotkeys",
                "Global Pomodoro controls will be configured here.",
            ),
            (
                "pomodoro_placement",
                "Pomodoro Placement",
                "Ring, countdown and icon placement controls will live here.",
            ),
            (
                "shortcuts",
                "Keyboard Shortcuts",
                "Mousehair-wide configurable shortcuts will be moved here.",
            ),
        ):
            page, _grid = self._page(
                title,
                text,
            )

            self.stack.add_named(
                page,
                name,
            )

    def _build_general_page(self):
        page, grid = self._page(
            "General",
            "Application startup and global overlay behaviour.",
        )

        row = 0

        self._switch(
            grid,
            row,
            "start_with_system",
            "Start with system",
        )
        row += 1

        self._slider_with_entry(
            grid,
            row,
            "alpha",
            "Overlay opacity",
            0.0,
            1.0,
            0.05,
            digits=2,
        )
        row += 1

        self._switch(
            grid,
            row,
            "fade_enabled",
            "Enable fade",
        )
        row += 1

        self._slider_with_entry(
            grid,
            row,
            "fade_out_delay",
            "Fade-out delay (ms)",
            0,
            5000,
            50,
        )
        row += 1

        self._slider_with_entry(
            grid,
            row,
            "fade_in_delay",
            "Fade-in delay (ms)",
            0,
            5000,
            50,
        )
        row += 1

        self._slider_with_entry(
            grid,
            row,
            "fade_duration",
            "Fade duration (ms)",
            0,
            5000,
            50,
        )

        self.stack.add_named(
            page,
            "general",
        )

    def _build_crosshair_page(self):
        page, grid = self._page(
            "Crosshair",
            "Crosshair and ring geometry, colours and visibility.",
        )

        row = 0

        self._slider_with_entry(
            grid,
            row,
            "gap",
            "Pointer gap (px)",
            0,
            500,
            1,
        )
        row += 1

        self._slider_with_entry(
            grid,
            row,
            "outer_thickness",
            "Outer line thickness (px)",
            1,
            20,
            1,
        )
        row += 1

        self._slider_with_entry(
            grid,
            row,
            "inner_thickness",
            "Inner line thickness (px)",
            1,
            20,
            1,
        )
        row += 1

        self._colour(
            grid,
            row,
            "outer_color",
            "Outer colour",
        )
        row += 1

        self._colour(
            grid,
            row,
            "inner_color",
            "Inner colour",
        )
        row += 1

        self._switch(
            grid,
            row,
            "ring_enabled",
            "Enable ring reticule",
        )

        self.stack.add_named(
            page,
            "crosshair",
        )

    def _build_magnifier_page(self):
        page, grid = self._page(
            "Magnifier",
            "Pointer-centred compositor magnification.",
        )

        row = 0

        self._switch(
            grid,
            row,
            "magnifier_enabled",
            "Enable magnifier",
        )
        row += 1

        self._slider_with_entry(
            grid,
            row,
            "magnification",
            "Magnification",
            1.25,
            5.0,
            0.25,
            digits=2,
        )

        self.stack.add_named(
            page,
            "magnifier",
        )

    def _build_effects_page(self):
        page, grid = self._page(
            "Effects",
            "Choose how the crosshair itself is rendered.",
        )

        self._add_label(
            grid,
            0,
            "Crosshair effect",
        )

        combo = Gtk.ComboBoxText()

        selected = str(
            self.config.get(
                "crosshair_effect",
                "static",
            )
        )

        selected_index = 0

        for index, effect in enumerate(
            EFFECT_CLASSES
        ):
            combo.append(
                effect.name,
                effect.display_name,
            )

            if effect.name == selected:
                selected_index = index

        combo.set_active(
            selected_index
        )

        grid.attach(
            combo,
            1,
            0,
            1,
            1,
        )

        self.controls[
            "crosshair_effect"
        ] = (
            "combo",
            combo,
        )

        self.stack.add_named(
            page,
            "effects",
        )

    def _build_pomodoro_timer_page(self):
        page, grid = self._page(
            "Pomodoro Timer",
            "Focus, break and cycle behaviour.",
        )

        row = 0

        self._switch(
            grid,
            row,
            "pomodoro_enabled",
            "Enable Pomodoro",
        )
        row += 1

        self._spin(
            grid,
            row,
            "pomodoro_focus_minutes",
            "Focus duration (minutes)",
            1,
            180,
        )
        row += 1

        self._spin(
            grid,
            row,
            "pomodoro_short_break_minutes",
            "Short break (minutes)",
            1,
            60,
        )
        row += 1

        self._spin(
            grid,
            row,
            "pomodoro_long_break_minutes",
            "Long break (minutes)",
            1,
            120,
        )
        row += 1

        self._spin(
            grid,
            row,
            "pomodoro_focuses_before_long_break",
            "Focuses before long break",
            1,
            20,
        )
        row += 1

        self._switch(
            grid,
            row,
            "pomodoro_auto_start_break",
            "Automatically start breaks",
        )
        row += 1

        self._switch(
            grid,
            row,
            "pomodoro_auto_start_focus",
            "Automatically start next focus",
        )
        row += 1

        self._switch(
            grid,
            row,
            "pomodoro_pause_after_cycle",
            "Stop after a full Pomodoro cycle",
        )

        self.stack.add_named(
            page,
            "pomodoro_timer",
        )

    def _build_pomodoro_appearance_page(self):
        page, grid = self._page(
            "Pomodoro Appearance",
            "Colours and dimensions of the pointer-centred timer.",
        )

        row = 0

        self._colour(
            grid,
            row,
            "pomodoro_focus_colour",
            "Focus ring colour",
        )
        row += 1

        self._colour(
            grid,
            row,
            "pomodoro_break_colour",
            "Break ring colour",
        )
        row += 1

        self._slider_with_entry(
            grid,
            row,
            "pomodoro_timer_text_size",
            "Countdown text size (px)",
            8,
            72,
            1,
        )
        row += 1

        self._slider_with_entry(
            grid,
            row,
            "pomodoro_ring_thickness",
            "Ring thickness (px)",
            1,
            60,
            1,
        )
        row += 1

        self._slider_with_entry(
            grid,
            row,
            "pomodoro_icon_size",
            "Tomato icon size (px)",
            6,
            120,
            1,
        )

        self.stack.add_named(
            page,
            "pomodoro_appearance",
        )

    # ============================================================
    # Apply / save
    # ============================================================

    def _collect(self):
        updated = dict(
            self.config
        )

        for key, (
            kind,
            widget,
        ) in self.controls.items():

            if kind == "switch":
                value = widget.get_active()

            elif kind == "int":
                value = widget.get_value_as_int()

            elif kind == "float":
                value = float(
                    widget.get_value()
                )

            elif kind == "combo":
                value = widget.get_active_id()

            elif kind == "colour":
                rgba = widget.get_rgba()

                value = "#{:02x}{:02x}{:02x}".format(
                    round(rgba.red * 255),
                    round(rgba.green * 255),
                    round(rgba.blue * 255),
                )

            else:
                continue

            updated[key] = value

        return updated

    def _signal_runtime_reload(self):
        """Ask any running Mousehair process to reread config."""
        try:
            subprocess.run(
                [
                    "pkill",
                    "-USR2",
                    "-f",
                    "[m]ousehair.py",
                ],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        except OSError:
            pass

    def apply(self):
        self.config = self._collect()

        save_config(
            self.config
        )

        self._signal_runtime_reload()

    def _ok_clicked(
        self,
        _button,
    ):
        self.apply()
        self.destroy()


def main():
    window = MousehairSettingsWindow()
    window.show_all()

    Gtk.main()


if __name__ == "__main__":
    main()
