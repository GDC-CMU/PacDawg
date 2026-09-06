"""Tile-aligned movement primitives shared by Scotty and the ghosts.

This module has no rendering concerns and does not import pygame: it
only knows about tile coordinates, directions, and the maze's walkability
rules.

:class:`MovingActor` provides the base "turn only at an exact tile
center" model used by ghosts (see :mod:`pacdawg.ghosts`): a direction is
only reconsidered once the actor's position reaches a segment target
exactly. :class:`Scotty` overrides movement with the documented arcade
cornering/pre-turn model instead -- turns are re-evaluated every frame
against Scotty's *current* tile, take effect immediately (no waiting for
the center), and Scotty drifts diagonally toward the new lane's
centerline while cornering. This asymmetry (ghosts center-only, Scotty
pre-turn-and-corner) is deliberate and documented as the mechanical basis
of the player's speed advantage; see ``pacman-reference.md`` sec. 7.
"""
from __future__ import annotations

from enum import Enum
from typing import Callable, Tuple

from .maze import Maze

Coord = Tuple[int, int]


class Direction(Enum):
    NONE = (0, 0)
    UP = (0, -1)
    DOWN = (0, 1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)

    @property
    def vector(self) -> Coord:
        return self.value

    @property
    def opposite(self) -> "Direction":
        return _OPPOSITES[self]


_OPPOSITES = {
    Direction.NONE: Direction.NONE,
    Direction.UP: Direction.DOWN,
    Direction.DOWN: Direction.UP,
    Direction.LEFT: Direction.RIGHT,
    Direction.RIGHT: Direction.LEFT,
}

# All four cardinal directions, a stable order used for tie-breaking when a
# ghost has more than one equally-good option (classic maze-chase games
# prefer up, then left, then down, then right when distances tie).
TURN_PRIORITY = (Direction.UP, Direction.LEFT, Direction.DOWN, Direction.RIGHT)

_EPSILON = 1e-6

EnterPredicate = Callable[[int, int], bool]


class MovingActor:
    """A position on the tile grid that moves toward tile centers.

    Subclasses (Scotty, ghosts) provide the entry predicate (whether a
    tile may be entered) and decide when to change ``queued_direction``.
    """

    def __init__(self, col: int, row: int, speed: float = 8.0):
        self.x: float = float(col)
        self.y: float = float(row)
        self.direction: Direction = Direction.NONE
        self.queued_direction: Direction = Direction.NONE
        self.speed = speed  # tiles per second
        # The tile-center this actor is currently walking toward. Tracking
        # this explicitly (rather than re-deriving "current tile" from
        # round(x, y) on every sub-step) is essential: round() flips to the
        # next integer as soon as an actor crosses the halfway point of a
        # tile, which is *before* it has actually arrived, and would
        # otherwise cause the target to silently jump one tile further out
        # mid-flight.
        self._target_x: float = float(col)
        self._target_y: float = float(row)

    @property
    def tile(self) -> Coord:
        return (round(self.x), round(self.y))

    def is_centered(self) -> bool:
        return (
            abs(self.x - round(self.x)) < _EPSILON
            and abs(self.y - round(self.y)) < _EPSILON
        )

    def teleport(self, col: int, row: int, direction: Direction = Direction.NONE) -> None:
        self.x, self.y = float(col), float(row)
        self._target_x, self._target_y = float(col), float(row)
        self.direction = direction
        self.queued_direction = Direction.NONE

    def queue_direction(self, direction: Direction) -> None:
        self.queued_direction = direction

    def step(
        self,
        maze: Maze,
        dt: float,
        can_enter: EnterPredicate,
        speed: float = None,
        on_center: Callable[["MovingActor"], None] = None,
    ) -> None:
        """Advance up to ``speed * dt`` tiles, turning only at centers.

        ``on_center`` (if given) is invoked every time the actor arrives
        exactly at a tile center, before the queued direction is resolved
        -- this is how ghosts recompute their target-seeking direction
        fresh at each junction rather than only once per frame.
        """
        remaining = (self.speed if speed is None else speed) * dt
        guard = 0
        while remaining > _EPSILON and guard < 8:
            guard += 1
            distance = abs(self._target_x - self.x) + abs(self._target_y - self.y)
            if distance < _EPSILON:
                self._arrive_and_resolve(maze, can_enter, on_center)
                if self.direction is Direction.NONE:
                    break
                distance = abs(self._target_x - self.x) + abs(self._target_y - self.y)
                if distance < _EPSILON:
                    break  # no legal move from here; stay put this frame

            dx, dy = self.direction.vector
            travel = min(remaining, distance)
            self.x += dx * travel
            self.y += dy * travel
            remaining -= travel

    def _arrive_and_resolve(
        self, maze: Maze, can_enter: EnterPredicate, on_center: Callable = None
    ) -> None:
        # Snap onto the target exactly, then correct for a tunnel wrap: the
        # target may have been set one tile past a maze edge (col -1 or
        # col == maze.cols) so straight-line distance math stays valid
        # through the wrap; only now, having arrived, do we fold it back
        # into the valid column range.
        self.x, self.y = self._target_x, self._target_y
        if self.x < 0:
            self.x += maze.cols
        elif self.x >= maze.cols:
            self.x -= maze.cols
        self._target_x, self._target_y = self.x, self.y

        if on_center is not None:
            on_center(self)

        col, row = round(self.x), round(self.y)
        if self.queued_direction is not Direction.NONE:
            if self._can_step(maze, col, row, self.queued_direction, can_enter):
                self.direction = self.queued_direction
                self.queued_direction = Direction.NONE

        if not self._can_step(maze, col, row, self.direction, can_enter):
            self.direction = Direction.NONE
            return

        dx, dy = self.direction.vector
        # Deliberately unwrapped: may be -1 or maze.cols on a tunnel row.
        # See the wrap-correction comment above.
        self._target_x = self.x + dx
        self._target_y = self.y + dy

    @staticmethod
    def _can_step(
        maze: Maze, col: int, row: int, direction: Direction, can_enter: EnterPredicate
    ) -> bool:
        if direction is Direction.NONE:
            return False
        dx, dy = direction.vector
        ncol, nrow = col + dx, row + dy
        if maze.is_tunnel_row(row):
            ncol = maze.wrap_col(ncol)
        return can_enter(ncol, nrow)

    def available_directions(self, maze: Maze, can_enter: EnterPredicate) -> list:
        """Directions Scotty/a ghost could take from its current tile."""
        col, row = round(self.x), round(self.y)
        return [
            d
            for d in TURN_PRIORITY
            if self._can_step(maze, col, row, d, can_enter)
        ]


