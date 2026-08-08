"""Runtime manager for Mousehair complications."""

from .pomodoro import PomodoroComplication


class ComplicationManager:
    """Own persistent complication instances for one Mousehair overlay."""

    def __init__(self, host):
        self.host = host

        self._instances = {
            "pomodoro": PomodoroComplication(
                host
            ),
        }

    def get(self, name):
        """Return a complication by stable name."""
        return self._instances.get(
            str(name)
        )

    @property
    def pomodoro(self):
        """Return the built-in Pomodoro complication."""
        return self._instances["pomodoro"]

    def update(self):
        """Advance all enabled complication state."""
        changed = False

        for complication in self._instances.values():
            if complication.update():
                changed = True

        return changed

    def enabled(self):
        """Yield complications currently enabled by Mousehair settings."""
        if bool(
            getattr(
                self.host,
                "pomodoro_enabled",
                False,
            )
        ):
            yield self.pomodoro
