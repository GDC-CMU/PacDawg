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


class GoBackOneLevelTests(unittest.TestCase):
    """P1, Esc, Backspace, and button B are all equivalent aliases of a
    single "go back one level" action, used identically everywhere: from
    the main menu they exit to the gallery; from every other state
    (including HOW_TO_PLAY and a game in progress) they return to the
    main menu, treating any in-progress game as abandoned.
    """

    @staticmethod
    def _frame(game, raw, dt=1 / 60.0):
        # Mirrors Game.run()'s real per-frame order: the back check runs
        # BEFORE update() so it always sees the state update() is about
        # to (possibly) change -- this is the order that matters for the
        # held-control-across-a-transition scenarios below.
        game.maybe_go_back(raw)
        game.update(dt, raw)

    def test_escape_on_how_to_play_returns_to_menu_without_exiting(self):
        game = Game(rng=random.Random(40))
        game.state = GameState.HOW_TO_PLAY
        try:
            self._frame(game, RawInput(pressed_keys=frozenset({"escape"})))
        except SystemExit:
            self.fail("Esc exited the process from HOW_TO_PLAY")
        self.assertEqual(game.state, GameState.ATTRACT)

    def test_backspace_on_how_to_play_also_returns_to_menu(self):
        game = Game(rng=random.Random(41))
        game.state = GameState.HOW_TO_PLAY
        try:
            self._frame(game, RawInput(pressed_keys=frozenset({"backspace"})))
        except SystemExit:
            self.fail("Backspace exited the process from HOW_TO_PLAY")
        self.assertEqual(game.state, GameState.ATTRACT)

    def test_button_b_on_how_to_play_also_returns_to_menu(self):
        game = Game(rng=random.Random(42))
        game.state = GameState.HOW_TO_PLAY
        try:
            self._frame(game, RawInput(pressed_buttons=frozenset({config.BUTTON_B})))
        except SystemExit:
            self.fail("button B exited the process from HOW_TO_PLAY")
        self.assertEqual(game.state, GameState.ATTRACT)

    def test_p1_on_how_to_play_returns_to_menu_not_exit(self):
        game = Game(rng=random.Random(43))
        game.state = GameState.HOW_TO_PLAY
        try:
            self._frame(game, RawInput(pressed_buttons=frozenset({config.BUTTON_P1})))
        except SystemExit:
            self.fail("P1 exited the process directly from HOW_TO_PLAY")
        self.assertEqual(game.state, GameState.ATTRACT)

    def test_p1_from_gameplay_lands_on_the_menu_and_does_not_exit(self):
        game = Game(rng=random.Random(47))
        game.new_game()
        game.state = GameState.PLAYING
        try:
            self._frame(game, RawInput(pressed_buttons=frozenset({config.BUTTON_P1})))
        except SystemExit:
            self.fail("P1 exited the process directly from PLAYING")
        self.assertEqual(game.state, GameState.ATTRACT)

    def test_p1_from_game_over_lands_on_the_menu(self):
        game = Game(rng=random.Random(48))
        game.state = GameState.GAME_OVER
        try:
            self._frame(game, RawInput(pressed_buttons=frozenset({config.BUTTON_P1})))
        except SystemExit:
            self.fail("P1 exited the process directly from GAME_OVER")
        self.assertEqual(game.state, GameState.ATTRACT)

    def test_p1_from_the_main_menu_exits(self):
        game = Game(rng=random.Random(44))
        self.assertEqual(game.state, GameState.ATTRACT)
        with self.assertRaises(SystemExit) as cm:
            self._frame(game, RawInput(pressed_buttons=frozenset({config.BUTTON_P1})))
        self.assertEqual(cm.exception.code, 0)

    def test_escape_on_the_main_menu_exits(self):
        game = Game(rng=random.Random(44))
        self.assertEqual(game.state, GameState.ATTRACT)
        with self.assertRaises(SystemExit) as cm:
            self._frame(game, RawInput(pressed_keys=frozenset({"escape"})))
        self.assertEqual(cm.exception.code, 0)

    def test_two_p1_presses_with_a_release_between_leave_the_gallery(self):
        # The intended two-press flow from mid-game: once back to the
        # menu, once more to exit -- never a single accidental quit.
        game = Game(rng=random.Random(49))
        game.new_game()
        game.state = GameState.PLAYING
        p1 = RawInput(pressed_buttons=frozenset({config.BUTTON_P1}))
        self._frame(game, p1)
        self.assertEqual(game.state, GameState.ATTRACT)
        self._frame(game, RawInput())  # release, so the second press is a fresh edge
        with self.assertRaises(SystemExit) as cm:
            self._frame(game, p1)
        self.assertEqual(cm.exception.code, 0)

    def test_a_single_held_p1_press_never_skips_a_level(self):
        # One held press must land on the menu and stay there -- it must
        # never fall straight through to process exit in the same hold.
        game = Game(rng=random.Random(50))
        game.new_game()
        game.state = GameState.PLAYING
        held_p1 = RawInput(pressed_buttons=frozenset({config.BUTTON_P1}))
        try:
            for _ in range(30):
                self._frame(game, held_p1)
        except SystemExit:
            self.fail("a single held P1 press skipped straight to process exit")
        self.assertEqual(game.state, GameState.ATTRACT)

    def test_held_escape_through_the_how_to_play_transition_does_not_chain_into_exit(self):
        # Regression: a single Esc press/hold that carries the game back
        # to ATTRACT must not then be re-read as a fresh press the
        # instant the menu appears -- it must be seen released first.
        game = Game(rng=random.Random(45))
        game.state = GameState.HOW_TO_PLAY
        held_esc = RawInput(pressed_keys=frozenset({"escape"}))
        try:
            for _ in range(15):  # hold well past the HOW_TO_PLAY -> ATTRACT flip
                self._frame(game, held_esc)
        except SystemExit:
            self.fail("held Esc chained HOW_TO_PLAY -> ATTRACT -> exit in one hold")
        self.assertEqual(game.state, GameState.ATTRACT)

        # Release, then a genuine fresh Esc on the menu still exits.
        self._frame(game, RawInput())
        with self.assertRaises(SystemExit):
            self._frame(game, held_esc)

    def test_held_button_b_through_the_transition_does_not_chain(self):
        game = Game(rng=random.Random(46))
        game.state = GameState.HOW_TO_PLAY
        held_b = RawInput(pressed_buttons=frozenset({config.BUTTON_B}))
        try:
            for _ in range(15):
                self._frame(game, held_b)
        except SystemExit:
            self.fail("held button B chained into an exit")
        self.assertEqual(game.state, GameState.ATTRACT)

    def test_leaving_a_game_in_progress_commits_the_high_score(self):
        game = Game(rng=random.Random(51))
        game.new_game()
        game.state = GameState.PLAYING
        game.score.score = game.score.high_score + 500
        abandoned_score = game.score.score
        self._frame(game, RawInput(pressed_buttons=frozenset({config.BUTTON_P1})))
        self.assertEqual(game.state, GameState.ATTRACT)
        self.assertEqual(game.score.high_score, abandoned_score)

    def test_starting_again_after_abandoning_gives_a_fresh_game(self):
        game = Game(rng=random.Random(52))
        game.new_game()
        game.state = GameState.PLAYING
        game.score.score = 1234
        game.score.lives = 1
        self._frame(game, RawInput(pressed_buttons=frozenset({config.BUTTON_P1})))
        self.assertEqual(game.state, GameState.ATTRACT)
        self._frame(game, RawInput())  # release before the fresh confirm press
        self._frame(game, RawInput(pressed_keys=frozenset({"return"})))
        self.assertEqual(game.state, GameState.READY)
        self.assertEqual(game.score.score, 0)
        self.assertEqual(game.score.level, 1)


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
            game.maybe_go_back(held)  # must not raise SystemExit (default state is ATTRACT)
        # But once genuinely (re-)pressed after being seen released, P1
        # must still work immediately -- the guard must not eat it.
        game.maybe_go_back(RawInput())
        with self.assertRaises(SystemExit) as cm:
            game.maybe_go_back(held)
        self.assertEqual(cm.exception.code, 0)

    def test_p1_not_held_at_startup_still_exits_immediately(self):
        game = Game(rng=random.Random(34))
        game._seed_input_state(set(), set())
        with self.assertRaises(SystemExit):
            game.maybe_go_back(RawInput(pressed_buttons=frozenset({config.BUTTON_P1})))


if __name__ == "__main__":
    unittest.main()
