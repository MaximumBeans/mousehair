/*
 * Mousehair Cinnamon Magnifier Proof, version 4.5
 *
 * Diagnostic purpose:
 *
 *   * Keep the centred lens geometry.
 *   * Keep the working D-Bus opacity bridge.
 *   * Remove the circular shader completely.
 *   * Size the diagnostic lens from Mousehair's real JSON settings.
 *   * Keep a conspicuous square border so geometry remains easy to inspect.
 *
 * This version is intentionally not pretty. It isolates whether version 4.1
 * failed because of the shader or because the lens actor itself was misplaced.
 */

const Clutter = imports.gi.Clutter;
const Gio = imports.gi.Gio;
const GLib = imports.gi.GLib;
const St = imports.gi.St;
const GObject = imports.gi.GObject;

const Main = imports.ui.main;


const APPLICATIONS_SCHEMA =
    'org.cinnamon.desktop.a11y.applications';
const MAGNIFIER_SCHEMA =
    'org.cinnamon.desktop.a11y.magnifier';

const SHOW_KEY = 'screen-magnifier-enabled';
const MAG_FACTOR_KEY = 'mag-factor';

const DEFAULT_GAP = 100;
const DEFAULT_MAGNIFICATION = 2.0;
const MOUSEHAIR_CONFIG_PATH =
    GLib.build_filenamev([GLib.get_home_dir(), '.config', 'mousehair', 'config.json']);
const UPDATE_INTERVAL_MS = 16;

const DBUS_NAME = 'org.maximumbeans.Mousehair.Cinnamon';
const DBUS_PATH = '/org/maximumbeans/Mousehair/Cinnamon';

/*
 * Cinnamon handles Super-key shortcuts itself. Registering the Mousehair
 * shortcut here avoids the timing problems encountered with an external X11
 * passive key grab.
 */
const TOGGLE_HOTKEY_NAME = 'mousehair-toggle';
const TOGGLE_HOTKEY_ACCELERATOR = '<Super><Shift>m';

const DBUS_XML = `
<node>
  <interface name="org.maximumbeans.Mousehair.Cinnamon">
    <method name="SetOpacity">
      <arg type="d" name="opacity" direction="in"/>
    </method>
    <method name="SetGeometry">
      <arg type="d" name="gap" direction="in"/>
      <arg type="d" name="magnification" direction="in"/>
    </method>
    <method name="Show"/>
    <method name="Hide"/>
    <method name="GetState">
      <arg type="d" name="opacity" direction="out"/>
      <arg type="b" name="cinnamonMagnifierActive" direction="out"/>
    </method>
  </interface>
</node>
`;

let lens = null;


/*
 * Circular alpha mask for the complete magnifier actor.
 *
 * Clutter first renders the actor into an off-screen texture. The fragment
 * shader then samples that texture and removes pixels outside the circular
 * aperture.
 *
 * The sampler is deliberately not set from JavaScript. Clutter binds the
 * off-screen texture to texture unit zero and GLSL sampler uniforms default
 * to zero. The earlier v4.1 experiment attempted to set the sampler manually,
 * which made the complete actor transparent on this Cinnamon build.
 */
const CircularMaskEffect = GObject.registerClass(
class CircularMaskEffect extends Clutter.ShaderEffect {
    _init() {
        super._init({
            shader_type: Clutter.ShaderType.FRAGMENT_SHADER,
        });

        this.set_shader_source(`
            uniform sampler2D tex;

            void main() {
                vec2 uv = cogl_tex_coord_in[0].st;
                vec4 pixel = texture2D(tex, uv);

                float distanceFromCentre =
                    distance(uv, vec2(0.5, 0.5));

                float feather = 0.004;
                float mask = 1.0 - smoothstep(
                    0.5 - feather,
                    0.5,
                    distanceFromCentre
                );

                cogl_color_out =
                    vec4(pixel.rgb, pixel.a * mask) *
                    cogl_color_in;
            }
        `);
    }
});


