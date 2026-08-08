# Mousehair Cinnamon Magnifier Proof, version 4.5

Version 4.5 keeps every proven part of version 4.4:

- lens size from `~/.config/mousehair/config.json`;
- magnification from the same configuration;
- exact pointer centring;
- D-Bus show, hide, and opacity controls;
- automatic hiding while Cinnamon's own magnifier is active.

It makes one experimental change: a circular `Clutter.ShaderEffect` is applied
to the complete lens actor.

Unlike version 4.1, this shader does not try to set its texture sampler from
JavaScript. Clutter binds the actor's off-screen texture to texture unit zero,
which is also the sampler's default value.

## Install

```bash
./install.sh
```

Restart Cinnamon with `Alt+F2`, type `r`, and press Enter. Then disable and
re-enable **Mousehair Magnifier Proof**.

## Expected result

- The lens remains aligned with the existing Mousehair ring.
- The four square corners disappear.
- The image remains visible inside a genuine circular aperture.
- The pale-purple diagnostic border is clipped to the same circle.
- D-Bus opacity controls continue to work.

Test:

```bash
./mousehair-lensctl state
./mousehair-lensctl opacity 0.5
./mousehair-lensctl hide
./mousehair-lensctl show
```
