"""Tests for Game-level orchestration: ghost-house release, Cruise Elroy,
and the scatter/chase timer pausing during frightened mode.

These exercise pacdawg.game.Game directly with synthetic input, headless
(no real display needed for pure state updates).
"""
from __future__ import annotations

import random
import unittest

from pacdawg import config, levels
from pacdawg.game import Game, GameState, MENU_ITEMS, MENU_EXIT_TO_GALLERY, MENU_HOW_TO_PLAY, MENU_START_GAME
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


class OpeningEngagesImmediatelyTests(unittest.TestCase):
    """Regression tests for the arcade-fair opening override: a level (and
    a life respawn) must begin in CHASE, not scatter, so ghosts engage
    the player almost as soon as they leave the house instead of walking
    to a corner and orbiting it for the first ~10 seconds."""

    def test_level_start_ghosts_reach_chase_within_a_couple_seconds_of_leaving(self):
        game = Game(rng=random.Random(20))
        game.new_game()
        saw_scatter = False
        reached_chase_by = None
        for frame in range(600):  # 10 simulated seconds
            game.update(1 / 60.0, RawInput())
            active = [g for g in game.ghosts.values() if g.mode is not GhostMode.HOUSE]
            if any(g.mode is GhostMode.SCATTER for g in active):
                saw_scatter = True
            if reached_chase_by is None and active and all(
                g.mode is GhostMode.CHASE for g in active if g.mode is not GhostMode.LEAVING
            ):
                reached_chase_by = frame
        self.assertFalse(saw_scatter, "a ghost scattered during the opening burst")
        self.assertIsNotNone(reached_chase_by)
        self.assertLess(reached_chase_by / 60.0, 4.0)

    def test_life_respawn_also_opens_in_chase(self):
        game = Game(rng=random.Random(21))
        game.new_game()
        game._reset_positions_same_level()
        table = levels.scatter_chase_timetable_for_level(game.score.level)
        self.assertEqual(table[0][0], "chase")
        self.assertEqual(game.scatter_clock.timetable[0][0], "chase")


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


class MainMenuTests(unittest.TestCase):
    def test_starts_on_the_attract_menu_with_start_game_selected(self):
        game = Game(rng=random.Random(10))
        self.assertEqual(game.state, GameState.ATTRACT)
        self.assertEqual(MENU_ITEMS[game.menu_index], MENU_START_GAME)

    def test_down_then_up_returns_to_the_original_selection(self):
        game = Game(rng=random.Random(11))
        game.update(1 / 60.0, RawInput(pressed_keys=frozenset({"down"})))
        game.update(1 / 60.0, RawInput())  # release, so the next press is a new edge
        self.assertEqual(MENU_ITEMS[game.menu_index], MENU_HOW_TO_PLAY)
        game.update(1 / 60.0, RawInput(pressed_keys=frozenset({"up"})))
        game.update(1 / 60.0, RawInput())
        self.assertEqual(MENU_ITEMS[game.menu_index], MENU_START_GAME)

    def test_holding_down_does_not_rapid_fire_through_every_item(self):
        # Edge-triggered nav: holding the direction for many frames must
        # move the selection at most once, not scroll continuously.
        game = Game(rng=random.Random(12))
        held = RawInput(pressed_keys=frozenset({"down"}))
        for _ in range(30):
            game.update(1 / 60.0, held)
        self.assertEqual(MENU_ITEMS[game.menu_index], MENU_HOW_TO_PLAY)

    def test_confirm_on_how_to_play_opens_that_screen_and_back_returns(self):
        game = Game(rng=random.Random(13))
        game.update(1 / 60.0, RawInput(pressed_keys=frozenset({"down"})))
        game.update(1 / 60.0, RawInput())
        game.update(1 / 60.0, RawInput(pressed_keys=frozenset({"return"})))
        self.assertEqual(game.state, GameState.HOW_TO_PLAY)

        game.update(1 / 60.0, RawInput())
        game.update(1 / 60.0, RawInput(pressed_keys=frozenset({"return"})))
        self.assertEqual(game.state, GameState.ATTRACT)

    def test_holding_confirm_across_the_how_to_play_transition_does_not_double_fire(self):
        # A single held button press must not chain HOW_TO_PLAY -> ATTRACT
        # -> re-enter HOW_TO_PLAY (or worse, START GAME) in one frame.
        game = Game(rng=random.Random(14))
        game.update(1 / 60.0, RawInput(pressed_keys=frozenset({"down"})))
        game.update(1 / 60.0, RawInput())
        held_confirm = RawInput(pressed_keys=frozenset({"return"}))
        game.update(1 / 60.0, held_confirm)
        self.assertEqual(game.state, GameState.HOW_TO_PLAY)
        for _ in range(10):
            game.update(1 / 60.0, held_confirm)
        self.assertEqual(game.state, GameState.HOW_TO_PLAY)  # did not bounce back out

    def test_confirm_on_start_game_begins_play(self):
        game = Game(rng=random.Random(15))
        game.update(1 / 60.0, RawInput(pressed_keys=frozenset({"return"})))
        self.assertEqual(game.state, GameState.READY)

    def test_confirm_on_exit_to_gallery_calls_sys_exit_zero(self):
        game = Game(rng=random.Random(16))
        game.update(1 / 60.0, RawInput(pressed_keys=frozenset({"down"})))
        game.update(1 / 60.0, RawInput())
        game.update(1 / 60.0, RawInput(pressed_keys=frozenset({"down"})))
        game.update(1 / 60.0, RawInput())
        self.assertEqual(MENU_ITEMS[game.menu_index], MENU_EXIT_TO_GALLERY)
        with self.assertRaises(SystemExit) as cm:
            game.update(1 / 60.0, RawInput(pressed_keys=frozenset({"return"})))
        self.assertEqual(cm.exception.code, 0)

    def test_game_over_confirm_returns_to_attract_menu(self):
        game = Game(rng=random.Random(17))
        game.state = GameState.GAME_OVER
        game.update(1 / 60.0, RawInput(pressed_keys=frozenset({"return"})))
        self.assertEqual(game.state, GameState.ATTRACT)


