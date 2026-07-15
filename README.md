# Mousehair

Mousehair is a configurable full-screen mouse crosshair overlay for Linux/X11.

It provides a transparent overlay that draws configurable guide lines centred on the mouse pointer. The overlay supports custom colours, line thicknesses, centre gap, opacity, fading, and animated inward-moving line segments.

## Features

* Transparent always-on-top overlay
* Dual-colour crosshair
* Adjustable gap around the mouse pointer
* Configurable opacity
* Adjustable line thickness
* Optional fade after mouse inactivity
* Optional inward crawling animation
* Global hotkey
* System tray icon with settings
* JSON configuration

## Requirements

* Linux
* X11
* Python 3
* PyQt5
* python-xlib

On Debian, Ubuntu or Linux Mint:

```bash
sudo apt install python3-pyqt5 python3-xlib
```

## Running

```bash
python3 mousehair.py
```

Mousehair stores its configuration in:

```
~/.config/mousehair/config.json
```

## Roadmap

Planned future effects include:

* Plasma energy flow
* Direction arrows
* Vortex mode
* Centre reticule
* Zoom lens
* Additional animated effects

