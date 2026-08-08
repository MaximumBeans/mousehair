# Mousehair Roadmap

This document records planned and experimental directions for Mousehair.

## Current foundation

-   High-visibility configurable crosshair overlay.
-   Two-colour bordered line rendering.
-   Ring reticule.
-   Compositor-native circular Cinnamon magnifier.
-   Integration with Cinnamon's full-screen magnifier.
-   Mousehair/Cinnamon lifecycle synchronisation.
-   Effects Engine with modular visual effects.
-   Built-in effects:
    -   Static
    -   Sliding inward
    -   Direction arrows
    -   Pulse
-   `crosshair_effect` is the canonical persisted effect setting.

## Pointer Gestures

Gestures should normally require a configurable modifier key.

### Initial ideas

-   Ctrl + small clockwise circle: Zoom in.
-   Ctrl + small anticlockwise circle: Zoom out.

Recognition safeguards:

-   Minimum angular travel.
-   Minimum sample count.
-   Maximum gesture radius.
-   Direction consistency.
-   Cooldown after recognition.

### Reticule size compensation

Avoid linear growth. Use stepped or curved scaling.

Example:

    2.0x -> 100 px
    2.5x -> 110 px
    3.0x -> 125 px
    4.0x -> 145 px
    5.0x -> 160 px

User options:

-   Enable/disable compensation.
-   Minimum radius.
-   Maximum radius.
-   Base radius.
-   Stepped or curved growth.
-   Optional smooth animation.

Suggested gesture subsystem:

    mousehair_app/
        gestures/
            __init__.py
            recognizer.py
            circle.py
            actions.py

## Effects Engine

Future work:

-   Effect-specific settings.
-   Plugin discovery.
-   Persistent instances.
-   Rich metadata.

Candidate effects:

-   Radar sweep.
-   Vortex.
-   Scanner.
-   Circuit lines.
-   Energy flow.
-   Pulse variants.
-   Sniper reticules.

## Ring Complications

Possible HUD elements:

-   Pomodoro timer.
-   CPU / Memory.
-   Battery.
-   Downloads.
-   Media playback.
-   Email/messages.

## Architecture

    Mousehair
        |
        +-- Settings / state
        +-- Gesture subsystem
        +-- Effects Engine
        +-- Ring / complication layers
        +-- Magnifier bridge
                |
                +-- Cinnamon compositor extension
