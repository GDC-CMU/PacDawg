"""Tests for the attract-mode demo's simple self-playing controller
(pacdawg.demo_ai). Pure logic, no display or hardware needed.
"""
from __future__ import annotations

import unittest

from pacdawg import demo_ai, levels
from pacdawg.entities import Direction, MovingActor
from pacdawg.ghosts import GhostMode

_CARDINALS = (Direction.UP, Direction.DOWN, Direction.LEFT, Direction.RIGHT)


class _StubGhost:
    """A minimal stand-in exposing only what demo_ai needs (.tile,
    .mode) -- avoids constructing a real Ghost just to place it."""

    def __init__(self, tile, mode):
        self.tile = tile
        self.mode = mode


def _legal_directions(maze, col, row):
    return [
        d
        for d in _CARDINALS
        if maze.can_player_enter(col + d.vector[0], row + d.vector[1])
    ]


class ChooseDirectionTests(unittest.TestCase):
    def setUp(self):
        self.maze = levels.build_maze(1)

    def test_returns_a_legal_direction_with_no_ghosts_around(self):
        col, row = self.maze.player_start
        player = MovingActor(col, row)
        direction = demo_ai.choose_direction(self.maze, player, {})
        self.assertIsNotNone(direction)
        dcol, drow = direction.vector
        self.assertTrue(self.maze.can_player_enter(col + dcol, row + drow))

    def test_heads_toward_the_nearest_pellet(self):
        col, row = self.maze.player_start
        player = MovingActor(col, row)
        direction = demo_ai.choose_direction(self.maze, player, {})
        target = demo_ai._nearest_pellet(self.maze, col, row)
        self.assertIsNotNone(target)
        dcol, drow = direction.vector
        before = abs(col - target[0]) + abs(row - target[1])
        after = abs((col + dcol) - target[0]) + abs((row + drow) - target[1])
        self.assertLessEqual(after, before)

    def test_steers_away_from_a_nearby_hunting_ghost(self):
        col, row = self.maze.player_start
        player = MovingActor(col, row)
        legal = _legal_directions(self.maze, col, row)
        self.assertTrue(legal)
        if len(legal) < 2:
            self.skipTest("player_start has only one legal direction; nothing to avoid into")
        threat_direction = legal[0]
        dcol, drow = threat_direction.vector
        ghost = _StubGhost((col + dcol, row + drow), GhostMode.CHASE)
        direction = demo_ai.choose_direction(self.maze, player, {"gates": ghost})
        self.assertNotEqual(direction, threat_direction)

    def test_ignores_a_frightened_ghost_as_a_threat(self):
        col, row = self.maze.player_start
        player = MovingActor(col, row)
        ghost = _StubGhost((col, row), GhostMode.FRIGHTENED)  # right on top, but edible
        direction = demo_ai.choose_direction(self.maze, player, {"gates": ghost})
        self.assertIsNotNone(direction)

    def test_ignores_a_ghost_still_in_the_house(self):
        col, row = self.maze.player_start
        player = MovingActor(col, row)
        ghost = _StubGhost((col, row), GhostMode.HOUSE)
        direction_with = demo_ai.choose_direction(self.maze, player, {"gates": ghost})
        direction_without = demo_ai.choose_direction(self.maze, player, {})
        self.assertEqual(direction_with, direction_without)

    def test_never_freezes_when_every_direction_is_threatened(self):
        col, row = self.maze.player_start
        player = MovingActor(col, row)
        ghosts = {}
        for i, d in enumerate(_CARDINALS):
            dcol, drow = d.vector
            ghosts[f"g{i}"] = _StubGhost((col + dcol, row + drow), GhostMode.CHASE)
        direction = demo_ai.choose_direction(self.maze, player, ghosts)
        self.assertIsNotNone(direction)  # picks the least-bad option, never gives up

    def test_none_only_when_truly_boxed_in(self):
        # A degenerate stand-in maze with no legal moves at all -- must
        # say so rather than crash or fabricate a move.
        class _BoxedMaze:
            cols = 3
            rows = 3

            def can_player_enter(self, col, row):
                return False

            def is_tunnel_row(self, row):
                return False

            def wrap_col(self, col):
                return col

        player = MovingActor(1, 1)
        self.assertIsNone(demo_ai.choose_direction(_BoxedMaze(), player, {}))


if __name__ == "__main__":
    unittest.main()
