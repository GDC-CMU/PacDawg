"""Tests for the hard arcade-cabinet contract with ArcadeLauncher.

- The display must be exactly 800x600.
- Button 5 (P1) or Esc must exit immediately, from any game state, via
  ``sys.exit(0)``.
- The game must survive hundreds of simulated frames without crashing,
  including full runs through every input direction and state.
"""
from __future__ import annotations

import os
import random
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

from pacdawg import config  # noqa: E402
from pacdawg.entities import Direction  # noqa: E402
from pacdawg.game import Game, GameState  # noqa: E402
from pacdawg.input import RawInput  # noqa: E402


class DisplayContractTests(unittest.TestCase):
    def test_configured_resolution_is_800x600(self):
        self.assertEqual(config.SCREEN_WIDTH, 800)
        self.assertEqual(config.SCREEN_HEIGHT, 600)

    def test_display_surface_matches_configured_resolution(self):
        pygame.init()
        screen = pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
        self.assertEqual(screen.get_size(), (800, 600))


class ExitContractTests(unittest.TestCase):
    def test_p1_button_exits_with_code_zero_from_every_state(self):
        for state in GameState:
            with self.subTest(state=state):
                game = Game(rng=random.Random(0))
                game.state = state
                raw = RawInput(pressed_buttons=frozenset({config.BUTTON_P1}))
                with self.assertRaises(SystemExit) as cm:
                    game.maybe_exit(raw)
                self.assertEqual(cm.exception.code, 0)

    def test_escape_key_also_exits_with_code_zero(self):
        game = Game(rng=random.Random(0))
        raw = RawInput(pressed_keys=frozenset({"escape"}))
        with self.assertRaises(SystemExit) as cm:
            game.maybe_exit(raw)
        self.assertEqual(cm.exception.code, 0)

    def test_no_exit_without_the_exit_input(self):
        game = Game(rng=random.Random(0))
        raw = RawInput(pressed_buttons=frozenset({config.BUTTON_A}))
        try:
            game.maybe_exit(raw)
        except SystemExit:
            self.fail("maybe_exit() exited without an exit input present")

    def test_either_button_5_from_a_second_stick_still_exits(self):
        # Two identical DragonRise sticks are on the cabinet; button
        # indices are per-event, not per-device, so this is really just
        # confirming index 5 alone is sufficient regardless of source.
        game = Game(rng=random.Random(0))
        raw = RawInput(pressed_buttons=frozenset({config.BUTTON_P1}))
        with self.assertRaises(SystemExit):
            game.maybe_exit(raw)


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
