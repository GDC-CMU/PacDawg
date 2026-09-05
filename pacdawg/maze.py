"""Maze grid parsing and pellet accounting.

Layouts are authored as plain text grids (see :mod:`pacdawg.levels`) so
they are easy to read, diff, and hand-edit. This module turns that text
into a validated, queryable :class:`Maze` object. It deliberately avoids
importing :mod:`pygame` so maze logic is testable without a display.
"""
from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Set, Tuple

Coord = Tuple[int, int]  # (col, row)

WALL = "#"
PELLET = "."
POWER_PELLET = "o"
EMPTY = " "
PLAYER_START = "P"
GATE = "="
TUNNEL = "T"

# Ghost house start markers, mapped to the ghost personality that spawns
# there. See pacdawg.ghosts for what each personality actually does.
GHOST_MARKERS = {"1": "gates", "2": "hunt", "3": "wean", "4": "doherty"}

VALID_CHARS = {WALL, PELLET, POWER_PELLET, EMPTY, PLAYER_START, GATE, TUNNEL}
VALID_CHARS.update(GHOST_MARKERS.keys())


class MazeError(ValueError):
    """Raised when a maze text layout fails validation.

    Kept as a distinct, loud exception type (rather than silently
    tolerating bad data) so a broken layout is caught the moment it is
    authored, not mid-game.
    """


