"""A deliberately simple, self-playing controller for Scotty, used only
by the attract-mode demo (see :mod:`pacdawg.game`'s ``_update_demo``).

It does not need to be good -- the client's brief is explicit that it
just needs to be alive and legible from a few feet away: seek the
nearest pellet, but steer away from any ghost that has gotten close.
This is a greedy heuristic, not real planning, and that's fine; a demo
that looked *too* skilled would be less honest about what the real game
feels like to a first-time player.

Pure logic, no pygame: given the maze and the current positions of the
demo Scotty and the ghosts, it returns the single best
:class:`~pacdawg.entities.Direction` to head in this frame (or ``None``
if there is truly no legal move at all, which should not happen on a
validated maze).
"""
from __future__ import annotations

from typing import Dict, Optional

from .entities import Direction, MovingActor
from .ghosts import Ghost, GhostMode
from .maze import Maze

_DIRECTIONS = (Direction.UP, Direction.DOWN, Direction.LEFT, Direction.RIGHT)
_DELTA = {
    Direction.UP: (0, -1),
    Direction.DOWN: (0, 1),
    Direction.LEFT: (-1, 0),
    Direction.RIGHT: (1, 0),
}

# How many tiles away a hunting ghost has to be before the demo AI
# treats it as a threat worth steering away from. Deliberately small
# and unsophisticated -- this is a demo, not real difficulty.
GHOST_AVOID_RADIUS_TILES = 4

# Ghosts in these modes are not a threat: still in the house/leaving it
# isn't dangerous yet, and eaten (eyes-only) ghosts can't catch Scotty.
_NOT_A_THREAT = frozenset({GhostMode.HOUSE, GhostMode.LEAVING, GhostMode.EATEN, GhostMode.FRIGHTENED})


def choose_direction(
    maze: Maze, player: MovingActor, ghosts: Dict[str, Ghost]
) -> Optional[Direction]:
    """The demo Scotty's one decision per frame: prefer whichever legal,
    not-currently-threatened direction gets closest to the nearest
    pellet; if every legal direction is threatened, take the least bad
    one rather than freezing -- a demo that stands still reads as
    broken, not cautious."""
    col, row = player.tile
    legal = [d for d in _DIRECTIONS if _walkable(maze, col, row, d)]
    if not legal:
        return None

    threatened = _threatened_directions(maze, col, row, ghosts)
    safe = [d for d in legal if d not in threatened] or legal

    target = _nearest_pellet(maze, col, row)
    if target is None:
        return safe[0]

    tcol, trow = target

    def distance_if_taken(direction: Direction) -> int:
        dcol, drow = _DELTA[direction]
        return abs((col + dcol) - tcol) + abs((row + drow) - trow)

    return min(safe, key=distance_if_taken)


def _walkable(maze: Maze, col: int, row: int, direction: Direction) -> bool:
    dcol, drow = _DELTA[direction]
    ncol, nrow = col + dcol, row + drow
    if maze.is_tunnel_row(row):
        ncol = maze.wrap_col(ncol)
    return maze.can_player_enter(ncol, nrow)


def _threatened_directions(maze: Maze, col: int, row: int, ghosts: Dict[str, Ghost]) -> set:
    threatened = set()
    for ghost in ghosts.values():
        if ghost.mode in _NOT_A_THREAT:
            continue
        gcol, grow = ghost.tile
        dist = abs(gcol - col) + abs(grow - row)
        if dist > GHOST_AVOID_RADIUS_TILES:
            continue
        for direction in _DIRECTIONS:
            dcol, drow = _DELTA[direction]
            ncol, nrow = col + dcol, row + drow
            if abs(ncol - gcol) + abs(nrow - grow) < dist:
                threatened.add(direction)
    return threatened


def _nearest_pellet(maze: Maze, col: int, row: int):
    best = None
    best_dist = None
    for coord in maze.pellets:
        dist = abs(coord[0] - col) + abs(coord[1] - row)
        if best_dist is None or dist < best_dist:
            best, best_dist = coord, dist
    for coord in maze.power_pellets:
        dist = abs(coord[0] - col) + abs(coord[1] - row)
        if best_dist is None or dist < best_dist:
            best, best_dist = coord, dist
    return best
