"""Pause/start contract exercised in run() order, with real RawInput tuples."""
from __future__ import annotations

import copy
import os
import random
import unittest
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from pacdawg import config, render
from pacdawg.entities import Direction
from pacdawg.game import ACTIVE_STATES, Game, GameState
from pacdawg.ghosts import GhostMode
from pacdawg.input import RawInput


IDLE = RawInput()
START = RawInput(pressed_buttons=frozenset({config.BUTTON_START}))
A = RawInput(pressed_buttons=frozenset({config.BUTTON_A}))
BACKS = (
    RawInput(pressed_buttons=frozenset({config.BUTTON_B})),
    RawInput(pressed_buttons=frozenset({config.BUTTON_P1})),
    RawInput(pressed_keys=frozenset({"escape"})),
    RawInput(pressed_keys=frozenset({"backspace"})),
)
DOWN = RawInput(axes=((0.0, 0.0), (0.0, 1.0)))


def frame(game, raw=IDLE, dt=1 / 60.0):
    game.maybe_go_back(raw)
    game.update(dt, raw)


def snapshot(game):
    """All simulation fields, including entity internals, timers and RNG.

    Exclude only navigation/hardware/UI fields; normalize PAUSED to its
    saved phase so entering/resuming can also be compared exactly.
    """
    fields = (
        "state_timer", "gameplay_time", "fruit_active", "fruit_tile",
        "fruit_timer", "fruit_thresholds_hit", "life_elapsed",
        "last_ghost_eaten_points", "last_ghost_eaten_at", "dot_counter_mode",
        "last_power_at", "last_power_tile", "last_extra_life_at",
        "_house_order_index", "_house_dot_counter", "_global_dot_counter",
        "_time_since_last_pellet", "elroy_unlocked",
    )
    value = {name: getattr(game, name) for name in fields}
    value.update(
        phase=game.paused_state or game.state,
        player=vars(game.player), ghosts={k: vars(v) for k, v in game.ghosts.items()},
        maze=vars(game.maze), score=vars(game.score),
        scatter_clock=vars(game.scatter_clock), rng=game.rng.getstate(),
    )
    return copy.deepcopy(value)


