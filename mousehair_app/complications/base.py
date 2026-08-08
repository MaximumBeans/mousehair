"""Base interfaces for Mousehair ring complications."""

from dataclasses import dataclass

from .placement import ComplicationPlacement


@dataclass(frozen=True)
class ComplicationSetting:
    """Describe one configurable setting belonging to a complication."""

    key: str
    label: str
    kind: str
    default: object

    minimum: float | int | None = None
    maximum: float | int | None = None
    step: float | int | None = None

    suffix: str = ""
    decimals: int = 0

    choices: tuple = ()


class Complication:
    """Base class for a pointer-centred Mousehair complication."""

    name = "base"
    display_name = "Base complication"

    settings = ()

    default_placement = ComplicationPlacement()

    def __init__(
        self,
        host,
        placement=None,
    ):
        self.host = host

        self.placement = (
            placement
            if placement is not None
            else self.default_placement
        )

    def update(self, now):
        """Advance internal complication state if required."""
        del now

    def draw(
        self,
        painter,
        geometry,
        placement,
    ):
        """Draw the complication.

        Concrete complication classes implement this method.
        """
        raise NotImplementedError
