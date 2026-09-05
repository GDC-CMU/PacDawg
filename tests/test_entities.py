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

_OPEN_BOX = [
    "#######",
    "#.....#",
    "#.....#",
    "#.....#",
    "#.....#",
    "#..P..#",
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


class ScottyCorneringTests(unittest.TestCase):
    """The documented arcade pre-turn/cornering input model (see
    ``pacman-reference.md`` sec. 7): turns are re-evaluated every frame
    against Scotty's *current* tile and take effect immediately, never
    waiting for the exact tile center -- unlike ghosts, which only ever
    turn at centers (see GhostVsScottyTurningTests below).
    """

    def setUp(self):
        self.maze = Maze(_OPEN_BOX, name="open-box")
        self.dt = 1 / 60.0

    def test_turn_takes_effect_immediately_at_various_sub_tile_offsets(self):
        for frames_before_turn in (1, 3, 5, 7, 9):
            with self.subTest(frames_before_turn=frames_before_turn):
                scotty = Scotty(3, 5, speed=8.0)
                scotty.direction = Direction.LEFT
                scotty.queue_direction(Direction.LEFT)
                for _ in range(frames_before_turn):
                    scotty.update(self.maze, self.dt)
                self.assertFalse(
                    scotty.is_centered(), "test setup should land mid-tile, not on a center"
                )
                y_before = scotty.y
                scotty.queue_direction(Direction.UP)
                scotty.update(self.maze, self.dt)
                self.assertEqual(
                    scotty.direction,
                    Direction.UP,
                    f"turn queued mid-tile after {frames_before_turn} frames did not take "
                    "effect on the very next frame",
                )
                self.assertLess(scotty.y, y_before)  # actually moved up that same frame

    def test_180_degree_reversal_is_instant_regardless_of_position(self):
        scotty = Scotty(3, 5, speed=8.0)
        scotty.direction = Direction.LEFT
        scotty.queue_direction(Direction.LEFT)
        for _ in range(6):
            scotty.update(self.maze, self.dt)
        self.assertFalse(scotty.is_centered())
        x_before = scotty.x
        scotty.queue_direction(Direction.RIGHT)
        scotty.update(self.maze, self.dt)
        self.assertEqual(scotty.direction, Direction.RIGHT)
        self.assertGreater(scotty.x, x_before)  # already moving right, same frame

    def test_blocked_direction_latches_and_fires_once_a_gap_appears(self):
        # In _CORRIDOR, UP is walled off above columns 2-4 but open above
        # column 1: holding UP while walking left should do nothing until
        # Scotty reaches column 1, then fire immediately -- a one-slot
        # latch, not a timed buffer.
        maze = Maze(_CORRIDOR, name="corridor-test")
        scotty = Scotty(3, 5, speed=8.0)
        scotty.direction = Direction.LEFT
        scotty.queue_direction(Direction.UP)
        turned_early = False
        for _ in range(40):
            scotty.update(maze, self.dt)
            if scotty.direction is Direction.UP and scotty.x > 1.5:
                turned_early = True
        self.assertFalse(turned_early)
        self.assertEqual(scotty.direction, Direction.UP)
        self.assertLess(scotty.y, 5.0)

    def test_cornering_moves_both_axes_in_the_same_frame(self):
        # The documented 45-degree corner cut: mid-turn, both the axis of
        # travel and the perpendicular (drifting toward its centerline)
        # axis change within a single frame.
        scotty = Scotty(3, 5, speed=8.0)
        scotty.direction = Direction.LEFT
        scotty.queue_direction(Direction.LEFT)
        for _ in range(8):
            scotty.update(self.maze, self.dt)
        x_before, y_before = scotty.x, scotty.y
        scotty.queue_direction(Direction.UP)
        scotty.update(self.maze, self.dt)
        self.assertNotEqual(scotty.x, x_before)
        self.assertNotEqual(scotty.y, y_before)


class GhostVsScottyTurningTests(unittest.TestCase):
    """Ghosts must NOT get the pre-turn/cornering treatment: they may
    only change direction exactly on a tile center."""

    def test_ghost_does_not_turn_mid_tile_where_scotty_would(self):
        from pacdawg.ghosts import Ghost

        maze = Maze(_OPEN_BOX, name="open-box")
        dt = 1 / 60.0
        ghost = Ghost("gates", (3, 5), (1, 1), normal_speed=8.0)
        ghost.direction = Direction.LEFT
        ghost.queue_direction(Direction.LEFT)
        for _ in range(6):
            ghost.step(maze, dt, maze.can_ghost_enter)
        self.assertFalse(ghost.is_centered(), "test setup should land the ghost mid-tile")

        ghost.queue_direction(Direction.UP)
        ghost.step(maze, dt, maze.can_ghost_enter)
        # Unlike Scotty, the ghost keeps going in its old direction until
        # it actually reaches a tile center.
        self.assertEqual(ghost.direction, Direction.LEFT)

    def test_ghost_does_turn_once_it_reaches_the_center(self):
        from pacdawg.ghosts import Ghost

        maze = Maze(_OPEN_BOX, name="open-box")
        dt = 1 / 60.0
        ghost = Ghost("gates", (3, 5), (1, 1), normal_speed=8.0)
        ghost.direction = Direction.LEFT
        ghost.queue_direction(Direction.LEFT)
        ghost.queue_direction(Direction.UP)
        for _ in range(60):
            ghost.step(maze, dt, maze.can_ghost_enter)
            if ghost.direction is Direction.UP:
                break
        self.assertEqual(ghost.direction, Direction.UP)


if __name__ == "__main__":
    unittest.main()