class MousehairMagnifierProof {
    constructor() {
        this._lensActor = null;
        this._clone = null;
        this._maskEffect = null;

        this._timerId = 0;
        this._signalIds = [];

        this._applicationsSettings = null;
        this._magnifierSettings = null;

        this._topWindowGroupWasReparented = false;
        this._overlayGroupWasReparented = false;

        this._cinnamonMagnifierActive = false;
        this._requestedOpacity = 1.0;

        /*
         * Mousehair's ring radius is the configured crosshair gap. Therefore
         * the compositor lens diameter is exactly twice the gap.
         */
        this._gap = DEFAULT_GAP;
        this._lensSize = DEFAULT_GAP * 2;
        this._magnification = DEFAULT_MAGNIFICATION;

        this._dbusObject = null;
        this._dbusNameOwnerId = 0;
    }

    enable() {
        this._applicationsSettings = new Gio.Settings({
            schema_id: APPLICATIONS_SCHEMA,
        });

        this._magnifierSettings = new Gio.Settings({
            schema_id: MAGNIFIER_SCHEMA,
        });

        this._signalIds.push([
            this._applicationsSettings,
            this._applicationsSettings.connect(
                `changed::${SHOW_KEY}`,
                () => this._refreshVisibility()
            ),
        ]);

        this._signalIds.push([
            this._magnifierSettings,
            this._magnifierSettings.connect(
                `changed::${MAG_FACTOR_KEY}`,
                () => this._refreshVisibility()
            ),
        ]);

        this._loadMousehairConfiguration();
        this._ensureSharedGroupsInUiGroup();
        this._createLensActor();
        this._exportDbus();
        this._registerToggleHotkey();

        this._refreshVisibility();
        this._updateLens();

        this._timerId = GLib.timeout_add(
            GLib.PRIORITY_DEFAULT,
            UPDATE_INTERVAL_MS,
            () => this._updateLens()
        );
    }

    disable() {
        if (this._timerId) {
            GLib.source_remove(this._timerId);
            this._timerId = 0;
        }

        for (const [settings, signalId] of this._signalIds)
            settings.disconnect(signalId);

        this._signalIds = [];

        /*
         * Remove the native Cinnamon shortcut before destroying the rest of the
         * extension so no callback can arrive during teardown.
         */
        this._unregisterToggleHotkey();
        this._unexportDbus();

        if (this._lensActor) {
            this._lensActor.destroy();
            this._lensActor = null;
            this._clone = null;
            this._maskEffect = null;
            }

        if (!this._isCinnamonMagnifierActive())
            this._restoreSharedGroupsWeMoved();

        this._applicationsSettings = null;
        this._magnifierSettings = null;
    }

    _loadMousehairConfiguration() {
        /*
         * Read the same JSON configuration used by the current Python
         * Mousehair application. This removes the screenshot-derived size
         * guess from earlier proofs.
         *
         * The ring is drawn at the edge of the crosshair gap, so:
         *
         *     ring radius   = gap
         *     lens diameter = gap * 2
         */
        try {
            const [success, contents] =
                GLib.file_get_contents(MOUSEHAIR_CONFIG_PATH);

            if (!success)
                return;

            const config = JSON.parse(
                imports.byteArray.toString(contents)
            );

            const gap = Number(config.gap);
            const magnification = Number(config.magnification);

            if (Number.isFinite(gap) && gap > 0) {
                this._gap = gap;
                this._lensSize = Math.round(gap * 2);
            }

            if (Number.isFinite(magnification) && magnification > 0)
                this._magnification = magnification;
        } catch (error) {
            global.logError(
                error,
                '[Mousehair] Failed to read Mousehair configuration'
            );
        }
    }

