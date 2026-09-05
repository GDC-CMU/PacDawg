"""Tests for tile-aligned movement: turning, walls, and tunnel wrap."""
from __future__ import annotations

import unittest

from pacdawg.entities import Direction, MovingActor, Scotty
from pacdawg.maze import Maze

_CORRIDOR = [
    "#######",
    "#.....#",
    "#.###.#",
    "#.....#",
    "#.###.#",
    "#..P..#",
    "#######",
]

_TUNNEL = [
    "#######",
    "T....PT",
    "#######",
]


class MovementTests(unittest.TestCase):
    def setUp(self):
        self.maze = Maze(_CORRIDOR, name="corridor-test")

    def _run_for(self, actor, seconds, dt=1 / 60.0):
        steps = int(round(seconds / dt))
        for _ in range(steps):
            actor.step(self.maze, dt, self.maze.can_player_enter)

    def test_reaches_exact_tile_centers_not_approximations(self):
        actor = MovingActor(3, 5, speed=8.0)
        actor.direction = Direction.LEFT
        self._run_for(actor, 2.0 / 8.0)  # exactly 2 tiles at speed 8
        self.assertAlmostEqual(actor.x, 1.0, places=6)
        self.assertAlmostEqual(actor.y, 5.0, places=6)
        self.assertTrue(actor.is_centered())

    def test_queued_turn_is_honored_exactly_at_the_junction(self):
        actor = MovingActor(3, 5, speed=8.0)
        actor.direction = Direction.LEFT
        actor.queue_direction(Direction.UP)
        # Run long enough to travel from col 3 to col 1 (junction) and
        # partway up, at a frame rate that does not evenly divide 1 tile
        # (the original bug only showed up under exactly this condition).
        self._run_for(actor, 0.4)
        self.assertEqual(actor.direction, Direction.UP)
        self.assertLess(actor.y, 5.0)
        self.assertAlmostEqual(actor.x, 1.0, places=6)

    def test_stops_at_a_dead_end_instead_of_phasing_through_walls(self):
        actor = MovingActor(1, 5, speed=8.0)
        actor.direction = Direction.LEFT  # column 0 is a wall here
        self._run_for(actor, 2.0)
        self.assertEqual(actor.direction, Direction.NONE)
        self.assertGreaterEqual(actor.x, 1.0)

    def test_movement_at_a_frame_rate_that_does_not_divide_evenly(self):
        # 37 fps deliberately does not divide 1.0 tile evenly at speed 8.
        actor = MovingActor(5, 3, speed=8.0)
        actor.direction = Direction.LEFT
        actor.queue_direction(Direction.NONE)
        dt = 1.0 / 37.0
        for _ in range(500):
            actor.step(self.maze, dt, self.maze.can_player_enter)
        # Column 1 is open floor bounded by walls at col 2/4 in adjacent
        # rows, but row 3 is the open corridor, so Scotty should coast
        # all the way to the left wall and stop there cleanly.
        self.assertAlmostEqual(actor.x, 1.0, places=6)
        self.assertTrue(actor.is_centered())


class TunnelWrapTests(unittest.TestCase):
    def test_wraps_around_at_tunnel_edges(self):
        maze = Maze(_TUNNEL, name="tunnel-test")
        actor = MovingActor(1, 1, speed=8.0)
        actor.direction = Direction.LEFT
        dt = 1 / 60.0
        for _ in range(400):
            actor.step(maze, dt, maze.can_player_enter)
            if actor.x > maze.cols - 3:
                break
        self.assertGreater(actor.x, 3.0)  # wrapped to the right-hand side


class ScottyTests(unittest.TestCase):
    def test_facing_updates_only_on_real_movement(self):
        maze = Maze(_CORRIDOR, name="corridor-test")
        scotty = Scotty(3, 5, speed=8.0)
        self.assertEqual(scotty.facing, Direction.RIGHT)
        scotty.queue_direction(Direction.LEFT)
        scotty.update(maze, 1 / 60.0)
        self.assertEqual(scotty.facing, Direction.LEFT)


if __name__ == "__main__":
    unittest.main()