class Scotty(MovingActor):
    """The player character: a small, shaggy Scottish Terrier.

    Movement follows the documented arcade input/cornering model (see
    ``pacman-reference.md`` sec. 7), which is deliberately *not* the same
    algorithm ghosts use:

    * The held direction is re-sampled every frame against the tile
      Scotty's center currently occupies (``round(x, y)``) -- not just at
      the exact tile center. A turn takes effect immediately, wherever
      inside the tile he is, as soon as the adjacent tile in that
      direction opens up. Because ``round()`` flips to the new tile up to
      half a tile before the geometric center, this naturally reproduces
      the documented "pre-turn" window with no timer of any kind.
    * A wanted direction that is currently blocked simply isn't cleared;
      it's re-tried every subsequent frame (a one-slot latch, not a timed
      buffer), so it fires the instant a gap appears -- including while
      Scotty is stopped dead against a wall.
    * A 180-degree reversal is just a turn where the "adjacent tile" is
      guaranteed open (it's the tile Scotty just came from), so it always
      takes effect on the very next frame.
    * While moving, Scotty also drifts up to one step per frame toward
      the centerline of whichever axis he *isn't* currently traveling
      along, cutting corners at an effective diagonal rather than
      snapping onto the new lane. Ghosts get none of this: they may only
      change direction exactly on a tile center (see Ghost/MovingActor),
      which is the entire mechanical basis of Scotty's cornering
      advantage over them.
    """

    def __init__(self, col: int, row: int, speed: float):
        super().__init__(col, row, speed)
        self.facing = Direction.RIGHT  # last non-NONE direction, for animation
        self.pause_timer = 0.0  # brief freeze after eating a (power) pellet
        self.chomp_travel = 0.0  # cosmetic, bounded to one tile; never drives motion
        self.moved_this_frame = False

    @property
    def chomp_frame(self) -> int:
        """Close on collection/rest; open halfway through each travelled tile."""
        if self.pause_timer > 0 or not self.moved_this_frame:
            return 1
        return 1 + int(self.chomp_travel / 0.5)

    def teleport(self, col: int, row: int, direction: Direction = Direction.NONE) -> None:
        super().teleport(col, row, direction)
        self.chomp_travel = 0.0
        self.moved_this_frame = False

    def pause(self, seconds: float) -> None:
        """Freeze movement for a short spell, as when eating a dot."""
        self.pause_timer = max(self.pause_timer, seconds)
        self.chomp_travel = 0.0

    def update(self, maze: Maze, dt: float) -> None:
        self.moved_this_frame = False
        if self.pause_timer > 0:
            self.pause_timer = max(0.0, self.pause_timer - dt)
            self._steer(maze)  # input still re-sampled during the freeze
            return
        self._steer(maze)
        self._advance(maze, dt)
        if self.direction is not Direction.NONE:
            self.facing = self.direction

    def _steer(self, maze: Maze) -> None:
        """Re-sample the held direction every frame against the *current*
        tile (not the exact center) -- the documented pre-turn model."""
        can_enter = maze.can_player_enter
        col, row = round(self.x), round(self.y)
        wanted = self.queued_direction
        if wanted is not Direction.NONE and wanted is not self.direction:
            if self._can_step(maze, col, row, wanted, can_enter):
                self._begin_direction(maze, wanted, col, row)

    def _begin_direction(self, maze: Maze, direction: Direction, col: int, row: int) -> None:
        self.direction = direction
        dx, dy = direction.vector
        ncol, nrow = col + dx, row + dy
        if maze.is_tunnel_row(row):
            ncol = maze.wrap_col(ncol)
        # Only the axis of travel needs a fresh segment target; the other
        # axis keeps drifting toward its own centerline in _advance(),
        # which is what produces the cornering cut when a turn is taken
        # before Scotty is fully aligned with the new lane.
        if dx != 0:
            self._target_x = float(ncol)
        else:
            self._target_y = float(nrow)

    def _advance(self, maze: Maze, dt: float) -> None:
        if self.direction is Direction.NONE:
            return
        can_enter = maze.can_player_enter
        remaining = self.speed * dt
        guard = 0
        while remaining > _EPSILON and guard < 8:
            guard += 1
            dx, dy = self.direction.vector
            if dx != 0:
                primary_attr, target_attr, perp_attr = "x", "_target_x", "y"
            else:
                primary_attr, target_attr, perp_attr = "y", "_target_y", "x"

            primary_value = getattr(self, primary_attr)
            target_value = getattr(self, target_attr)
            primary_distance = abs(target_value - primary_value)

            if primary_distance < _EPSILON:
                # Arrived at the next tile boundary on the axis of travel:
                # snap, then decide whether continuing is still legal.
                setattr(self, primary_attr, target_value)
                col, row = round(self.x), round(self.y)
                if not self._can_step(maze, col, row, self.direction, can_enter):
                    self.direction = Direction.NONE
                    break
                ndx, ndy = self.direction.vector
                ncol, nrow = col + ndx, row + ndy
                if maze.is_tunnel_row(row):
                    ncol = maze.wrap_col(ncol)
                setattr(self, target_attr, float(ncol if ndx != 0 else nrow))
                target_value = getattr(self, target_attr)
                primary_value = getattr(self, primary_attr)
                primary_distance = abs(target_value - primary_value)
                if primary_distance < _EPSILON:
                    break  # no legal move from here; stay put this frame

            travel = min(remaining, primary_distance)
            self.chomp_travel = (self.chomp_travel + travel) % 1.0
            self.moved_this_frame = self.moved_this_frame or travel > _EPSILON
            sign = 1.0 if target_value >= primary_value else -1.0
            setattr(self, primary_attr, primary_value + sign * travel)
            remaining -= travel

            # Cornering: drift the perpendicular axis toward its own
            # centerline by up to the same distance just traveled.
            perp_value = getattr(self, perp_attr)
            center = float(round(perp_value))
            drift = min(travel, abs(center - perp_value))
            if perp_value < center:
                setattr(self, perp_attr, perp_value + drift)
            elif perp_value > center:
                setattr(self, perp_attr, perp_value - drift)

            if maze.is_tunnel_row(round(self.y)):
                if self.x < 0:
                    self.x += maze.cols
                elif self.x >= maze.cols:
                    self.x -= maze.cols