class PauseContractTests(unittest.TestCase):
    def setUp(self):
        save_patch = patch("pacdawg.score.save_high_score")
        self.save = save_patch.start()
        self.addCleanup(save_patch.stop)

    def active_game(self, phase=GameState.PLAYING):
        game = Game(rng=random.Random(120))
        game.new_game()
        frame(game, RawInput(pressed_keys=frozenset({"left"})), 2.1)
        for _ in range(12):
            frame(game)
        self.assertEqual(game.state, GameState.PLAYING)
        if phase is GameState.READY:
            game.new_game()
            frame(game, dt=0.4)
        elif phase is GameState.DYING:
            game._on_player_caught()
            frame(game, dt=0.4)
        elif phase is GameState.LEVEL_CLEAR:
            game.maze.pellets.clear()
            game.maze.power_pellets.clear()
            frame(game)
            frame(game, dt=0.4)
        self.assertEqual(game.state, phase)
        return game

    def test_every_phase_and_back_alias_freezes_exact_snapshot_and_rng(self):
        for phase in ACTIVE_STATES:
            for back in BACKS:
                with self.subTest(phase=phase, back=back):
                    game = self.active_game(phase)
                    # Nonzero fruit, frightened/revival/release timers and combo.
                    game._spawn_fruit()
                    game.fruit_timer = 8.25
                    game.fruit_thresholds_hit = {70}
                    game.ghosts["gates"].mode = GhostMode.CHASE
                    game.ghosts["gates"].frighten(4.5, 3)
                    game.ghosts["wean"].house_dwell_remaining = 2.25
                    game.score.ghost_chain = 2
                    game._time_since_last_pellet = 1.25
                    game._house_dot_counter = 7
                    before = snapshot(game)
                    objects = (game.player, game.maze, game.score, game.ghosts)
                    frame(game, back, 0.25)
                    self.assertEqual(game.state, GameState.PAUSED)
                    self.assertEqual(game.pause_index, 0)
                    self.assertEqual(snapshot(game), before)
                    for _ in range(240):
                        frame(game, back, 0.25)
                    frame(game, DOWN, 2.0)  # UI navigation must not steer Scotty
                    frame(game, A, 2.0)
                    self.assertEqual(game.pause_index, 1)
                    self.assertEqual(game.state, GameState.PAUSED)
                    self.assertEqual(snapshot(game), before)
                    self.assertGreater(game.pause_ui_time, config.DEMO_IDLE_SECONDS)
                    # Back resumes even when the destructive option is selected.
                    frame(game, back, 0.25)
                    self.assertEqual(game.state, phase)
                    self.assertEqual(snapshot(game), before)
                    self.assertEqual(objects, (game.player, game.maze, game.score, game.ghosts))
                    self.save.assert_not_called()

    def test_resume_matches_uninterrupted_simulation_including_phase_expiry(self):
        for phase in ACTIVE_STATES:
            with self.subTest(phase=phase):
                game = self.active_game(phase)
                control = copy.deepcopy(game)
                frame(game, BACKS[0])
                frame(game, dt=180.0)
                frame(game, START)
                self.assertEqual(snapshot(game), snapshot(control))
                for _ in range(150):
                    frame(game)
                    frame(control)
                    self.assertEqual(snapshot(game), snapshot(control))

    def test_deliberate_abandon_commits_and_new_run_is_fresh(self):
        game = self.active_game()
        game.score.score = game.score.high_score + 500
        game.score.lives = 1
        game.fruit_active = True
        earned = game.score.score
        old_objects = (game.player, game.maze, game.score)
        frame(game, BACKS[0])
        self.save.assert_not_called()
        frame(game, DOWN)
        frame(game, START)
        self.assertEqual(game.state, GameState.ATTRACT)
        self.assertIsNone(game.paused_state)
        self.save.assert_called_once_with(earned)
        for _ in range(40):
            frame(game, START)
        self.assertEqual(game.state, GameState.ATTRACT)
        frame(game)
        frame(game, START)
        self.assertEqual(game.state, GameState.READY)
        self.assertEqual(game.state_timer, 2.0)
        self.assertEqual(game.score.score, 0)
        self.assertEqual(game.score.level, 1)
        self.assertEqual(game.score.lives, config.STARTING_LIVES)
        self.assertFalse(game.fruit_active)
        self.assertEqual(game.maze.pellets_remaining, game.maze.total_pellets)
        for old, new in zip(old_objects, (game.player, game.maze, game.score)):
            self.assertIsNot(old, new)

    def test_start_held_with_back_cannot_resume_pause_until_released(self):
        for back in BACKS:
            game = self.active_game()
            combo = RawInput(pressed_keys=back.pressed_keys,
                             pressed_buttons=back.pressed_buttons | START.pressed_buttons)
            for _ in range(40):
                frame(game, combo)
            frame(game, START)  # release Back only
            self.assertEqual(game.state, GameState.PAUSED)
            frame(game)  # old Start release is not confirmation
            self.assertEqual(game.state, GameState.PAUSED)
            frame(game, START)
            self.assertEqual(game.state, GameState.PLAYING)

    def test_pause_direction_does_not_leak_into_resumed_game_or_new_run(self):
        game = self.active_game()
        frame(game, BACKS[0])
        queued = game.player.queued_direction
        frame(game, DOWN)
        held = RawInput(axes=DOWN.axes, pressed_buttons=BACKS[0].pressed_buttons)
        frame(game, held)
        frame(game, held)  # held pause navigation must not steer or pause again
        self.assertEqual(game.state, GameState.PLAYING)
        self.assertEqual(game.player.queued_direction, queued)
        menu = Game()
        combo = RawInput(pressed_keys=frozenset({"left", "return"}))
        frame(menu, combo)
        for _ in range(10):
            frame(menu, combo)
        self.assertEqual(menu.player.queued_direction, Direction.NONE)
        frame(menu)
        frame(menu, RawInput(pressed_keys=frozenset({"left"})))
        self.assertEqual(menu.player.queued_direction, Direction.LEFT)

    def test_a_never_confirms_on_menu_help_result_or_pause(self):
        for state in (GameState.ATTRACT, GameState.HOW_TO_PLAY, GameState.GAME_OVER, GameState.PAUSED):
            with self.subTest(state=state):
                game = self.active_game()
                if state is GameState.PAUSED:
                    frame(game, BACKS[0])
                else:
                    game.state = state
                for _ in range(40):
                    frame(game, A)
                self.assertEqual(game.state, state)
                frame(game)
                frame(game, START)
                self.assertEqual(game.state, {
                    GameState.ATTRACT: GameState.READY, GameState.PAUSED: GameState.PLAYING,
                    GameState.HOW_TO_PLAY: GameState.ATTRACT, GameState.GAME_OVER: GameState.READY,
                }[state])

    def test_demo_wake_is_consumed_for_start_a_back_and_stick(self):
        for wake in (START, A, DOWN, *BACKS):
            game = Game()
            real_score = game.score
            game._enter_demo()
            for _ in range(30):
                frame(game)
            for _ in range(40):
                frame(game, wake)
                self.assertEqual(game.state, GameState.ATTRACT)
                self.assertEqual(game.menu_index, 0)
            self.assertIs(game.score, real_score)
            frame(game)
            frame(game, A)
            self.assertEqual(game.state, GameState.ATTRACT)
            frame(game, START)
            self.assertEqual(game.state, GameState.READY)

    def test_a_is_menu_activity_without_starting(self):
        game = Game()
        for _ in range(100):
            frame(game, A, 1.0)
        self.assertEqual(game.state, GameState.ATTRACT)
        self.assertEqual(game._menu_idle_seconds, 0.0)

    def test_keyboard_confirm_aliases_and_startup_held_controls(self):
        confirms = (START, *(RawInput(pressed_keys=frozenset({key}))
                             for key in ("return", "enter", "space")))
        for held in (*confirms, *BACKS, A):
            with self.subTest(held=held):
                game = Game()
                game._seed_input_state(held.pressed_keys, held.pressed_buttons)
                for _ in range(40):
                    frame(game, held)
                self.assertEqual(game.state, GameState.ATTRACT)
                frame(game)
                if held in BACKS:
                    with self.assertRaises(SystemExit):
                        frame(game, held)
                elif held in confirms:
                    frame(game, held)
                    self.assertEqual(game.state, GameState.READY)
                    frame(game, BACKS[0])
                    frame(game)
                    frame(game, held)
                    self.assertEqual(game.state, GameState.READY)

    def test_held_start_across_death_does_not_dismiss_game_over(self):
        game = self.active_game()
        game.score.lives = 1
        frame(game, START)
        game._on_player_caught()
        for _ in range(180):
            frame(game, START)
        self.assertEqual(game.state, GameState.GAME_OVER)
        frame(game)
        frame(game, START)
        for _ in range(40):
            frame(game, START)
        self.assertEqual(game.state, GameState.READY)

    def test_back_plus_confirm_on_help_cannot_start_a_game(self):
        game = Game()
        game.state = GameState.HOW_TO_PLAY
        combo = RawInput(pressed_keys=frozenset({"escape", "return"}))
        for _ in range(40):
            frame(game, combo)
        self.assertEqual(game.state, GameState.ATTRACT)
        frame(game)
        frame(game, START)
        self.assertEqual(game.state, GameState.HOW_TO_PLAY)  # focus restored to help

    def test_held_back_through_main_menu_and_new_run_requires_release(self):
        for back in BACKS:
            game = self.active_game()
            frame(game, back)
            frame(game, RawInput(axes=DOWN.axes, pressed_keys=back.pressed_keys,
                                 pressed_buttons=back.pressed_buttons))
            combo = RawInput(pressed_keys=back.pressed_keys,
                             pressed_buttons=back.pressed_buttons | START.pressed_buttons)
            frame(game, combo)
            self.assertEqual(game.state, GameState.ATTRACT)
            for _ in range(40):
                frame(game, combo)
            frame(game, back)  # release only Start
            frame(game, combo)
            self.assertEqual(game.state, GameState.READY)
            frame(game, back)  # Back is still the original physical hold
            self.assertEqual(game.state, GameState.READY)
            frame(game)
            frame(game, back)
            self.assertEqual(game.state, GameState.PAUSED)

    def test_paused_backdrop_pixels_and_rendering_never_advance_the_run(self):
        render.clear_caches()
        pygame.init()
        self.addCleanup(pygame.quit)
        self.addCleanup(render.clear_caches)
        screen = pygame.display.set_mode((800, 600))
        for phase in ACTIVE_STATES:
            with self.subTest(phase=phase):
                game = self.active_game(phase)
                render.draw_frame(screen, game)
                pixels = pygame.image.tostring(screen, "RGB")
                before = snapshot(game)
                frame(game, BACKS[0])
                with patch.object(render, "_draw_pause_screen"):
                    # Switch input device and advance only UI/wall clocks.
                    frame(game, RawInput(pressed_keys=frozenset({"left"})), 30.0)
                    with patch("pygame.time.get_ticks", return_value=987654321):
                        render.draw_frame(screen, game)
                    self.assertEqual(pygame.image.tostring(screen, "RGB"), pixels)
                self.assertEqual(snapshot(game), before)
                render.draw_frame(screen, game)  # real overlay, too
                self.assertEqual(snapshot(game), before)

    def test_static_menu_helpers_are_reused_and_all_screens_render(self):
        render.clear_caches()
        pygame.init()
        self.addCleanup(pygame.quit)
        self.addCleanup(render.clear_caches)
        screen = pygame.display.set_mode((800, 600))
        game = Game()
        for pad in (False, True):
            game.using_gamepad = pad
            for state in (GameState.ATTRACT, GameState.HOW_TO_PLAY, GameState.GAME_OVER):
                game.state = state
                render.draw_frame(screen, game)
        with patch("pygame.transform.scale", wraps=pygame.transform.scale) as scale:
            for state in (GameState.ATTRACT, GameState.HOW_TO_PLAY):
                game.state = state
                render.draw_frame(screen, game)
                render.draw_frame(screen, game)
            scale.assert_not_called()


