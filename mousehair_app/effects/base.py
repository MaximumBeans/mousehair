"""Base interfaces for Mousehair visual effects."""


class CrosshairEffect:
    """Base class for a crosshair rendering effect.

    Effects deliberately receive their host overlay rather than owning global
    application state themselves. This keeps effects concerned only with
    drawing while Mousehair continues to own settings, timers, fading,
    magnification, and Cinnamon integration.
    """

    name = "base"

    def __init__(self, host):
        self.host = host

    def render(
        self,
        painter,
        mx,
        my,
        outer_pen,
        inner_pen,
    ):
        """Render this effect.

        Subclasses must implement this method.
        """
        raise NotImplementedError
