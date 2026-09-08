"""Tests for the hard arcade-cabinet contract with ArcadeLauncher.

- The display must be exactly 800x600.
- P1 (button 5), Esc, Backspace, and button B are all aliases of a
  single "go back one level" action, per this club's cross-game arcade
  contract: from the main menu it exits via ``sys.exit(0)``; from every
  help/result/demo state it returns to the main menu. Active runs pause/resume.
- The game must survive hundreds of simulated frames without crashing,
  including full runs through every input direction and state.
"""
from __future__ import annotations

import os
import random
import unittest
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

from pacdawg import config  # noqa: E402
from pacdawg.entities import Direction  # noqa: E402
from pacdawg.game import ACTIVE_STATES, Game, GameState  # noqa: E402
from pacdawg.input import RawInput  # noqa: E402


class DisplayContractTests(unittest.TestCase):
    def test_configured_resolution_is_800x600(self):
        self.assertEqual(config.SCREEN_WIDTH, 800)
        self.assertEqual(config.SCREEN_HEIGHT, 600)

    def test_display_surface_matches_configured_resolution(self):
        pygame.init()
        screen = pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
        self.assertEqual(screen.get_size(), (800, 600))

    def test_default_display_retains_scaled_fullscreen_and_windowed_alias(self):
        for windowed in (False, True):
            game = Game()
            with patch("pacdawg.config.windowed_requested", return_value=windowed), \
                 patch("pygame.display.set_mode", return_value=pygame.Surface((800, 600))) as mode, \
                 patch("pygame.joystick.get_count", return_value=0), \
                 patch.object(game, "_seed_input_state_from_hardware"):
                game.init_display()
            expected = pygame.SCALED | (0 if windowed else pygame.FULLSCREEN)
            mode.assert_called_once_with((800, 600), expected)


class BackOneLevelContractTests(unittest.TestCase):
    """Back exits only at the root; abandoning a run is a deliberate choice."""

    def test_p1_from_the_main_menu_exits_with_code_zero(self):
        game = Game(rng=random.Random(0))
        self.assertEqual(game.state, GameState.ATTRACT)
        raw = RawInput(pressed_buttons=frozenset({config.BUTTON_P1}))
        with self.assertRaises(SystemExit) as cm:
            game.maybe_go_back(raw)
        self.assertEqual(cm.exception.code, 0)

    def test_p1_from_every_other_state_never_exits(self):
        raw = RawInput(pressed_buttons=frozenset({config.BUTTON_P1}))
        for state in GameState:
            if state is GameState.ATTRACT:
                continue
            with self.subTest(state=state):
                game = Game(rng=random.Random(0))
                game.new_game()
                if state is GameState.DEMO:
                    game._enter_demo()
                elif state is GameState.PAUSED:
                    game._pause_game()
                else:
                    game.state = state
                try:
                    game.maybe_go_back(raw)
                except SystemExit:
                    self.fail(f"P1 exited the process directly from {state}")
                expected = (GameState.PAUSED if state in ACTIVE_STATES else
                            GameState.READY if state is GameState.PAUSED else GameState.ATTRACT)
                self.assertEqual(game.state, expected)

    def test_escape_key_mirrors_p1_exactly(self):
        raw = RawInput(pressed_keys=frozenset({"escape"}))
        game = Game(rng=random.Random(0))
        with self.assertRaises(SystemExit) as cm:
            game.maybe_go_back(raw)
        self.assertEqual(cm.exception.code, 0)

        game2 = Game(rng=random.Random(0))
        game2.new_game()
        game2.state = GameState.PLAYING
        try:
            game2.maybe_go_back(raw)
        except SystemExit:
            self.fail("Esc exited the process directly from PLAYING")
        self.assertEqual(game2.state, GameState.PAUSED)

    def test_no_go_back_without_a_back_input(self):
        game = Game(rng=random.Random(0))
        raw = RawInput(pressed_buttons=frozenset({config.BUTTON_A}))
        try:
            game.maybe_go_back(raw)
        except SystemExit:
            self.fail("maybe_go_back() exited without a back input present")
        self.assertEqual(game.state, GameState.ATTRACT)

    def test_either_button_5_from_a_second_stick_still_works(self):
        # Two identical DragonRise sticks are on the cabinet; button
        # indices are per-event, not per-device, so this is really just
        # confirming index 5 alone is sufficient regardless of source.
        game = Game(rng=random.Random(0))
        raw = RawInput(pressed_buttons=frozenset({config.BUTTON_P1}))
        with self.assertRaises(SystemExit):
            game.maybe_go_back(raw)

    def test_from_any_state_deliberate_menu_then_back_can_exit(self):
        press = RawInput(pressed_buttons=frozenset({config.BUTTON_P1}))
        release = RawInput()
        for state in GameState:
            with self.subTest(state=state):
                game = Game(rng=random.Random(0))
                game.new_game()
                if state is GameState.DEMO:
                    game._enter_demo()
                elif state is GameState.PAUSED:
                    game._pause_game()
                else:
                    game.state = state
                exited = False
                for _ in range(4):
                    try:
                        if game.state is GameState.PAUSED:
                            game.maybe_go_back(release)
                            game.update(0.0, release)
                            game.pause_index = 2  # Main Menu, after How to Play
                            game.update(0.0, RawInput(pressed_buttons=frozenset({config.BUTTON_START})))
                        else:
                            game.maybe_go_back(press)
                            game.update(0.0, press)
                    except SystemExit as exc:
                        self.assertEqual(exc.code, 0)
                        exited = True
                        break
                    game.maybe_go_back(release)
                self.assertTrue(exited, f"deliberate exit was unreachable from {state}")


class HeadlessStabilityTests(unittest.TestCase):
    def test_survives_several_hundred_frames_of_varied_input(self):
        game = Game(rng=random.Random(42))
        game.new_game()
        directions = ["up", "down", "left", "right", "w", "a", "s", "d"]
        for frame in range(600):
            key = directions[frame % len(directions)]
            raw = RawInput(pressed_keys=frozenset({key}))
            game.update(1 / 60.0, raw)  # must not raise
        self.assertIn(game.state, list(GameState))

    def test_survives_idle_input_through_multiple_state_transitions(self):
        game = Game(rng=random.Random(7))
        game.state = GameState.ATTRACT
        raw_confirm = RawInput(pressed_keys=frozenset({"return"}))
        raw_idle = RawInput()
        game.update(1 / 60.0, raw_confirm)  # ATTRACT -> READY
        self.assertEqual(game.state, GameState.READY)
        for _ in range(300):
            game.update(1 / 60.0, raw_idle)
        self.assertIn(game.state, (GameState.PLAYING, GameState.DYING, GameState.GAME_OVER))

    def test_render_frame_does_not_raise(self):
        from pacdawg import render

        pygame.init()
        screen = pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
        game = Game(rng=random.Random(1))
        game.new_game()
        for _ in range(5):
            game.update(1 / 60.0, RawInput())
            render.draw_frame(screen, game)  # must not raise


if __name__ == "__main__":
    unittest.main()
