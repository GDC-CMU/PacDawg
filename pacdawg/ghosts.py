"""Ghost personalities and the scatter/chase/frightened state machine.

Four ghosts, four genuinely different targeting algorithms -- not one
rule recolored four times. Each is named after a CMU campus landmark:

* **Gates** -- a direct chaser. Always targets Scotty's exact tile.
* **Hunt** -- an ambusher. Targets several tiles *ahead* of wherever
  Scotty is facing, trying to cut him off before he arrives.
* **Wean** -- a flanker. Its target is derived from Gates' position
  reflected through a point ahead of Scotty, so it swings in from an
  unpredictable angle that depends on where Gates currently is.
* **Doherty** -- shy. It chases aggressively while far from Scotty, but
  once it gets close it flees back toward its home corner, so it never
  quite commits to the kill by itself.

This module does not import pygame; ghosts are pure tile-grid logic so
they can be driven and asserted against headlessly.
"""
from __future__ import annotations

import random
from enum import Enum, auto
from typing import Callable, Dict, List, Tuple

from . import config
from .entities import Direction, MovingActor
from .maze import GHOST_MARKERS, Maze

Coord = Tuple[int, int]


class GhostMode(Enum):
    HOUSE = auto()       # bobbing inside the ghost house, waiting to be released
    LEAVING = auto()     # walking out through the gate
    SCATTER = auto()      # heading for its home corner
    CHASE = auto()        # hunting Scotty per its personality
    FRIGHTENED = auto()   # fleeing at reduced speed after a power pellet
    EATEN = auto()         # eyes-only, returning to the house


# Corners each ghost retreats to during scatter phases (and Doherty's shy
# retreat). Placed near the four maze corners, inset by one tile so they
# are always open floor rather than a border wall.
def _corners(maze: Maze) -> Dict[str, Coord]:
    return {
        "gates": (maze.cols - 2, 1),
        "hunt": (1, 1),
        "wean": (maze.cols - 2, maze.rows - 2),
        "doherty": (1, maze.rows - 2),
    }


def _gate_tile(maze: Maze) -> Coord:
    # Layouts are authored with exactly one gate tile; picking the
    # lexicographically smallest keeps this deterministic if that ever
    # changes.
    return min(maze.gates)


def _house_exit_tile(maze: Maze) -> Coord:
    gate_col, gate_row = _gate_tile(maze)
    return (gate_col, gate_row - 1)


def target_gates(ghost: "Ghost", player, ghosts: Dict[str, "Ghost"], maze: Maze) -> Coord:
    """Direct chaser: always aim at Scotty's current tile."""
    return player.tile


def _facing_offset_with_overflow(facing: Direction, magnitude: int) -> Coord:
    """Reproduce the original ROM's documented "up" targeting bug.

    The original computes an offset by doubling a 16-bit (dx, dy) vector
    with a single ``ADD HL,HL`` Z80 instruction (doubled again for Pinky's
    4-tile offset). That instruction doubles the *whole* 16-bit value,
    so when facing up the vector (0, -1) is stored as the 16-bit pattern
    for (1, -1) and a carry leaks from the low byte into the high byte:
    "4 tiles up" becomes "4 tiles up AND 4 tiles left". Don Hodges'
    ROM-level writeup confirms this is a genuine bug, not a design choice
    -- but it is load-bearing for authentic ghost behavior (it is why
    Pinky/Inky-style ghosts can be out-maneuvered by facing up), so we
    deliberately reproduce it rather than "fixing" it.
    """
    if facing is Direction.UP:
        return (-magnitude, -magnitude)
    fx, fy = facing.vector
    return (fx * magnitude, fy * magnitude)


def target_hunt(ghost: "Ghost", player, ghosts: Dict[str, "Ghost"], maze: Maze) -> Coord:
    """Ambusher: aim four tiles ahead of the way Scotty is facing.

    Reproduces the documented "up" overflow bug: facing up targets four
    tiles up *and* four tiles left, not simply four tiles up.
    """
    px, py = player.tile
    ox, oy = _facing_offset_with_overflow(player.facing, 4)
    return (px + ox, py + oy)