class TwoStickPollingTests(unittest.TestCase):
    def test_start_and_back_seeded_from_each_real_hardware_slot_are_held(self):
        class Joystick:
            def __init__(self, button):
                self.button = button
            def get_numbuttons(self):
                return 10
            def get_button(self, index):
                return index == self.button
            def get_numaxes(self):
                return 2
            def get_axis(self, index):
                return 0.0
        for slot in (11, 22):
            for button in (config.BUTTON_START, config.BUTTON_B, config.BUTTON_P1):
                game = Game()
                game.joysticks = {11: Joystick(-1), 22: Joystick(-1)}
                game.joysticks[slot] = Joystick(button)
                with patch("pygame.key.get_pressed", return_value=[]):
                    game._seed_input_state_from_hardware()
                with patch("pygame.event.get", return_value=[]):
                    for _ in range(40):
                        raw = game.poll_hardware()
                        self.assertEqual(raw.axes, ((0.0, 0.0), (0.0, 0.0)))
                        frame(game, raw)
                self.assertEqual(game.state, GameState.ATTRACT)

    def test_both_devices_can_start_and_pause_and_one_release_does_not_rearm(self):
        def event(kind, device, button):
            return pygame.event.Event(kind, instance_id=device, button=button)

        with patch("pacdawg.score.save_high_score"):
            for device in (11, 22):
                game = Game()
                def poll(*events):
                    with patch("pygame.event.get", return_value=list(events)):
                        raw = game.poll_hardware()
                    self.assertIsInstance(raw.axes, tuple)
                    frame(game, raw)
                poll(event(pygame.JOYBUTTONDOWN, device, config.BUTTON_A))
                self.assertEqual(game.state, GameState.ATTRACT)
                poll(event(pygame.JOYBUTTONDOWN, device, config.BUTTON_START))
                self.assertEqual(game.state, GameState.READY)
                poll(event(pygame.JOYBUTTONUP, device, config.BUTTON_START))
                poll(event(pygame.JOYBUTTONDOWN, device, config.BUTTON_B))
                self.assertEqual(game.state, GameState.PAUSED)
                other = 33 - device
                poll(event(pygame.JOYBUTTONDOWN, other, config.BUTTON_B))
                poll(event(pygame.JOYBUTTONUP, device, config.BUTTON_B))
                self.assertFalse(game._back_armed)
                self.assertEqual(game.state, GameState.PAUSED)
                poll(event(pygame.JOYBUTTONUP, other, config.BUTTON_B))
                poll(event(pygame.JOYBUTTONDOWN, other, config.BUTTON_B))
                self.assertEqual(game.state, GameState.READY)


if __name__ == "__main__":
    unittest.main()
