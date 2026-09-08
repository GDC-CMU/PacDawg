"""Ordered key intent, safe paused help, and existing-cue hierarchy."""
from __future__ import annotations

import copy
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import pygame

from pacdawg import assets, config, input as inputs, render
from pacdawg.entities import Direction
from pacdawg.game import Game, GameState, PAUSE_ITEMS
from pacdawg.input import RawInput
from tests.test_pause import A, BACKS, DOWN, IDLE, START, UP, frame, snapshot
from tests.test_polish import catch_player, clear_maze, collect_power, park_ghosts, playing_game


def key_event(name, down=True):
    return pygame.event.Event(pygame.KEYDOWN if down else pygame.KEYUP,
                              key=pygame.key.key_code(name))


def poll(game, *events):
    with patch("pygame.event.get", return_value=list(events)):
        return game.poll_hardware()


class RefinementTests(unittest.TestCase):
    def setUp(self):
        for target in ("pacdawg.score.load_high_score", "pacdawg.score.save_high_score"):
            mock = patch(target, return_value=0)
            mock.start()
            self.addCleanup(mock.stop)
        pygame.init()
        render.clear_caches()
        self.screen = pygame.display.set_mode((800, 600))
        self.addCleanup(pygame.quit)
        self.addCleanup(assets.clear_cache)
        self.addCleanup(render.clear_caches)

    def test_perpendicular_opposite_and_alias_keys_follow_press_order(self):
        for first, second in (("right", "up"), ("d", "w"), ("left", "right"),
                              ("a", "d"), ("up", "w"), ("up", "down")):
            for a, b in ((first, second), (second, first)):
                with self.subTest(a=a, b=b):
                    game = Game()
                    raw = poll(game, key_event(a), key_event(b))
                    self.assertEqual(inputs.resolve_direction(raw), inputs.KEY_DIRECTIONS[b])
                    self.assertEqual(raw.keyboard_order, (a, b))
                    raw = poll(game, key_event(a))  # held OS repeat cannot take priority
                    self.assertEqual(inputs.resolve_direction(raw), inputs.KEY_DIRECTIONS[b])
                    raw = poll(game, key_event(b, False))
                    self.assertEqual(inputs.resolve_direction(raw), inputs.KEY_DIRECTIONS[a])
                    raw = poll(game, key_event(a, False))
                    self.assertIsNone(inputs.resolve_direction(raw))
                    self.assertEqual(raw.keyboard_order, ())

    def test_same_frame_release_repress_is_a_new_edge_and_history_is_bounded(self):
        game = Game()
        poll(game, key_event("w"), key_event("d"))
        raw = poll(game, key_event("w", False), key_event("w"))
        self.assertEqual(inputs.resolve_direction(raw), Direction.UP)
        for _ in range(100):
            raw = poll(game, *(key_event(key) for key in inputs.KEY_DIRECTIONS))
        self.assertEqual(len(raw.keyboard_order), len(inputs.KEY_DIRECTIONS))
        self.assertEqual(len(set(raw.keyboard_order)), len(raw.keyboard_order))

    def test_unknown_startup_order_has_stable_fallback_and_reseeding_clears_history(self):
        game = Game()
        poll(game, key_event("d"), key_event("w"))
        game._seed_input_state({"left", "right"}, set())
        self.assertEqual(game._keyboard_direction_order, [])
        self.assertEqual(inputs.resolve_direction(poll(game)), Direction.LEFT)
        raw = poll(game, key_event("down"))
        self.assertEqual(inputs.resolve_direction(raw), Direction.DOWN)
        raw = poll(game, key_event("down", False))
        self.assertEqual(inputs.resolve_direction(raw), Direction.LEFT)
        for keys in ({"up", "left"}, frozenset({"left", "up"})):
            self.assertEqual(inputs.keyboard_direction(keys), Direction.UP)

    def test_stick_priority_deadzone_and_both_slots_ignore_keyboard_history(self):
        for slot in (0, 1):
            axes = [(0, 0), (0, 0)]
            axes[slot] = (1, 0)
            raw = RawInput(axes=tuple(axes), pressed_keys=frozenset({"w", "s"}),
                           keyboard_order=("w", "s"))
            self.assertEqual(inputs.resolve_direction(raw), Direction.RIGHT)
        raw = RawInput(axes=((0, -1), (1, 0)), pressed_keys=frozenset({"s"}),
                       keyboard_order=("s",))
        self.assertEqual(inputs.resolve_direction(raw), Direction.UP)
        self.assertIsNone(inputs.axis_direction(config.JOYSTICK_DEADZONE - 0.01, 0))

    def test_overlapping_keys_match_single_resolved_direction_simulation(self):
        game = playing_game()
        park_ghosts(game)
        control = copy.deepcopy(game)
        for tick in range(100):
            events = {0: [key_event("right")], 8: [key_event("up")],
                      18: [key_event("right")], 25: [key_event("up", False)],
                      50: [key_event("right", False)]}.get(tick, [])
            raw = poll(game, *events)
            direction = inputs.resolve_direction(raw)
            keys = frozenset({direction.name.lower()}) if direction is not None else frozenset()
            frame(game, raw)
            frame(control, RawInput(pressed_keys=keys))
            self.assertEqual(snapshot(game), snapshot(control))
            if tick == 8:
                self.assertEqual(game.player.direction, Direction.UP)

    def test_held_ordered_keys_are_consumed_on_start_help_and_resume(self):
        game = Game()
        frame(game, poll(game, key_event("right"), key_event("left"), key_event("return")))
        self.assertEqual(game.state, GameState.READY)
        for _ in range(130):
            frame(game, poll(game))
        self.assertEqual(game.player.queued_direction, Direction.NONE)
        frame(game, poll(game, key_event("right", False), key_event("left", False),
                         key_event("return", False)))
        frame(game, poll(game, key_event("escape")))
        frame(game, poll(game, key_event("escape", False), key_event("down")))
        frame(game, poll(game, key_event("return")))
        self.assertEqual(game.state, GameState.HOW_TO_PLAY)
        for _ in range(10):
            frame(game, poll(game))
        frame(game, poll(game, key_event("return", False)))
        frame(game, poll(game, key_event("escape")))
        self.assertEqual(game.state, GameState.PAUSED)
        for _ in range(10):
            frame(game, poll(game))
        frame(game, poll(game, key_event("escape", False)))
        before = snapshot(game)
        frame(game, poll(game, key_event("escape")))
        self.assertEqual(game.state, GameState.PLAYING)
        self.assertEqual(snapshot(game), before)
        frame(game, poll(game))
        self.assertEqual(game.player.queued_direction, Direction.NONE)  # Down still held

    def phase_game(self, phase):
        if phase is GameState.READY:
            game = Game()
            frame(game, START)
            frame(game)
        else:
            game = playing_game()
            collect_power(game)
            if phase is GameState.DYING:
                catch_player(game)
            elif phase is GameState.LEVEL_CLEAR:
                clear_maze(game)
        self.assertEqual(game.state, phase)
        return game

    def test_keyboard_retry_consumes_all_held_directions_until_neutral(self):
        game = playing_game()
        game.score.lives = 1
        catch_player(game)
        frame(game, dt=1.5)
        self.assertEqual(game.state, GameState.GAME_OVER)
        frame(game, poll(game, key_event("left"), key_event("right"), key_event("space")))
        self.assertEqual(game.state, GameState.READY)
        for _ in range(130):
            frame(game, poll(game))
        self.assertEqual(game.player.queued_direction, Direction.NONE)
        frame(game, poll(game, key_event("right", False), key_event("space", False)))
        self.assertEqual(game.player.queued_direction, Direction.NONE)  # Left still held
        frame(game, poll(game, key_event("left", False)))
        frame(game, poll(game, key_event("up")))
        self.assertEqual(game.player.direction, Direction.UP)

    def test_help_from_every_real_phase_freezes_snapshot_pixels_rng_and_returns_to_pause(self):
        confirms = (START, *(RawInput(pressed_keys=frozenset({k})) for k in ("return", "space")))
        for phase in (GameState.READY, GameState.PLAYING, GameState.DYING, GameState.LEVEL_CLEAR):
            for close in (*BACKS, *confirms):
                with self.subTest(phase=phase, close=close):
                    game = self.phase_game(phase)
                    before = snapshot(game)
                    frame(game, BACKS[0])
                    frame(game, DOWN)
                    frame(game, START)
                    self.assertEqual(game.state, GameState.HOW_TO_PLAY)
                    render.draw_frame(self.screen, game)
                    pixels = pygame.image.tostring(self.screen, "RGB")
                    for _ in range(3):
                        frame(game, START, dt=30)
                        render.draw_frame(self.screen, game)
                        self.assertEqual(pygame.image.tostring(self.screen, "RGB"), pixels)
                        self.assertEqual(snapshot(game), before)
                    frame(game, A)
                    self.assertEqual(game.state, GameState.HOW_TO_PLAY)
                    frame(game)
                    frame(game, close)
                    self.assertEqual(game.state, GameState.PAUSED)
                    self.assertEqual(PAUSE_ITEMS[game.pause_index], "HOW TO PLAY")
                    for _ in range(3):
                        frame(game, close)
                        self.assertEqual(game.state, GameState.PAUSED)
                    self.assertEqual(snapshot(game), before)
                    frame(game)
                    frame(game, UP)
                    frame(game, START)
                    self.assertEqual(game.state, phase)
                    self.assertEqual(snapshot(game), before)

    def test_root_help_still_returns_to_main_menu_with_help_focused(self):
        game = Game()
        frame(game, DOWN)
        frame(game, START)
        frame(game)
        frame(game, BACKS[0])
        self.assertEqual(game.state, GameState.ATTRACT)
        self.assertEqual(game.menu_index, 1)
        self.assertIsNone(game.paused_state)

    def test_each_controller_can_open_and_close_paused_help(self):
        for device in (11, 22):
            game = playing_game()
            def button(down, number):
                event = pygame.event.Event(pygame.JOYBUTTONDOWN if down else pygame.JOYBUTTONUP,
                                          instance_id=device, button=number)
                frame(game, poll(game, event))
            button(True, config.BUTTON_B)
            button(False, config.BUTTON_B)
            axes = [(0, 0), (0, 0)]
            axes[0 if device == 11 else 1] = (0, 1)
            frame(game, RawInput(axes=tuple(axes)))
            button(True, config.BUTTON_START)
            self.assertEqual(game.state, GameState.HOW_TO_PLAY)
            button(False, config.BUTTON_START)
            button(True, config.BUTTON_A)
            self.assertEqual(game.state, GameState.HOW_TO_PLAY)
            button(True, config.BUTTON_P1)
            self.assertEqual(game.state, GameState.PAUSED)

    def test_reward_replaces_only_high_and_restores_after_existing_lifetime(self):
        game = playing_game()
        def texts():
            with patch.object(render, "_font_text", wraps=render._font_text) as text:
                render.draw_frame(self.screen, game)
            return [call.args[1] for call in text.call_args_list]
        self.assertTrue(any(t.startswith("HIGH ") for t in texts()))
        collect_power(game)
        event = texts()
        self.assertIn("POWER PELLET", event)
        self.assertFalse(any(t.startswith("HIGH ") for t in event))
        self.assertTrue(any(t.startswith("SCORE ") for t in event))
        self.assertIn("LEVEL 1", event)
        for expected, ghost in zip(config.GHOST_COMBO_SCORES, game.ghosts.values()):
            ghost.teleport(*game.player.tile)
            frame(game, dt=0)
            label = f"+{expected}  GHOST CHAIN"
            self.assertEqual(texts().count(label), 1)
            surface = render._font_text(render._font(28), label, render.HUD_ACCENT_COLOR)
            self.assertTrue(pygame.Rect(200, 0, 400, 40).contains(surface.get_rect(center=(400, 20))))
        park_ghosts(game)
        game.player.teleport(1, 1)
        for _ in range(73):
            frame(game)
        self.assertTrue(any(t.startswith("HIGH ") for t in texts()))
        self.assertFalse(any("GHOST CHAIN" in t for t in texts()))