def target_wean(ghost: "Ghost", player, ghosts: Dict[str, "Ghost"], maze: Maze) -> Coord:
    """Flanker: reflect Gates' position through a point ahead of Scotty.

    The "pivot" point two tiles ahead of Scotty is subject to the same
    documented "up" overflow bug as Hunt's target (see
    ``_facing_offset_with_overflow``).
    """
    px, py = player.tile
    ox, oy = _facing_offset_with_overflow(player.facing, 2)
    pivot_x, pivot_y = px + ox, py + oy
    gates = ghosts.get("gates")
    gx, gy = gates.tile if gates is not None else (px, py)
    return (2 * pivot_x - gx, 2 * pivot_y - gy)


def target_doherty(ghost: "Ghost", player, ghosts: Dict[str, "Ghost"], maze: Maze) -> Coord:
    """Shy: chase from afar, but flee home once Scotty gets close.

    The 8-tile-or-more threshold is inclusive (``>= 64`` squared tiles),
    matching the Dossier's "eight tiles or more" wording -- one of the
    two reference clones examined flips behavior at exactly 8 tiles by
    using a strict ``>``, which the documentation explicitly does not.
    """
    gx, gy = ghost.tile
    px, py = player.tile
    distance_sq = (gx - px) ** 2 + (gy - py) ** 2
    if distance_sq >= 64:  # eight tiles or more: come on in
        return (px, py)
    return ghost.corner  # too close: lose your nerve and retreat


TARGET_FUNCTIONS: Dict[str, Callable] = {
    "gates": target_gates,
    "hunt": target_hunt,
    "wean": target_wean,
    "doherty": target_doherty,
}

# Turn order matches entities.TURN_PRIORITY for tie-breaking.
from .entities import TURN_PRIORITY  # noqa: E402  (after TARGET_FUNCTIONS for readability)