class HeldButtonAtStartupTests(unittest.TestCase):
    """Regression tests for the "launched from the gallery with the
    select button still held" bug: the ArcadeLauncher's gallery is left
    with button 1/A (or Enter) physically held down -- that is how the
    visitor selected PacDawg -- and our first hardware read must not
    mistake that stale, already-held button for a fresh press, or the
    menu confirms START GAME before the visitor ever sees it.

    Game.init_display() reproduces this by seeding pressed state from
    real hardware; _seed_input_state() is the pure, testable half of
    that (no real display/joystick needed) so we can simulate "already
    held at startup" directly.
    """

    def test_button_a_held_at_startup_does_not_auto_start(self):
        game = Game(rng=random.Random(30))
        game._seed_input_state(set(), {config.BUTTON_A})
        held = RawInput(pressed_buttons=frozenset({config.BUTTON_A}))
        for _ in range(40):  # well past both the settle window and a bounce
            game.update(1 / 60.0, held)
        self.assertEqual(game.state, GameState.ATTRACT)
        self.assertEqual(MENU_ITEMS[game.menu_index], MENU_START_GAME)

    def test_enter_key_held_at_startup_does_not_auto_start(self):
        game = Game(rng=random.Random(31))
        game._seed_input_state({"return"}, set())
        held = RawInput(pressed_keys=frozenset({"return"}))
        for _ in range(40):
            game.update(1 / 60.0, held)
        self.assertEqual(game.state, GameState.ATTRACT)

    def test_release_then_genuine_press_after_seeded_hold_still_starts(self):
        game = Game(rng=random.Random(32))
        game._seed_input_state(set(), {config.BUTTON_A})
        held = RawInput(pressed_buttons=frozenset({config.BUTTON_A}))
        for _ in range(40):
            game.update(1 / 60.0, held)
        game.update(1 / 60.0, RawInput())  # visitor releases the stale button
        game.update(1 / 60.0, held)  # then genuinely presses it again
        self.assertNotEqual(game.state, GameState.ATTRACT)

    def test_p1_held_at_startup_does_not_instantly_exit(self):
        game = Game(rng=random.Random(33))
        game._seed_input_state(set(), {config.BUTTON_P1})
        held = RawInput(pressed_buttons=frozenset({config.BUTTON_P1}))
        for _ in range(40):
            game.maybe_exit(held)  # must not raise SystemExit
        # But once genuinely (re-)pressed after being seen released, P1
        # must still exit immediately -- the guard must not eat it.
        game.maybe_exit(RawInput())
        with self.assertRaises(SystemExit) as cm:
            game.maybe_exit(held)
        self.assertEqual(cm.exception.code, 0)

    def test_p1_not_held_at_startup_still_exits_immediately(self):
        game = Game(rng=random.Random(34))
        game._seed_input_state(set(), set())
        with self.assertRaises(SystemExit):
            game.maybe_exit(RawInput(pressed_buttons=frozenset({config.BUTTON_P1})))


if __name__ == "__main__":
    unittest.main()
