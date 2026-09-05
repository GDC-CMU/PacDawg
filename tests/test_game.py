"""Tests for Game-level orchestration: ghost-house release, Cruise Elroy,
and the scatter/chase timer pausing during frightened mode.

These exercise pacdawg.game.Game directly with synthetic input, headless
(no real display needed for pure state updates).
"""
from __future__ import annotations

import random
import unittest

from pacdawg import levels
from pacdawg.game import Game, GameState
from pacdawg.ghosts import GhostMode
from pacdawg.input import RawInput


def _run_frames(game: Game, n: int, raw: RawInput = None) -> None:
    raw = raw or RawInput()
    for _ in range(n):
        game.update(1 / 60.0, raw)


class GhostHouseReleaseTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(rng=random.Random(0))
        self.game.new_game()
        # Skip the READY pause so PLAYING logic (release counters) runs.
        _run_frames(self.game, 130)
        self.assertEqual(self.game.state, GameState.PLAYING)

    def test_gates_releases_immediately_never_subject_to_house_logic(self):
        # Gates/Blinky is documented to never be subject to house-release
        # logic at all; it should already be out (or leaving) right away.
        gates = self.game.ghosts["gates"]
        self.assertNotEqual(gates.mode, GhostMode.HOUSE)

    def test_hunt_has_zero_limit_and_leaves_almost_immediately(self):
        # Hunt/Pinky's personal dot limit is 0 at every level: it should
        # release within the first few frames of PLAYING, with zero dots
        # eaten.
        hunt = self.game.ghosts["hunt"]
        self.assertIn(hunt.mode, (GhostMode.LEAVING, GhostMode.CHASE, GhostMode.SCATTER))

    def test_personal_counter_releases_wean_after_enough_pellets(self):
        wean = self.game.ghosts["wean"]
        self.assertEqual(wean.mode, GhostMode.HOUSE)  # not yet -- needs pellets
        limit = levels.personal_dot_limit(1, "wean", self.game.maze.total_pellets)
        for _ in range(limit):
            self.game._on_dot_eaten()
            self.game._release_ghosts_if_due()
        self.assertNotEqual(wean.mode, GhostMode.HOUSE)

    def test_anti_starvation_timer_releases_a_ghost_without_any_pellets(self):
        doherty = self.game.ghosts["doherty"]
        self.assertEqual(doherty.mode, GhostMode.HOUSE)
        timeout = levels.ghost_release_timeout_seconds(self.game.score.level)
        _run_frames(self.game, int(timeout * 60) + 120)
        # Hunt and Wean should be out (zero/low limits); the anti-starvation
        # timer should also have forced further releases without any
        # pellets ever being eaten.
        self.assertNotEqual(self.game.ghosts["hunt"].mode, GhostMode.HOUSE)


class GlobalDotCounterTests(unittest.TestCase):
    def test_life_lost_switches_to_global_counter_mode(self):
        game = Game(rng=random.Random(1))
        game.new_game()
        self.assertEqual(game.dot_counter_mode, "personal")
        game._reset_positions_same_level()
        self.assertEqual(game.dot_counter_mode, "global")

    def test_global_counter_releases_hunt_wean_doherty_in_order(self):
        game = Game(rng=random.Random(2))
        game.new_game()
        game._reset_positions_same_level()
        total = game.maze.total_pellets
        hunt_at = levels.global_dot_counter_threshold("hunt", total)
        wean_at = levels.global_dot_counter_threshold("wean", total)
        doherty_at = levels.global_dot_counter_threshold("doherty", total)

        for _ in range(hunt_at):
            game._on_dot_eaten()
        game._release_ghosts_if_due()
        self.assertNotEqual(game.ghosts["hunt"].mode, GhostMode.HOUSE)
        self.assertEqual(game.ghosts["wean"].mode, GhostMode.HOUSE)

        for _ in range(wean_at - hunt_at):
            game._on_dot_eaten()
        game._release_ghosts_if_due()
        self.assertNotEqual(game.ghosts["wean"].mode, GhostMode.HOUSE)
        self.assertEqual(game.ghosts["doherty"].mode, GhostMode.HOUSE)

        for _ in range(doherty_at - wean_at):
            game._on_dot_eaten()
        game._release_ghosts_if_due()
        self.assertNotEqual(game.ghosts["doherty"].mode, GhostMode.HOUSE)
        self.assertEqual(game.dot_counter_mode, "personal")  # deactivated


class CruiseElroyTests(unittest.TestCase):
    def test_gates_speeds_up_as_pellets_run_low(self):
        game = Game(rng=random.Random(3))
        game.new_game()
        _run_frames(game, 130)
        gates = game.ghosts["gates"]
        self.assertEqual(gates.elroy_stage, 0)

        stage1, stage2 = levels.elroy_thresholds_for_level(1, game.maze.total_pellets)
        # Eat pellets down to at or below the stage-2 threshold.
        while game.maze.pellets_remaining > stage2:
            if game.maze.pellets:
                game.maze.pellets.pop()
            elif game.maze.power_pellets:
                game.maze.power_pellets.pop()
            else:
                break
        game._update_cruise_elroy()
        self.assertEqual(gates.elroy_stage, 2)

    def test_elroy_locked_after_life_lost_until_doherty_releases(self):
        game = Game(rng=random.Random(4))
        game.new_game()
        _run_frames(game, 130)
        game._reset_positions_same_level()
        self.assertFalse(game.elroy_unlocked)
        game.ghosts["doherty"].released = False
        game._update_cruise_elroy()
        self.assertFalse(game.elroy_unlocked)
        game.ghosts["doherty"].released = True
        game._update_cruise_elroy()
        self.assertTrue(game.elroy_unlocked)


class ScatterChasePauseTests(unittest.TestCase):
    def test_scatter_chase_timer_pauses_while_any_ghost_is_frightened(self):
        game = Game(rng=random.Random(5))
        game.new_game()
        _run_frames(game, 130)
        elapsed_before = game.scatter_clock.elapsed
        index_before = game.scatter_clock.index

        for ghost in game.ghosts.values():
            ghost.mode = GhostMode.CHASE  # ensure frighten() can take hold
        list(game.ghosts.values())[0].frighten(10.0, 5)

        _run_frames(game, 30)
        self.assertEqual(game.scatter_clock.elapsed, elapsed_before)
        self.assertEqual(game.scatter_clock.index, index_before)

    def test_scatter_chase_timer_resumes_once_frightened_ends(self):
        game = Game(rng=random.Random(6))
        game.new_game()
        _run_frames(game, 130)
        for ghost in game.ghosts.values():
            ghost.mode = GhostMode.CHASE
        list(game.ghosts.values())[0].frighten(0.05, 0)
        _run_frames(game, 10)  # frightened window ends partway through
        self.assertGreater(game.scatter_clock.elapsed, 0.0)


if __name__ == "__main__":
    unittest.main()