class Ghost(MovingActor):
    def __init__(
        self,
        name: str,
        start: Coord,
        corner: Coord,
        normal_speed: float,
        frightened_speed: float = None,
        tunnel_speed: float = None,
        eyes_speed: float = None,
        house_pace_speed: float = None,
        elroy1_speed: float = None,
        elroy2_speed: float = None,
    ):
        super().__init__(start[0], start[1], normal_speed)
        self.name = name
        self.corner = corner
        self.mode = GhostMode.HOUSE
        self.base_speed = normal_speed
        self.frightened_speed = frightened_speed if frightened_speed is not None else normal_speed
        self.tunnel_speed = tunnel_speed if tunnel_speed is not None else normal_speed
        self.eyes_speed = eyes_speed if eyes_speed is not None else normal_speed
        self.house_pace_speed = house_pace_speed if house_pace_speed is not None else normal_speed * 0.5
        # Cruise Elroy speeds only ever apply to Gates (Blinky); harmless
        # defaults for the other three, which never set elroy_stage > 0.
        self._elroy1_speed = elroy1_speed if elroy1_speed is not None else normal_speed
        self._elroy2_speed = elroy2_speed if elroy2_speed is not None else normal_speed
        self.frightened_seconds_left = 0.0
        self.frightened_total = 0.0
        self.frightened_flash_count = 0
        self.house_bob_direction = Direction.UP
        self.released = False
        self.elroy_stage = 0  # 0 = normal, 1 = Elroy 1, 2 = Elroy 2 (Gates only)
        self._pending_reversal = False
        self._house_anchor_row = float(start[1])

    def teleport(self, col: int, row: int, direction: Direction = Direction.NONE) -> None:
        super().teleport(col, row, direction)
        self._house_anchor_row = float(row)

    # -- house behaviour ---------------------------------------------------
    def release(self) -> None:
        if not self.released:
            self.released = True
            self.mode = GhostMode.LEAVING
            # Undo any in-progress bob offset and snap onto a clean integer
            # tile before moving. _bob_in_house() only ever touches self.y
            # directly (it never runs through step()), so without this the
            # tracked segment target can be left on the wrong side of the
            # ghost's actual (bobbed) position -- which makes "distance to
            # target" *increase* every frame instead of decrease, so it
            # never arrives, never re-checks walls, and just sails through
            # them in a straight line forever.
            self.x = round(self.x)
            self.y = self._house_anchor_row
            self._target_x, self._target_y = self.x, self.y
            self.direction = Direction.UP
            self.queue_direction(Direction.NONE)

    def _bob_in_house(self, dt: float) -> None:
        # Small, deterministic vertical bob so idle ghosts still read as
        # alive rather than frozen sprites. The anchor row is fixed once
        # (at spawn/teleport), not re-derived from round(y) each frame --
        # re-deriving it is unreliable because the oscillation deliberately
        # spans the rounding half-way point, so round() flips to a
        # different integer right after the first clamp and the anchor
        # would otherwise silently drift, one row per bounce, forever.
        span = 0.6
        speed = self.house_pace_speed
        dy = speed * dt * (1 if self.house_bob_direction is Direction.DOWN else -1)
        self.y += dy
        base_row = self._house_anchor_row
        if self.y > base_row + span:
            self.y = base_row + span
            self.house_bob_direction = Direction.UP
        elif self.y < base_row - span:
            self.y = base_row - span
            self.house_bob_direction = Direction.DOWN

    # -- frightened / eaten --------------------------------------------------
    def frighten(self, seconds: float, flash_count: int = 0) -> None:
        if self.mode not in (GhostMode.SCATTER, GhostMode.CHASE):
            return  # only actively hunting ghosts can be spooked
        self.mode = GhostMode.FRIGHTENED
        self.frightened_seconds_left = seconds
        self.frightened_total = seconds
        self.frightened_flash_count = flash_count
        # Forced reversal on entering frightened -- but per the documented
        # rule, it "takes effect when the ghost next enters a tile", not
        # instantly mid-corridor. Defer it via the pending-reversal flag,
        # consumed by _step_toward/_step_random's on_center the next time
        # this ghost actually arrives at a tile center.
        self._pending_reversal = True

    def get_eaten(self) -> None:
        self.mode = GhostMode.EATEN
        self._snap_and_reverse()

    def _snap_and_reverse(self) -> None:
        """Force an instant direction reversal, safely.

        Forcing ``direction = direction.opposite`` alone is not enough:
        the tracked segment target (``_target_x/_target_y``) would still
        describe *continuing the old direction*, which after a reversal
        sits behind the actor rather than ahead of it. Distance-to-target
        would then grow every frame instead of shrink, so the actor would
        never "arrive", never re-run a wall check, and sail straight
        through walls forever. Snapping to the nearest tile center first
        keeps the segment target consistent with the new direction.
        """
        self.x, self.y = float(round(self.x)), float(round(self.y))
        self.direction = self.direction.opposite
        self.queued_direction = Direction.NONE
        self._pending_reversal = False
        dx, dy = self.direction.vector
        self._target_x = self.x + dx
        self._target_y = self.y + dy

    @property
    def is_flashing(self) -> bool:
        """True during the alternating blue/white flash near the end of
        frightened mode. One flash = two FRIGHTENED_FLASH_TOGGLE_SECONDS
        intervals (blue, then white); the flash *count* varies by level,
        so the lead-in window is computed per ghost, not a flat constant.
        """
        if self.mode is not GhostMode.FRIGHTENED or self.frightened_flash_count <= 0:
            return False
        toggle = config.FRIGHTENED_FLASH_TOGGLE_SECONDS
        lead_in = self.frightened_flash_count * 2 * toggle
        if self.frightened_seconds_left > lead_in:
            return False
        elapsed_in_window = lead_in - self.frightened_seconds_left
        return int(elapsed_in_window / toggle) % 2 == 0

    # -- per-frame update -----------------------------------------------------
    def update(
        self,
        maze: Maze,
        dt: float,
        player,
        ghosts: Dict[str, "Ghost"],
        global_phase: str,
        rng: random.Random,
    ) -> None:
        if self.mode is GhostMode.HOUSE:
            self._bob_in_house(dt)
            return

        if self.mode is GhostMode.FRIGHTENED:
            self.frightened_seconds_left = max(0.0, self.frightened_seconds_left - dt)
            if self.frightened_seconds_left <= 0.0:
                # No reversal on leaving frightened -- only on entering it.
                self.mode = GhostMode.CHASE if global_phase == "chase" else GhostMode.SCATTER

        can_enter = maze.can_ghost_enter
        speed = self._current_speed(maze)

        if self.mode is GhostMode.LEAVING:
            target = _house_exit_tile(maze)
            self._step_toward(maze, dt, can_enter, target, speed)
            if self.tile == target and self.is_centered():
                self.mode = GhostMode.CHASE if global_phase == "chase" else GhostMode.SCATTER
            return

        if self.mode is GhostMode.EATEN:
            target = _gate_tile(maze)
            self._step_toward(maze, dt, can_enter, target, speed)
            if self.tile == target and self.is_centered():
                self.mode = GhostMode.HOUSE
                self.direction = Direction.NONE
                self._house_anchor_row = self.y
                self.released = False  # so it can leave the house again later
            return

        if self.mode is GhostMode.FRIGHTENED:
            self._step_random(maze, dt, can_enter, rng, speed)
            return

        # SCATTER or CHASE: personality-driven target seeking. Cruise Elroy
        # (Gates only, once active) targets Scotty directly even during
        # scatter, per the documented rule -- the other three ghosts keep
        # scattering normally.
        if self.mode is GhostMode.SCATTER and not (self.name == "gates" and self.elroy_stage > 0):
            target = self.corner
        else:
            target = TARGET_FUNCTIONS[self.name](self, player, ghosts, maze)
        self._step_toward(maze, dt, can_enter, target, speed)

    def _current_speed(self, maze: Maze) -> float:
        if self.mode is GhostMode.FRIGHTENED:
            base = self.frightened_speed
        elif self.mode is GhostMode.EATEN:
            base = self.eyes_speed
        elif self.name == "gates" and self.elroy_stage == 2:
            base = self._elroy2_speed
        elif self.name == "gates" and self.elroy_stage == 1:
            base = self._elroy1_speed
        else:
            base = self.base_speed
        row = round(self.y)
        if maze.is_tunnel_row(row) and self.mode not in (GhostMode.EATEN,):
            return self.tunnel_speed
        return base

    def _step_toward(self, maze: Maze, dt: float, can_enter, target: Coord, speed: float) -> None:
        def on_center(actor: "Ghost") -> None:
            if actor._pending_reversal:
                actor._pending_reversal = False
                actor.queue_direction(actor.direction.opposite)
                return
            if actor.tile == target:
                # Arrived exactly at a static target (e.g. the house exit
                # or the gate). The greedy seek rule below always picks
                # *some* direction to keep closing on a target, so without
                # this explicit stop it would sail straight past forever
                # (there is no "distance to self" that beats moving away
                # by exactly one tile). Force a real stop here; queuing
                # alone is not enough since a still-valid old direction
                # would otherwise just carry on.
                actor.direction = Direction.NONE
                actor.queue_direction(Direction.NONE)
                return
            actor.queue_direction(_best_seeking_direction(actor, maze, can_enter, target))

        self.step(maze, dt, can_enter, speed=speed, on_center=on_center)

    def _step_random(self, maze: Maze, dt: float, can_enter, rng: random.Random, speed: float) -> None:
        def on_center(actor: "Ghost") -> None:
            if actor._pending_reversal:
                actor._pending_reversal = False
                actor.queue_direction(actor.direction.opposite)
                return
            options = actor.available_directions(maze, can_enter)
            if actor.direction is not Direction.NONE:
                reverse = actor.direction.opposite
                non_reverse = [d for d in options if d != reverse]
                if non_reverse:
                    options = non_reverse
            if options:
                actor.queue_direction(rng.choice(options))

        self.step(maze, dt, can_enter, speed=speed, on_center=on_center)