class Maze:
    """A validated, mutable maze: walls, gate, tunnels, and pellets."""

    def __init__(self, layout: List[str], name: str = "unnamed"):
        if not layout:
            raise MazeError(f"maze '{name}' has no rows")

        width = len(layout[0])
        if width == 0:
            raise MazeError(f"maze '{name}' rows must not be empty")
        for row_index, row in enumerate(layout):
            if len(row) != width:
                raise MazeError(
                    f"maze '{name}' row {row_index} has length {len(row)}, "
                    f"expected {width} (all rows must be the same length)"
                )
            for col_index, ch in enumerate(row):
                if ch not in VALID_CHARS:
                    raise MazeError(
                        f"maze '{name}' row {row_index} col {col_index} has "
                        f"unknown character {ch!r}"
                    )

        self.name = name
        self.cols = width
        self.rows = len(layout)
        self._layout = layout

        self.walls: Set[Coord] = set()
        self.gates: Set[Coord] = set()
        self.tunnel_rows: Set[int] = set()
        self.pellets: Set[Coord] = set()
        self.power_pellets: Set[Coord] = set()
        self.ghost_starts: Dict[str, Coord] = {}
        player_start: Optional[Coord] = None

        for row_index, row in enumerate(layout):
            for col_index, ch in enumerate(row):
                coord = (col_index, row_index)
                if ch == WALL:
                    self.walls.add(coord)
                elif ch == GATE:
                    self.gates.add(coord)
                elif ch == PELLET:
                    self.pellets.add(coord)
                elif ch == POWER_PELLET:
                    self.power_pellets.add(coord)
                elif ch == PLAYER_START:
                    if player_start is not None:
                        raise MazeError(
                            f"maze '{name}' has more than one player start 'P'"
                        )
                    player_start = coord
                elif ch in GHOST_MARKERS:
                    ghost_name = GHOST_MARKERS[ch]
                    if ghost_name in self.ghost_starts:
                        raise MazeError(
                            f"maze '{name}' has more than one start for ghost "
                            f"'{ghost_name}'"
                        )
                    self.ghost_starts[ghost_name] = coord
                elif ch == TUNNEL:
                    pass  # validated per-row below

        if player_start is None:
            raise MazeError(f"maze '{name}' has no player start 'P'")
        self.player_start = player_start

        if not self.pellets and not self.power_pellets:
            raise MazeError(f"maze '{name}' has no pellets to eat")

        for row_index, row in enumerate(layout):
            left_is_tunnel = row[0] == TUNNEL
            right_is_tunnel = row[-1] == TUNNEL
            if left_is_tunnel != right_is_tunnel:
                raise MazeError(
                    f"maze '{name}' row {row_index} has a tunnel opening on "
                    "only one side; tunnels must be open at both ends"
                )
            if left_is_tunnel and right_is_tunnel:
                self.tunnel_rows.add(row_index)

        self.total_pellets = len(self.pellets) + len(self.power_pellets)
        self._validate_connectivity()

    # -- queries --------------------------------------------------------
    def in_bounds(self, col: int, row: int) -> bool:
        return 0 <= row < self.rows and 0 <= col < self.cols

    def is_wall(self, col: int, row: int) -> bool:
        if not self.in_bounds(col, row):
            return True
        return (col, row) in self.walls

    def is_gate(self, col: int, row: int) -> bool:
        return (col, row) in self.gates

    def can_ghost_enter(self, col: int, row: int) -> bool:
        """Ghosts may pass through the gate; walls still block them."""
        if not self.in_bounds(col, row):
            return False
        return (col, row) not in self.walls

    def can_player_enter(self, col: int, row: int) -> bool:
        """Scotty is blocked by both walls and the ghost-house gate."""
        if not self.in_bounds(col, row):
            return False
        coord = (col, row)
        return coord not in self.walls and coord not in self.gates

    def is_tunnel_row(self, row: int) -> bool:
        return row in self.tunnel_rows

    def wrap_col(self, col: int) -> int:
        if col < 0:
            return self.cols - 1
        if col >= self.cols:
            return 0
        return col

    # -- pellet accounting ------------------------------------------------
    def eat_at(self, col: int, row: int) -> Optional[str]:
        """Remove and report any pellet at a tile.

        Returns ``"pellet"``, ``"power"``, or ``None``.
        """
        coord = (col, row)
        if coord in self.pellets:
            self.pellets.discard(coord)
            return "pellet"
        if coord in self.power_pellets:
            self.power_pellets.discard(coord)
            return "power"
        return None

    @property
    def pellets_remaining(self) -> int:
        return len(self.pellets) + len(self.power_pellets)

    @property
    def pellets_eaten(self) -> int:
        return self.total_pellets - self.pellets_remaining

    @property
    def is_complete(self) -> bool:
        return self.pellets_remaining == 0

    def reset_pellets(self) -> None:
        """Restore pellets from the original layout (new life on same level)."""
        self.pellets.clear()
        self.power_pellets.clear()
        for row_index, row in enumerate(self._layout):
            for col_index, ch in enumerate(row):
                if ch == PELLET:
                    self.pellets.add((col_index, row_index))
                elif ch == POWER_PELLET:
                    self.power_pellets.add((col_index, row_index))

    # -- validation --------------------------------------------------------
    def _validate_connectivity(self) -> None:
        """Every pellet must be reachable from the player start.

        A design-time sanity check: an unreachable pellet would make a
        level impossible to clear. Reachability is computed as Scotty
        would move (blocked by walls and the gate), with tunnel wrap-around
        at edges included.
        """
        start = self.player_start
        visited: Set[Coord] = {start}
        queue = deque([start])
        while queue:
            col, row = queue.popleft()
            neighbors = [(col + 1, row), (col - 1, row), (col, row + 1), (col, row - 1)]
            if self.is_tunnel_row(row):
                if col == 0:
                    neighbors.append((self.cols - 1, row))
                elif col == self.cols - 1:
                    neighbors.append((0, row))
            for ncol, nrow in neighbors:
                ncol = self.wrap_col(ncol) if self.is_tunnel_row(row) else ncol
                coord = (ncol, nrow)
                if coord in visited:
                    continue
                if not self.can_player_enter(ncol, nrow):
                    continue
                visited.add(coord)
                queue.append(coord)

        unreachable = (self.pellets | self.power_pellets) - visited
        if unreachable:
            raise MazeError(
                f"maze '{self.name}' has {len(unreachable)} unreachable "
                f"pellet(s), e.g. {sorted(unreachable)[0]}"
            )
