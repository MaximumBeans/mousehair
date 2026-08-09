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
    <method name="SetRingStyle">
      <arg type="d" name="radius" direction="in"/>
      <arg type="d" name="outerThickness" direction="in"/>
      <arg type="d" name="innerThickness" direction="in"/>
      <arg type="s" name="outerColour" direction="in"/>
      <arg type="s" name="innerColour" direction="in"/>
    </method>
    <method name="Heartbeat"/>
    <method name="SetPomodoroState">
      <arg type="b" name="enabled" direction="in"/>
      <arg type="s" name="phase" direction="in"/>
      <arg type="d" name="progress" direction="in"/>
      <arg type="d" name="remainingSeconds" direction="in"/>
      <arg type="s" name="focusColour" direction="in"/>
      <arg type="s" name="breakColour" direction="in"/>
      <arg type="i" name="timerTextSize" direction="in"/>
      <arg type="d" name="ringThickness" direction="in"/>
      <arg type="d" name="iconSize" direction="in"/>
    </method>
    <method name="SynchroniseState">
      <arg type="d" name="lensRadius" direction="in"/>
      <arg type="d" name="magnification" direction="in"/>
      <arg type="d" name="ringRadius" direction="in"/>
      <arg type="d" name="outerThickness" direction="in"/>
      <arg type="d" name="innerThickness" direction="in"/>
      <arg type="s" name="outerColour" direction="in"/>
      <arg type="s" name="innerColour" direction="in"/>
      <arg type="d" name="opacity" direction="in"/>
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

        this._ringActor = null;
        this._ringRadius = this._gap;
        this._ringOuterThickness = 4.0;
        this._ringInnerThickness = 2.0;
        this._ringOuterColour = '#000000';
        this._ringInnerColour = '#FFFFFF';

        /*
         * Pomodoro state is supplied by the Python application. Cinnamon owns
         * only the compositor-side presentation.
         */
        this._pomodoroEnabled = false;
        this._pomodoroPhase = 'focus';
        this._pomodoroProgress = 0.0;
        this._pomodoroRemainingSeconds = 25 * 60;
        this._pomodoroFocusColour = '#E53935';
        this._pomodoroBreakColour = '#43A047';
        this._pomodoroTimerTextSize = 16;
        this._pomodoroRingThickness = 5.0;
        this._pomodoroIconSize = 14.0;
        /*
         * The apparent circular lens is assembled from thin rectangular
         * magnified chords. Everything outside those chords remains
         * transparent, allowing the real desktop beneath to show through.
         */
        this._magnifiedStrips = [];
        /*
         * Four-pixel chords approximately halve the number of Clutter clones
         * that must move with every pointer update. The compositor-native ring
         * covers the lens boundary, so the larger strips should not visibly
         * alter the circular edge.
         */
        this._stripHeight = 4;

        /*
         * Retained as null only so older teardown code and diagnostic builds
         * cannot accidentally encounter an undefined field.
         */
        this._clone = null;
        this._maskEffect = null;

        this._timerId = 0;
        this._signalIds = [];

        this._applicationsSettings = null;
        this._magnifierSettings = null;

        this._topWindowGroupWasReparented = false;
        this._overlayGroupWasReparented = false;

        this._cinnamonMagnifierActive = false;
        this._requestedOpacity = 0.0;

        // Mousehair must actively keep the compositor lens alive.
        // Starting hidden prevents the extension appearing by itself.
        this._lastHeartbeatUs = 0;

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
        this._createRingActor();
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
            this._magnifiedStrips = [];
            this._clone = null;
            this._maskEffect = null;
            }

        if (this._ringActor) {
            this._ringActor.destroy();
            this._ringActor = null;
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
         * The outer actor is only a rectangular viewport and position anchor.
         * It contains no coloured background, border, or shader.
         */
        this._lensActor = new Clutter.Actor({
            reactive: false,
            width: this._lensSize,
            height: this._lensSize,
            clip_to_allocation: true,
        });

        /*
         * Magnified circular content is assembled from thin rectangular
         * chords. Rebuilding is also used whenever Gap changes.
         */
        this._rebuildMagnifiedStrips();

        /*
         * Keep every lens actor outside Main.uiGroup. Main.uiGroup is the clone
         * source, so excluding the lens prevents recursive self-magnification.
         */
        global.stage.add_child(this._lensActor);
        this._lensActor.raise_top();
    }

    _rebuildMagnifiedStrips() {
        /*
         * Destroy strips belonging to the previous lens size.
         */
        for (const entry of this._magnifiedStrips) {
            if (entry.actor)
                entry.actor.destroy();
        }

        this._magnifiedStrips = [];

        if (!this._lensActor || this._lensSize <= 0)
            return;

        const diameter = this._lensSize;
        const radius = diameter / 2.0;
        const stripHeight = Math.max(1, this._stripHeight);

        /*
         * For each horizontal band, calculate the width of the corresponding
         * circle chord:
         *
         *     halfChord = sqrt(radius² - distanceFromCentre²)
         *
         * The chord actor clips its magnified clone to that rectangle.
         */
        for (let top = 0; top < diameter; top += stripHeight) {
            const actualHeight = Math.min(
                stripHeight,
                diameter - top
            );

            const sampleY = Math.min(
                diameter - 0.5,
                top + actualHeight / 2.0
            );

            const dy = sampleY - radius;
            const inside = Math.max(
                0.0,
                radius * radius - dy * dy
            );
            const halfChord = Math.sqrt(inside);

            let left = Math.floor(radius - halfChord);
            let right = Math.ceil(radius + halfChord);

            left = Math.max(0, Math.min(diameter, left));
            right = Math.max(left, Math.min(diameter, right));

            const chordWidth = right - left;

            if (chordWidth <= 0)
                continue;

            const stripActor = new Clutter.Actor({
                reactive: false,
                x: left,
                y: top,
                width: chordWidth,
                height: actualHeight,
                clip_to_allocation: true,
            });

            const stripClone = new Clutter.Clone({
                source: Main.uiGroup,
                reactive: false,
            });

            /*
             * Magnification changes only when SetGeometry is received.
             * SetGeometry rebuilds all strips, so applying the scale once here
             * avoids repeating an unchanged operation on every compositor
             * frame.
             */
            stripClone.set_scale(
                this._magnification,
                this._magnification
            );

            stripActor.add_child(stripClone);
            this._lensActor.add_child(stripActor);

            this._magnifiedStrips.push({
                actor: stripActor,
                clone: stripClone,
                left,
                top,
            });
        }
    }

    _parseHexColour(value, fallback) {
        const text = String(value || fallback || '#FFFFFF').trim();
        const match = /^#?([0-9a-fA-F]{6})$/.exec(text);

        if (!match)
            return this._parseHexColour(fallback || '#FFFFFF', '#FFFFFF');

        const packed = match[1];

        return {
            red: parseInt(packed.slice(0, 2), 16) / 255.0,
            green: parseInt(packed.slice(2, 4), 16) / 255.0,
            blue: parseInt(packed.slice(4, 6), 16) / 255.0,
        };
    }

    _createRingActor() {
        /*
         * St.DrawingArea paints after the magnified strips and is raised above
         * the lens actor. This is the visible compositor-native ring.
         */
        this._ringActor = new St.DrawingArea({
            reactive: false,
            can_focus: false,
            track_hover: false,
        });

        this._ringActor.connect(
            'repaint',
            actor => this._paintRing(actor)
        );

        global.stage.add_child(this._ringActor);
        this._resizeRingActor();
        this._ringActor.raise_top();
    }

    _resizeRingActor() {
        if (!this._ringActor)
            return;

        /*
         * PyQt draws the ring stroke centred at _ringRadius. The allocation
         * must therefore include half of the outer stroke beyond that radius,
         * plus a small antialiasing margin.
         */
        const outerHalfWidth = Math.max(
            0.0,
            Number(this._ringOuterThickness) / 2.0
        );

        let visibleExtent =
            this._ringRadius + outerHalfWidth;

        if (this._pomodoroEnabled) {
            const pomodoroExtent =
                this._pomodoroProgressRadius()
                + Math.max(
                    3.0,
                    Number(this._pomodoroIconSize) / 2.0
                );

            visibleExtent = Math.max(
                visibleExtent,
                pomodoroExtent
            );
        }

        const diameter = Math.max(
            2,
            Math.ceil(
                visibleExtent * 2.0 + 4.0
            )
        );

        this._ringActor.set_size(diameter, diameter);
        this._ringActor.queue_repaint();
    }

    _pomodoroProgressRadius() {
        const outerHalfWidth = Math.max(
            0.0,
            Number(this._ringOuterThickness) / 2.0
        );

        const ringInnerEdge = Math.max(
            1.0,
            Number(this._ringRadius) - outerHalfWidth
        );

        const thickness = Math.max(
            1.0,
            Number(this._pomodoroRingThickness)
        );

        return Math.max(
            8.0,
            Math.min(
                Number(this._ringRadius),
                ringInnerEdge - 5.0 - thickness / 2.0
            )
        );
    }

    _paintPomodoro(context, centreX, centreY) {
        if (!this._pomodoroEnabled)
            return;

        const thickness = Math.max(
            1.0,
            Number(this._pomodoroRingThickness)
        );

        const iconRadius = Math.max(
            3.0,
            Number(this._pomodoroIconSize) / 2.0
        );

        const progress = Math.max(
            0.0,
            Math.min(
                1.0,
                Number(this._pomodoroProgress)
            )
        );

        const radius = this._pomodoroProgressRadius();

        const isFocus =
            this._pomodoroPhase === 'focus';

        /*
         * Focus is tomato red. Both short and long breaks use green by
         * default so the current mode is obvious without reading text.
         */
        const progressColour = this._parseHexColour(
            isFocus
                ? this._pomodoroFocusColour
                : this._pomodoroBreakColour,
            isFocus
                ? '#E53935'
                : '#43A047'
        );

        const trackColour = {
            red: progressColour.red * 0.28,
            green: progressColour.green * 0.28,
            blue: progressColour.blue * 0.28,
        };

        context.setSourceRGBA(
            trackColour.red,
            trackColour.green,
            trackColour.blue,
            0.70
        );

        context.setLineWidth(thickness);

        /*
         * Reserve real angular space for the tomato. The first visible pixel
         * of the timer is immediately clockwise of the marker and 100% ends
         * immediately on its other side.
         */
        const markerClearance = Math.max(
            2.0,
            thickness / 2.0
        );

        const hiddenHalfWidth =
            iconRadius
            + markerClearance;

        const gapRatio = Math.min(
            0.95,
            hiddenHalfWidth
                / Math.max(
                    1.0,
                    radius
                )
        );

        const markerHalfAngle = Math.asin(
            gapRatio
        );

        const usableSpan = Math.max(
            0.01,
            Math.PI * 2.0
                - markerHalfAngle * 2.0
        );

        /*
         * Cairo's positive angular direction appears clockwise in screen
         * coordinates because Y increases downward.
         */
        const arcStart =
            -Math.PI / 2.0
            + markerHalfAngle;

        const arcEnd =
            arcStart
            + usableSpan;

        context.arc(
            centreX,
            centreY,
            radius,
            arcStart,
            arcEnd
        );

        context.stroke();

        /*
         * Filled elapsed-time arc.
         */
        if (progress > 0.0) {
            context.setSourceRGBA(
                progressColour.red,
                progressColour.green,
                progressColour.blue,
                1.0
            );

            context.setLineWidth(thickness);

            context.arc(
                centreX,
                centreY,
                radius,
                arcStart,
                arcStart
                    + usableSpan * progress
            );

            context.stroke();
        }

        /*
         * Countdown at 6 o'clock.
         */
        const remaining = Math.max(
            0,
            Math.ceil(
                this._pomodoroRemainingSeconds
            )
        );

        const minutes = Math.floor(
            remaining / 60
        );

        const seconds = (
            remaining % 60
        );

        const countdown =
            String(minutes).padStart(2, '0')
            + ':'
            + String(seconds).padStart(2, '0');

        context.selectFontFace(
            'Sans',
            0,
            1
        );
        context.setFontSize(
            Math.max(
                8.0,
                Number(this._pomodoroTimerTextSize)
            )
        );

        const extents = context.textExtents(
            countdown
        );

        const textX =
            centreX
            - extents.width / 2.0
            - extents.xBearing;

        const textY =
            centreY
            + radius
            - 14.0;

        const paddingX = 6.0;
        const paddingY = 4.0;

        context.setSourceRGBA(
            0.0,
            0.0,
            0.0,
            0.72
        );

        context.rectangle(
            textX
                + extents.xBearing
                - paddingX,
            textY
                + extents.yBearing
                - paddingY,
            extents.width
                + paddingX * 2.0,
            extents.height
                + paddingY * 2.0
        );

        context.fill();

        context.setSourceRGBA(
            1.0,
            1.0,
            1.0,
            1.0
        );

        context.moveTo(
            textX,
            textY
        );

        context.showText(
            countdown
        );

        /*
         * Temporary tomato marker. We will improve its actual tomato shape
         * after compositor layering is proven.
         */
        const tomatoX = centreX;
        const tomatoY = centreY - radius;

        context.setSourceRGBA(
            0xE5 / 255.0,
            0x39 / 255.0,
            0x35 / 255.0,
            1.0
        );

        context.arc(
            tomatoX,
            tomatoY,
            iconRadius,
            0.0,
            Math.PI * 2.0
        );

        context.fill();

        context.setSourceRGBA(
            0x43 / 255.0,
            0xA0 / 255.0,
            0x47 / 255.0,
            1.0
        );

        context.moveTo(
            tomatoX,
            tomatoY - iconRadius - 3.0
        );

        context.lineTo(
            tomatoX + iconRadius * 0.35,
            tomatoY - iconRadius * 0.35
        );

        context.lineTo(
            tomatoX + iconRadius * 0.75,
            tomatoY - iconRadius * 0.55
        );

        context.lineTo(
            tomatoX + iconRadius * 0.30,
            tomatoY
        );

        context.lineTo(
            tomatoX,
            tomatoY - iconRadius * 0.25
        );

        context.lineTo(
            tomatoX - iconRadius * 0.30,
            tomatoY
        );

        context.lineTo(
            tomatoX - iconRadius * 0.75,
            tomatoY - iconRadius * 0.55
        );

        context.lineTo(
            tomatoX - iconRadius * 0.35,
            tomatoY - iconRadius * 0.35
        );

        context.closePath();
        context.fill();
    }

    _setPomodoroState(
        enabled,
        phase,
        progress,
        remainingSeconds,
        focusColour,
        breakColour,
        timerTextSize,
        ringThickness,
        iconSize
    ) {
        this._pomodoroEnabled = Boolean(enabled);
        this._pomodoroPhase = String(
            phase || 'focus'
        );

        const requestedProgress = Number(progress);
        const requestedRemaining = Number(remainingSeconds);
        const requestedTextSize = Number(timerTextSize);
        const requestedThickness = Number(ringThickness);
        const requestedIconSize = Number(iconSize);

        this._pomodoroFocusColour = String(
            focusColour || '#E53935'
        );

        this._pomodoroBreakColour = String(
            breakColour || '#43A047'
        );

        if (
            Number.isFinite(requestedTextSize) &&
            requestedTextSize >= 8
        ) {
            this._pomodoroTimerTextSize =
                requestedTextSize;
        }

        if (Number.isFinite(requestedRemaining)) {
            this._pomodoroRemainingSeconds = Math.max(
                0.0,
                requestedRemaining
            );
        }

        if (Number.isFinite(requestedProgress)) {
            this._pomodoroProgress = Math.max(
                0.0,
                Math.min(1.0, requestedProgress)
            );
        }

        if (
            Number.isFinite(requestedThickness) &&
            requestedThickness > 0.0
        ) {
            this._pomodoroRingThickness = requestedThickness;
        }

        if (
            Number.isFinite(requestedIconSize) &&
            requestedIconSize > 0.0
        ) {
            this._pomodoroIconSize = requestedIconSize;
        }

        this._resizeRingActor();

        if (this._ringActor)
            this._ringActor.queue_repaint();
    }

    _paintRing(actor) {
        const context = actor.get_context();
        const width = actor.width;
        const height = actor.height;

        const centreX = width / 2.0;
        const centreY = height / 2.0;

        /*
         * Complications paint first. The accessibility reticule then paints
         * over them and remains the visually dominant pointer marker.
         */
        this._paintPomodoro(
            context,
            centreX,
            centreY
        );

        /*
         * Match Mousehair's PyQt renderer exactly: both strokes are centred on
         * the configured gap radius. Painting the wide outer stroke first and
         * the narrow inner stroke second leaves black visible on both sides of
         * the white centre.
         */
        const outerThickness = Math.max(
            0.0,
            Number(this._ringOuterThickness)
        );

        const innerThickness = Math.max(
            0.0,
            Number(this._ringInnerThickness)
        );

        const centrelineRadius = Math.max(
            0.5,
            Number(this._ringRadius)
        );

        const outer = this._parseHexColour(
            this._ringOuterColour,
            '#000000'
        );

        const inner = this._parseHexColour(
            this._ringInnerColour,
            '#FFFFFF'
        );

        if (outerThickness > 0.0) {
            context.setSourceRGBA(
                outer.red,
                outer.green,
                outer.blue,
                1.0
            );
            context.setLineWidth(outerThickness);
            context.arc(
                centreX,
                centreY,
                centrelineRadius,
                0.0,
                Math.PI * 2.0
            );
            context.stroke();
        }

        if (innerThickness > 0.0) {
            context.setSourceRGBA(
                inner.red,
                inner.green,
                inner.blue,
                1.0
            );
            context.setLineWidth(innerThickness);
            context.arc(
                centreX,
                centreY,
                centrelineRadius,
                0.0,
                Math.PI * 2.0
            );
            context.stroke();
        }

        context.$dispose();
    }

    _setRingStyle(
        radius,
        outerThickness,
        innerThickness,
        outerColour,
        innerColour
    ) {
        const requestedRadius = Number(radius);
        const requestedOuter = Number(outerThickness);
        const requestedInner = Number(innerThickness);

        const requestedOuterColour =
            String(outerColour || '#000000');

        const requestedInnerColour =
            String(innerColour || '#FFFFFF');

        let styleChanged = false;

        if (
            Number.isFinite(requestedRadius) &&
            requestedRadius > 0.0 &&
            requestedRadius !== this._ringRadius
        ) {
            this._ringRadius = requestedRadius;
            styleChanged = true;
        }

        if (
            Number.isFinite(requestedOuter) &&
            requestedOuter >= 0.0 &&
            requestedOuter !== this._ringOuterThickness
        ) {
            this._ringOuterThickness = requestedOuter;
            styleChanged = true;
        }

        if (
            Number.isFinite(requestedInner) &&
            requestedInner >= 0.0 &&
            requestedInner !== this._ringInnerThickness
        ) {
            this._ringInnerThickness = requestedInner;
            styleChanged = true;
        }

        if (
            requestedOuterColour !==
            this._ringOuterColour
        ) {
            this._ringOuterColour =
                requestedOuterColour;

            styleChanged = true;
        }

        if (
            requestedInnerColour !==
            this._ringInnerColour
        ) {
            this._ringInnerColour =
                requestedInnerColour;

            styleChanged = true;
        }

        if (!styleChanged)
            return;

        this._resizeRingActor();
        this._updateLens();
        this._refreshVisibility();
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

    _setRingParentForCinnamonMagnifier(cinnamonActive) {
        /*
         * Mousehair's ordinary PyQt overlay belongs to Cinnamon's desktop
         * scene and is therefore transformed by Cinnamon's magnifier.
         *
         * The compositor-native ring normally lives directly on global.stage
         * so it is excluded from Mousehair's own Main.uiGroup clone source.
         * During Cinnamon magnification, however, a stage-level ring and the
         * magnified crosshair occupy different coordinate spaces and drift
         * apart.
         *
         * Temporarily move the ring into Main.uiGroup while Cinnamon zoom is
         * active. Move it back to global.stage before Mousehair's own lens is
         * shown again, avoiding recursive capture by the strip clones.
         */
        if (!this._ringActor)
            return;

        const desiredParent = cinnamonActive
            ? Main.uiGroup
            : global.stage;

        if (this._ringActor.get_parent() !== desiredParent) {
            global.reparentActor(
                this._ringActor,
                desiredParent
            );
        }
    }

    _refreshVisibility() {
        this._cinnamonMagnifierActive =
            this._isCinnamonMagnifierActive();

        if (!this._lensActor)
            return;

        /*
         * Cinnamon magnification always wins over Mousehair's compositor lens.
         *
         * Keep the compositor-native ring visible, however. It remains the
         * pointer reticule even while Cinnamon provides full-screen
         * magnification.
         */
        if (this._cinnamonMagnifierActive) {
            /*
             * Hide Mousehair's own lens immediately. The ring remains useful,
             * but must join Main.uiGroup so Cinnamon transforms it together
             * with the crosshair rather than leaving it in stage coordinates.
             */
            this._lensActor.hide();
            this._setRingParentForCinnamonMagnifier(true);

            if (
                this._ringActor &&
                this._requestedOpacity > 0.0
            ) {
                this._ringActor.opacity = Math.round(
                    this._requestedOpacity * 255
                );
                this._ringActor.show();
                this._ringActor.raise_top();
            } else if (this._ringActor) {
                this._ringActor.hide();
            }

            return;
        }

        /*
         * Cinnamon zoom has ended. Return the ring to the stage before
         * restoring Mousehair's strip-built lens, otherwise Main.uiGroup's
         * clones would capture the ring recursively.
         */
        this._setRingParentForCinnamonMagnifier(false);
        this._ensureSharedGroupsInUiGroup();

        if (this._requestedOpacity <= 0.0) {
            this._lensActor.hide();
            if (this._ringActor)
                this._ringActor.hide();
            return;
        }

        this._lensActor.opacity = Math.round(
            this._requestedOpacity * 255
        );

        if (this._ringActor) {
            this._ringActor.opacity = Math.round(
                this._requestedOpacity * 255
            );
        }

        this._lensActor.show();
        if (this._ringActor)
            this._ringActor.show();

        this._lensActor.raise_top();

        /*
         * SetOpacity calls _refreshVisibility() throughout every fade. Always
         * restore the ring above the lens here, not only in _updateLens().
         */
        if (this._ringActor)
            this._ringActor.raise_top();
    }

    _setOpacity(opacity) {
        const requestedOpacity = Math.max(
            0.0,
            Math.min(1.0, Number(opacity))
        );

        if (
            requestedOpacity ===
            this._requestedOpacity
        ) {
            return;
        }

        this._requestedOpacity =
            requestedOpacity;

        this._refreshVisibility();
    }

    _synchroniseState(
        lensRadius,
        magnification,
        ringRadius,
        outerThickness,
        innerThickness,
        outerColour,
        innerColour,
        opacity
    ) {
        /*
         * Mousehair is the authority for compositor state. Receiving this
         * complete snapshot both refreshes the watchdog heartbeat and restores
         * every piece of state needed after a Cinnamon restart.
         */
        this._heartbeat();

        this._setGeometry(
            lensRadius,
            magnification
        );

        this._setRingStyle(
            ringRadius,
            outerThickness,
            innerThickness,
            outerColour,
            innerColour
        );

        this._setOpacity(
            opacity
        );
    }

    _heartbeat() {
        /*
         * Any successful heartbeat proves that the Python application is
         * alive. Visibility is still controlled independently by SetOpacity.
         */
        this._lastHeartbeatUs = GLib.get_monotonic_time();
    }

    _setGeometry(gap, magnification) {
        /*
         * Apply geometry only when it has genuinely changed.
         *
         * SynchroniseState() is deliberately sent periodically so Mousehair can
         * recover after Cinnamon restarts. Rebuilding every strip for an
         * identical heartbeat snapshot would destroy correctly positioned
         * clones and leave their replacements unpositioned until the mouse next
         * moves.
         */
        const requestedGap = Number(gap);
        const requestedMagnification = Number(magnification);

        let geometryChanged = false;

        if (
            Number.isFinite(requestedGap) &&
            requestedGap > 0
        ) {
            const newGap = requestedGap;
            const newLensSize = Math.max(
                2,
                Math.round(newGap * 2)
            );

            if (
                newGap !== this._gap ||
                newLensSize !== this._lensSize
            ) {
                this._gap = newGap;
                this._lensSize = newLensSize;
                geometryChanged = true;
            }
        }

        if (
            Number.isFinite(requestedMagnification) &&
            requestedMagnification >= 1.0
        ) {
            if (
                requestedMagnification !==
                this._magnification
            ) {
                this._magnification =
                    requestedMagnification;

                geometryChanged = true;
            }
        }

        if (
            geometryChanged &&
            this._lensActor
        ) {
            this._lensActor.set_size(
                this._lensSize,
                this._lensSize
            );

            /*
             * Both diameter and magnification affect the strip arrangement.
             */
            this._rebuildMagnifiedStrips();

            /*
             * Force _updateLens() to position every newly created clone even
             * when the physical pointer has remained stationary.
             */
            this._lastLensPointerX = null;
            this._lastLensPointerY = null;
        }

        this._updateLens();
        this._refreshVisibility();
    }

    _updateLens() {
        if (!this._lensActor)
            return GLib.SOURCE_REMOVE;

        const cinnamonActive = this._isCinnamonMagnifierActive();

        if (cinnamonActive !== this._cinnamonMagnifierActive)
            this._refreshVisibility();

        const [pointerX, pointerY] = global.get_pointer();

        /*
         * The ring remains useful while Cinnamon's own magnifier is active.
         * Position it independently from the Mousehair lens and strips.
         */
        if (this._ringActor) {
            const ringWidth = this._ringActor.width;
            const ringHeight = this._ringActor.height;
            const ringParent = this._ringActor.get_parent();

            /*
             * global.get_pointer() returns stage coordinates.
             *
             * While Cinnamon magnification is active, the ring belongs to
             * Main.uiGroup, which is transformed by the magnifier. Convert the
             * pointer into that parent's local coordinate space before placing
             * the ring. Otherwise the transformed actor appears to drift or
             * chase the pointer.
             */
            let localPointerX = pointerX;
            let localPointerY = pointerY;

            if (
                ringParent &&
                ringParent !== global.stage
            ) {
                const transformed =
                    ringParent.transform_stage_point(pointerX, pointerY);

                if (
                    transformed &&
                    transformed.length >= 3 &&
                    transformed[0]
                ) {
                    localPointerX = transformed[1];
                    localPointerY = transformed[2];
                }
            }

            this._ringActor.set_position(
                Math.round(localPointerX - ringWidth / 2.0),
                Math.round(localPointerY - ringHeight / 2.0)
            );

            this._ringActor.raise_top();
        }

        /*
         * Suppress Mousehair's compositor lens immediately when Cinnamon's
         * magnifier is active. Ring positioning above has already occurred.
         */
        if (this._cinnamonMagnifierActive)
            return GLib.SOURCE_CONTINUE;

        /*
         * Updating every strip is the expensive part of the compositor lens.
         * The timer must continue running for visibility and heartbeat checks,
         * but the lens geometry only needs updating when the pointer moves.
         */
        const pointerMoved =
            pointerX !== this._lastLensPointerX ||
            pointerY !== this._lastLensPointerY;

        if (pointerMoved) {
            this._lastLensPointerX = pointerX;
            this._lastLensPointerY = pointerY;

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

            /*
             * The desktop point under the pointer belongs at the centre of the
             * magnified lens.
             */
            const magnifiedCloneX =
                this._lensSize / 2 - pointerX * this._magnification;
            const magnifiedCloneY =
                this._lensSize / 2 - pointerY * this._magnification;

            /*
             * Each strip has its own local origin. Subtract that origin so all
             * strip clones sample one continuous magnified desktop image.
             */
            for (const entry of this._magnifiedStrips) {
                entry.clone.set_position(
                    Math.round(magnifiedCloneX - entry.left),
                    Math.round(magnifiedCloneY - entry.top)
                );
            }
        }

        /*
         * Raising the ring is cheap and preserves the required stacking order
         * even when another Cinnamon actor appears while the pointer is still.
         */
        if (this._ringActor)
            this._ringActor.raise_top();

        /*
         * The magnified strips belong above ordinary desktop content, but the
         * compositor-native ring must remain above the strips.
         */
        this._lensActor.raise_top();

        if (this._ringActor)
            this._ringActor.raise_top();

        /*
         * Hide stale compositor content when Mousehair is no longer running.
         * GLib.get_monotonic_time() is measured in microseconds.
         */
        const nowUs = GLib.get_monotonic_time();
        const heartbeatAgeUs = nowUs - this._lastHeartbeatUs;

        if (
            this._lastHeartbeatUs <= 0 ||
            heartbeatAgeUs > 2500000
        ) {
            this._requestedOpacity = 0.0;
            this._refreshVisibility();
        }

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

                SetRingStyle: (
                    radius,
                    outerThickness,
                    innerThickness,
                    outerColour,
                    innerColour
                ) => this._setRingStyle(
                    radius,
                    outerThickness,
                    innerThickness,
                    outerColour,
                    innerColour
                ),

                Heartbeat: () => this._heartbeat(),

                SetPomodoroState: (
                    enabled,
                    phase,
                    progress,
                    remainingSeconds,
                    focusColour,
                    breakColour,
                    timerTextSize,
                    ringThickness,
                    iconSize
                ) => this._setPomodoroState(
                    enabled,
                    phase,
                    progress,
                    remainingSeconds,
                    focusColour,
                    breakColour,
                    timerTextSize,
                    ringThickness,
                    iconSize
                ),

                SynchroniseState: (
                    lensRadius,
                    magnification,
                    ringRadius,
                    outerThickness,
                    innerThickness,
                    outerColour,
                    innerColour,
                    opacity
                ) => this._synchroniseState(
                    lensRadius,
                    magnification,
                    ringRadius,
                    outerThickness,
                    innerThickness,
                    outerColour,
                    innerColour,
                    opacity
                ),

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