def _best_seeking_direction(ghost: Ghost, maze: Maze, can_enter, target: Coord) -> Direction:
    col, row = ghost.tile
    options = ghost.available_directions(maze, can_enter)
    if ghost.direction is not Direction.NONE:
        reverse = ghost.direction.opposite
        non_reverse = [d for d in options if d != reverse]
        if non_reverse:
            options = non_reverse
    if not options:
        return Direction.NONE

    tx, ty = target

    def score(direction: Direction) -> Tuple[float, int]:
        dx, dy = direction.vector
        ncol, nrow = col + dx, row + dy
        if maze.is_tunnel_row(row):
            ncol = maze.wrap_col(ncol)
        dist_sq = (ncol - tx) ** 2 + (nrow - ty) ** 2
        return (dist_sq, TURN_PRIORITY.index(direction))

    return min(options, key=score)


def create_ghosts(maze: Maze, level: int) -> Dict[str, Ghost]:
    """Build the four ghosts at their maze-defined starting tiles, with
    every documented per-level speed pre-computed (Dossier Table A.1)."""
    from . import levels

    missing = set(GHOST_MARKERS.values()) - set(maze.ghost_starts)
    if missing:
        raise ValueError(
            f"maze '{maze.name}' is missing ghost start marker(s) for: {sorted(missing)}"
        )

    normal_speed = levels.ghost_normal_speed(level)
    frightened_speed = levels.ghost_frightened_speed(level)
    tunnel_speed = levels.ghost_tunnel_speed(level)
    eyes_speed = levels.eyes_speed(level)
    house_pace_speed = levels.house_pace_speed(level)
    elroy1_speed = levels.elroy1_speed(level)
    elroy2_speed = levels.elroy2_speed(level)

    corners = _corners(maze)
    ghosts: Dict[str, Ghost] = {}
    for name, start in maze.ghost_starts.items():
        ghosts[name] = Ghost(
            name,
            start,
            corners[name],
            normal_speed,
            frightened_speed=frightened_speed,
            tunnel_speed=tunnel_speed,
            eyes_speed=eyes_speed,
            house_pace_speed=house_pace_speed,
            elroy1_speed=elroy1_speed,
            elroy2_speed=elroy2_speed,
        )
    return ghosts


