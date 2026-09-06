"""The real level/life flow must use the beginner-to-hard difficulty curve."""
from __future__ import annotations

import random
import unittest
from unittest.mock import patch

from pacdawg import config, levels
from pacdawg.game import Game, GameState
from pacdawg.ghosts import GhostMode
from pacdawg.input import RawInput


class DifficultyCurveTests(unittest.TestCase):
    def test_first_maze_has_a_large_escape_margin_and_long_power_window(self):
        self.assertLessEqual(levels.ghost_normal_speed(1), 0.65 * levels.pacman_normal_speed(1))
        self.assertLess(levels.elroy2_speed(1), levels.pacman_normal_speed(1))
        self.assertGreaterEqual(levels.frightened_seconds_for_level(1), 10.0)
        self.assertGreater(levels.personal_dot_limit(1, "hunt", 244), 0)

    def test_every_cleared_level_increases_relative_ghost_pressure(self):
        cap = len(config.DIFFICULTY_BY_LEVEL)
        for level in range(1, cap):
            with self.subTest(level=level):
                a, b = levels.difficulty_for_level(level), levels.difficulty_for_level(level + 1)
                self.assertLess(a.ghost_pct / a.player_pct, b.ghost_pct / b.player_pct)
                self.assertLess(levels.ghost_normal_speed(level), levels.ghost_normal_speed(level + 1))
                self.assertGreater(a.frightened_seconds, b.frightened_seconds)
                self.assertGreater(a.release_timeout, b.release_timeout)
                self.assertTrue(all(old >= new for old, new in zip(a.house_dot_limits, b.house_dot_limits)))

    def test_difficulty_stays_bounded_when_layouts_loop(self):
        cap = len(config.DIFFICULTY_BY_LEVEL)
        self.assertEqual(levels.difficulty_for_level(10000), levels.difficulty_for_level(cap))
        self.assertEqual(levels.difficulty_for_level(0), levels.difficulty_for_level(1))
        self.assertGreater(levels.frightened_seconds_for_level(10000), 0)

    def test_frightened_and_tunnel_ghosts_remain_slower_at_every_tier(self):
        for level in range(1, 12):
            with self.subTest(level=level):
                speed = levels.ghost_normal_speed(level)
                self.assertLess(levels.ghost_frightened_speed(level), speed)
                self.assertLess(levels.ghost_tunnel_speed(level), speed)
                self.assertGreater(levels.eyes_speed(level), speed)


class DifficultyFlowTests(unittest.TestCase):
    def setUp(self):
        saving = patch("pacdawg.score.save_high_score")
        self.save = saving.start()
        self.addCleanup(saving.stop)
        self.game = Game(rng=random.Random(28))
        self.game.new_game()

    def test_actual_level_clear_advances_actor_speeds_and_power_duration(self):
        for current in range(1, 12):
            self.assertEqual(self.game.score.level, current)
            self.assertEqual(self.game.player.speed, levels.pacman_normal_speed(current))
            for ghost in self.game.ghosts.values():
                self.assertEqual(ghost.base_speed, levels.ghost_normal_speed(current))
                self.assertEqual(ghost.frightened_speed, levels.ghost_frightened_speed(current))
            self.game.update(2.1, RawInput())
            self.assertIs(self.game.state, GameState.PLAYING)
            self.game.maze.pellets.clear()
            self.game.maze.power_pellets.clear()
            self.game.update(1 / 60, RawInput())
            self.assertIs(self.game.state, GameState.LEVEL_CLEAR)
            self.game.update(2.1, RawInput())
            self.assertIs(self.game.state, GameState.READY)
            self.assertEqual(self.game.score.level, current + 1)

    def test_power_pellet_uses_the_current_tier(self):
        for current in (1, 2, 5, 10):
            self.game.score.level = current
            self.game._start_level(current)
            for ghost in self.game.ghosts.values():
                ghost.mode = GhostMode.CHASE
            self.game.maze.pellets.discard(self.game.player.tile)
            self.game.maze.power_pellets.add(self.game.player.tile)
            self.game._handle_pellets()
            for ghost in self.game.ghosts.values():
                self.assertIs(ghost.mode, GhostMode.FRIGHTENED)
                self.assertEqual(ghost.frightened_seconds_left, levels.frightened_seconds_for_level(current))

    def test_life_loss_preserves_tier_and_a_new_run_returns_to_easy(self):
        self.game.score.level = 6
        self.game._start_level(6)
        self.game._reset_positions_same_level()
        self.assertEqual(self.game.score.level, 6)
        self.assertEqual(self.game.player.speed, levels.pacman_normal_speed(6))
        for ghost in self.game.ghosts.values():
            self.assertEqual(ghost.base_speed, levels.ghost_normal_speed(6))
        threshold = levels.global_dot_counter_threshold("hunt", self.game.maze.total_pellets, level=6)
        self.game._global_dot_counter = threshold
        self.game._release_ghosts_if_due()
        self.assertTrue(self.game.ghosts["hunt"].released)
        self.game.new_game()
        self.assertEqual(self.game.score.level, 1)
        self.assertEqual(self.game.player.speed, levels.pacman_normal_speed(1))


if __name__ == "__main__":
    unittest.main()
