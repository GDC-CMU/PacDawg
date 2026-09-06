"""Input intent resolution: joystick axes + keyboard -> game actions.

This module contains no pygame imports. It resolves plain floats, key
name strings, and button index sets into game-level intent (a
direction, confirm, exit), so it is fully unit-testable without a
display or real hardware. The actual pygame event/joystick polling lives
in :mod:`pacdawg.game`, which builds a :class:`RawInput` each frame and
hands it to the functions here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Optional, Tuple

from . import config
from .entities import Direction

KEY_DIRECTIONS = {
    "up": Direction.UP,
    "w": Direction.UP,
    "down": Direction.DOWN,
    "s": Direction.DOWN,
    "left": Direction.LEFT,
    "a": Direction.LEFT,
    "right": Direction.RIGHT,
    "d": Direction.RIGHT,
}

CONFIRM_KEYS = frozenset({"return", "enter", "space"})
# "Go back one level" -- Esc and Backspace on the keyboard, or button P1
# (5)/B (0) on the cabinet. All four are equivalent aliases of a single
# action (see Game.maybe_go_back()): active runs pause/resume, the main
# menu exits to the gallery, and help/results/demo return to the menu. There is no
# separate "exit" concept any more -- P1 no longer means "quit
# immediately from anywhere", it means "go back", exactly like Esc.
BACK_KEYS = frozenset({"escape", "backspace"})


@dataclass(frozen=True)
class RawInput:
    """One frame's worth of raw hardware state, already read out of pygame.

    ``axes`` holds one ``(x, y)`` pair per connected joystick -- the
    cabinet may have either (or both) of its two identical sticks
    plugged in, and either should be able to play.
    """

    axes: Tuple[Tuple[float, float], ...] = field(default_factory=tuple)
    pressed_keys: FrozenSet[str] = frozenset()
    pressed_buttons: FrozenSet[int] = frozenset()


def axis_direction(axis_x: float, axis_y: float, deadzone: float = None) -> Optional[Direction]:
    """Resolve one analog stick reading into a single cardinal direction.

    The cabinet's stick reports a *digital* axis (values near -1/+1), so
    a simple deadzone comparison is enough. On a tie, vertical wins,
    since accidental diagonal pushes are more common than intentional
    ones in a 4-direction maze game.
    """
    dz = config.JOYSTICK_DEADZONE if deadzone is None else deadzone
    if abs(axis_y) >= dz and abs(axis_y) >= abs(axis_x):
        return Direction.DOWN if axis_y > 0 else Direction.UP
    if abs(axis_x) >= dz:
        return Direction.RIGHT if axis_x > 0 else Direction.LEFT
    return None


def keyboard_direction(pressed_keys) -> Optional[Direction]:
    for key in pressed_keys:
        direction = KEY_DIRECTIONS.get(key)
        if direction is not None:
            return direction
    return None


def resolve_direction(raw: RawInput) -> Optional[Direction]:
    """Either connected stick, or the keyboard, may steer Scotty."""
    for axis_x, axis_y in raw.axes:
        direction = axis_direction(axis_x, axis_y)
        if direction is not None:
            return direction
    return keyboard_direction(raw.pressed_keys)


def wants_confirm(raw: RawInput) -> bool:
    if raw.pressed_keys & CONFIRM_KEYS:
        return True
    return bool(raw.pressed_buttons & set(config.CONFIRM_BUTTONS))


def wants_go_back(raw: RawInput) -> bool:
    """The single "go back one level" intent: Esc, Backspace, button P1
    (5), or button B (0). All four are exactly equivalent everywhere in
    the game -- see Game.maybe_go_back() for pause/resume during a run,
    exit at the main menu, and back to the menu on help/results/demo."""
    if raw.pressed_keys & BACK_KEYS:
        return True
    return bool(raw.pressed_buttons & (set(config.EXIT_BUTTONS) | set(config.BACK_BUTTONS)))