class ScatterChaseClock:
    """Advances through a per-level (phase, seconds) timetable (see
    :func:`pacdawg.levels.scatter_chase_timetable_for_level`).

    Advancing this clock while any ghost is frightened is the caller's
    responsibility to skip (Dossier Ch. 2: "the scatter/chase timer is
    paused" during frightened mode, and resumes afterward) -- this class
    only tracks elapsed time within whichever timetable it was given.
    """

    def __init__(self, timetable: List[Tuple[str, float]]):
        self.timetable = timetable
        self.index = 0
        self.elapsed = 0.0

    @property
    def phase(self) -> str:
        return self.timetable[self.index][0]

    def update(self, dt: float) -> bool:
        """Advance the clock; returns True the frame the phase changes."""
        self.elapsed += dt
        duration = self.timetable[self.index][1]
        if self.elapsed >= duration and self.index < len(self.timetable) - 1:
            self.elapsed = 0.0
            self.index += 1
            return True
        return False


def apply_phase_change(ghosts: Dict[str, Ghost], phase: str) -> None:
    """Flag every actively-hunting ghost for reversal on a scatter/chase
    phase flip; frightened and eaten ghosts are left alone since they are
    not participating in the scatter/chase rhythm.

    Per the documented rule, "reversal takes effect when the ghost next
    enters a tile" -- not instantly mid-corridor -- so this only sets the
    pending-reversal flag, consumed by the ghost's own on_center callback
    the next time it actually arrives at a tile center.
    """
    new_mode = GhostMode.CHASE if phase == "chase" else GhostMode.SCATTER
    for ghost in ghosts.values():
        if ghost.mode in (GhostMode.SCATTER, GhostMode.CHASE):
            ghost.mode = new_mode
            ghost._pending_reversal = True