    _createLensActor() {
        /*
         * No decorative bezel is drawn in this transition version. The
         * existing PyQt Mousehair ring remains the visible frame, allowing us
         * to judge alignment directly.
         */
        /*
         * Diagnostic square viewport.
         *
         * The circular shader is deliberately absent in version 4.5. A faint
         * coloured background and visible border make the actor's geometry
         * impossible to mistake for a transparent or failed render.
         */
        this._lensActor = new St.Widget({
            reactive: false,
            can_focus: false,
            track_hover: false,
            width: this._lensSize,
            height: this._lensSize,
            clip_to_allocation: true,
            style: [
                'background-color: rgba(80, 30, 120, 0.30);',
                'border: 3px solid rgba(255, 180, 255, 0.95);',
            ].join(' '),
        });

        this._clone = new Clutter.Clone({
            source: Main.uiGroup,
            reactive: false,
        });

        this._lensActor.add_child(this._clone);

        /*
         * Apply the mask after attaching the live clone. The purple diagnostic
         * viewport from v4.4 remains in place, but only its circular portion
         * should now be visible.
         */
        this._maskEffect = new CircularMaskEffect();
        this._lensActor.add_effect_with_name(
            'mousehair-circular-mask',
            this._maskEffect
        );

        /*
         * The lens stays outside Main.uiGroup. It therefore cannot appear in
         * the scene that it clones, avoiding recursive magnification.
         */
        global.stage.add_child(this._lensActor);
        this._lensActor.raise_top();
    }

    _ensureSharedGroupsInUiGroup() {
        if (global.top_window_group.get_parent() !== Main.uiGroup) {
            global.reparentActor(global.top_window_group, Main.uiGroup);
            this._topWindowGroupWasReparented = true;
        }

        if (global.overlay_group.get_parent() !== Main.uiGroup) {
            global.reparentActor(global.overlay_group, Main.uiGroup);
            this._overlayGroupWasReparented = true;
        }
    }

    _restoreSharedGroupsWeMoved() {
        if (this._topWindowGroupWasReparented) {
            global.reparentActor(
                global.top_window_group,
                global.stage
            );
            this._topWindowGroupWasReparented = false;
        }

        if (this._overlayGroupWasReparented) {
            global.reparentActor(
                global.overlay_group,
                global.stage
            );
            this._overlayGroupWasReparented = false;
        }
    }

    _isCinnamonMagnifierActive() {
        if (!this._applicationsSettings || !this._magnifierSettings)
            return false;

        const enabled =
            this._applicationsSettings.get_boolean(SHOW_KEY);
        const factor =
            this._magnifierSettings.get_double(MAG_FACTOR_KEY);

        return enabled && factor > 1.0;
    }

    _refreshVisibility() {
        this._cinnamonMagnifierActive =
            this._isCinnamonMagnifierActive();

        if (!this._lensActor)
            return;

        /*
         * Cinnamon magnification always wins. Mousehair's own lens disappears,
         * while the ordinary Mousehair overlay remains inside Cinnamon's
         * magnified scene.
         */
        if (this._cinnamonMagnifierActive) {
            this._lensActor.hide();
            return;
        }

        this._ensureSharedGroupsInUiGroup();

        if (this._requestedOpacity <= 0.0) {
            this._lensActor.hide();
            return;
        }

        this._lensActor.opacity = Math.round(
            this._requestedOpacity * 255
        );
        this._lensActor.show();
        this._lensActor.raise_top();
    }

    _setOpacity(opacity) {
        this._requestedOpacity = Math.max(
            0.0,
            Math.min(1.0, Number(opacity))
        );

        this._refreshVisibility();
    }

    _setGeometry(gap, magnification) {
        /*
         * Mousehair's PyQt ring is drawn at radius ``gap``. The compositor lens
         * therefore needs a diameter of ``gap * 2`` to remain aligned with it.
         */
        const requestedGap = Number(gap);
        const requestedMagnification = Number(magnification);

        if (
            Number.isFinite(requestedGap) &&
            requestedGap > 0
        ) {
            this._gap = requestedGap;
            this._lensSize = Math.max(
                2,
                Math.round(requestedGap * 2)
            );
        }

        if (
            Number.isFinite(requestedMagnification) &&
            requestedMagnification >= 1.0
        ) {
            this._magnification = requestedMagnification;
        }

        if (this._lensActor) {
            this._lensActor.set_size(
                this._lensSize,
                this._lensSize
            );
        }

        /*
         * Recalculate the actor and clone positions immediately rather than
         * waiting for the next normal 16 ms compositor update.
         */
        this._updateLens();
        this._refreshVisibility();
    }

