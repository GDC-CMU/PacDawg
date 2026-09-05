"""Tile-aligned movement primitives shared by Scotty and the ghosts.

This module has no rendering concerns and does not import pygame: it
only knows about tile coordinates, directions, and the maze's walkability
rules. Movement is resolved one tile-center at a time so turns only ever
happen at junctions, matching the arcade maze-chase genre's feel, and a
direction queued before reaching a junction is honored the instant the
junction is reachable.
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
    """The player character: a small, shaggy Scottish Terrier."""

    def __init__(self, col: int, row: int, speed: float):
        super().__init__(col, row, speed)
        self.facing = Direction.RIGHT  # last non-NONE direction, for animation

    def update(self, maze: Maze, dt: float) -> None:
        self.step(maze, dt, maze.can_player_enter)
        if self.direction is not Direction.NONE:
            self.facing = self.direction
