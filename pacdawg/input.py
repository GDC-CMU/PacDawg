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
EXIT_KEYS = frozenset({"escape"})
# "Cancel/back" -- Esc and Backspace on the keyboard, button B (0) on the
# cabinet. Distinct from EXIT_KEYS/EXIT_BUTTONS: on most screens Esc
# means "exit", but on HOW TO PLAY it means "go back to the menu"
# instead (see Game.maybe_exit / Game._update_how_to_play), so the two
# concepts are resolved separately here rather than conflated.
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


def wants_back(raw: RawInput) -> bool:
    """"Cancel/back" intent: Esc, Backspace, or button B (0). Used by
    screens (like HOW TO PLAY) that need a way to return without exiting
    the game outright -- see wants_p1_exit()/wants_exit() for the exit
    contract, which is intentionally a separate concept."""
    if raw.pressed_keys & BACK_KEYS:
        return True
    return bool(raw.pressed_buttons & set(config.BACK_BUTTONS))


def wants_p1_exit(raw: RawInput) -> bool:
    """True only for the literal P1 button (5) -- the one exit path that
    must work identically from *every* state, including screens (like
    HOW TO PLAY) where Esc has been repurposed to mean "back" instead of
    "exit". Unlike wants_exit(), this deliberately ignores Esc."""
    return bool(raw.pressed_buttons & set(config.EXIT_BUTTONS))


def wants_escape_key(raw: RawInput) -> bool:
    """True iff the literal Esc key is physically held, independent of
    whatever it currently *means* (exit, on most screens; back, on HOW
    TO PLAY). Game.maybe_exit() tracks this separately from P1 so a
    single held Esc can't chain two meanings across a state transition
    -- e.g. pressing Esc to leave HOW TO PLAY must not also be read as a
    fresh Esc-means-exit press the instant the menu appears."""
    return bool(raw.pressed_keys & EXIT_KEYS)


def wants_exit(raw: RawInput) -> bool:
    """True the instant P1 (button 5) or Esc is pressed, from any state
    where Esc still means "exit" (i.e. everywhere except HOW TO PLAY --
    see wants_p1_exit() for the subset used there)."""
    if raw.pressed_keys & EXIT_KEYS:
        return True
    return bool(raw.pressed_buttons & set(config.EXIT_BUTTONS))