    _updateLens() {
        if (!this._lensActor || !this._clone)
            return GLib.SOURCE_REMOVE;

        const cinnamonActive = this._isCinnamonMagnifierActive();

        if (cinnamonActive !== this._cinnamonMagnifierActive)
            this._refreshVisibility();

        if (this._cinnamonMagnifierActive)
            return GLib.SOURCE_CONTINUE;

        const [pointerX, pointerY] = global.get_pointer();

        /*
         * Centre the lens directly on the pointer and, therefore, on the
         * existing Mousehair ring.
         */
        const lensX = pointerX - this._lensSize / 2;
        const lensY = pointerY - this._lensSize / 2;

        this._lensActor.set_position(
            Math.round(lensX),
            Math.round(lensY)
        );

        this._clone.set_scale(
            this._magnification,
            this._magnification
        );

        /*
         * The desktop point under the pointer belongs at the centre of the
         * magnified lens.
         */
        const cloneX =
            this._lensSize / 2 - pointerX * this._magnification;
        const cloneY =
            this._lensSize / 2 - pointerY * this._magnification;

        this._clone.set_position(
            Math.round(cloneX),
            Math.round(cloneY)
        );

        this._lensActor.raise_top();

        return GLib.SOURCE_CONTINUE;
    }

    _registerToggleHotkey() {
        /*
         * Cinnamon's keybinding manager is the authoritative owner of Super-key
         * combinations. The callback is invoked directly by the compositor.
         */
        Main.keybindingManager.addHotKey(
            TOGGLE_HOTKEY_NAME,
            TOGGLE_HOTKEY_ACCELERATOR,
            () => this._requestMousehairToggle()
        );
    }

    _unregisterToggleHotkey() {
        Main.keybindingManager.removeHotKey(
            TOGGLE_HOTKEY_NAME
        );
    }

    _requestMousehairToggle() {
        /*
         * Send SIGUSR1 to the running Python application.
         *
         * The bracketed character in [m]ousehair.py prevents pkill from
         * accidentally matching its own command line.
         */
        try {
            GLib.spawn_command_line_async(
                "pkill -USR1 -f '[m]ousehair.py'"
            );
        } catch (error) {
            global.logError(
                error,
                '[Mousehair] Failed to send hotkey toggle request'
            );
        }
    }

    _exportDbus() {
        this._dbusObject = Gio.DBusExportedObject.wrapJSObject(
            DBUS_XML,
            {
                SetOpacity: opacity => this._setOpacity(opacity),

                SetGeometry: (gap, magnification) =>
                    this._setGeometry(gap, magnification),

                Show: () => this._setOpacity(1.0),

                Hide: () => this._setOpacity(0.0),

                GetState: () => [
                    this._requestedOpacity,
                    this._cinnamonMagnifierActive,
                ],
            }
        );

        this._dbusObject.export(
            Gio.DBus.session,
            DBUS_PATH
        );

        this._dbusNameOwnerId = Gio.bus_own_name(
            Gio.BusType.SESSION,
            DBUS_NAME,
            Gio.BusNameOwnerFlags.NONE,
            null,
            null,
            null
        );
    }

    _unexportDbus() {
        if (this._dbusObject) {
            this._dbusObject.unexport();
            this._dbusObject = null;
        }

        if (this._dbusNameOwnerId) {
            Gio.bus_unown_name(this._dbusNameOwnerId);
            this._dbusNameOwnerId = 0;
        }
    }
}


function init(metadata) {
}


function enable() {
    if (lens)
        return;

    lens = new MousehairMagnifierProof();
    lens.enable();
}


function disable() {
    if (!lens)
        return;

    lens.disable();
    lens = null;
}
