"""Event/flow acceptance through movement, pickups, collisions and real timers.

Scenario setup positions actors and seeds score/pellets; no test selects a
READY/DYING/CLEAR/RESULT enum to manufacture the transition being verified.
"""
from __future__ import annotations

import copy
import os
import random
import unittest
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from pacdawg import assets, config, levels, render
from pacdawg.entities import Direction, Scotty
from pacdawg.game import DYING_SECONDS, LEVEL_CLEAR_SECONDS, READY_SECONDS, Game, GameState
from pacdawg.ghosts import GhostMode
from pacdawg.input import RawInput
from tests.test_pause import A, BACKS, IDLE, START, frame, snapshot


def playing_game():
    game = Game(rng=random.Random(902))
    frame(game, START)
    frame(game, dt=READY_SECONDS)
    assert game.state is GameState.PLAYING
    return game


def park_ghosts(game):
    for ghost in game.ghosts.values():
        ghost.teleport(*ghost.home_tile)
        ghost.mode = GhostMode.HOUSE
        ghost.house_dwell_remaining = 1000


def collect_power(game):
    """Walk into the top-left power pellet, with active ghosts far away."""
    game.player.teleport(2, 1)
    for ghost in game.ghosts.values():
        ghost.teleport(20, 10)
        ghost.mode = GhostMode.CHASE
    before = game.last_power_at
    for _ in range(60):
        frame(game, RawInput(pressed_keys=frozenset({"left"})))
        if game.last_power_at != before:
            break
    assert (1, 1) not in game.maze.power_pellets
    assert all(g.mode is GhostMode.FRIGHTENED for g in game.ghosts.values())


def catch_player(game, raw=IDLE):
    park_ghosts(game)
    ghost = game.ghosts["gates"]
    ghost.teleport(*game.player.tile)
    ghost.mode = GhostMode.CHASE
    frame(game, raw, dt=0)
    assert game.state is GameState.DYING


def clear_maze(game):
    """Only the final dot remains; move into it through the real pickup path."""
    park_ghosts(game)
    for tile in tuple(game.maze.pellets | game.maze.power_pellets):
        if tile != (3, 1):
            game.maze.eat_at(*tile)
    game.player.teleport(2, 1)
    game.player.pause_timer = 0
    for _ in range(60):
        frame(game, RawInput(pressed_keys=frozenset({"right"})))
        if game.state is GameState.LEVEL_CLEAR:
            break
    assert game.state is GameState.LEVEL_CLEAR


class PolishEventTests(unittest.TestCase):
    def setUp(self):
        for target in ("pacdawg.score.save_high_score", "pacdawg.score.load_high_score"):
            mock = patch(target, return_value=0)
            mock.start()
            self.addCleanup(mock.stop)
        render.clear_caches()
        assets.clear_cache()
        pygame.init()
        self.screen = pygame.display.set_mode((800, 600))
        self.addCleanup(pygame.quit)
        self.addCleanup(assets.clear_cache)
        self.addCleanup(render.clear_caches)

    def feedback_text(self, game):
        with patch.object(render, "_text_at") as text:
            render._draw_feedback(self.screen, game, game.paused_state or game.state)
        return [call.args[1] for call in text.call_args_list]

    def test_movement_opens_collection_closes_wall_idle_does_not_cycle(self):
        game = playing_game()
        park_ghosts(game)
        # A cleared corridor isolates actual travel from pellet pauses.
        for x in range(1, 8):
            game.maze.eat_at(x, 1)
        game.player.teleport(6, 1)
        seen = set()
        for _ in range(180):
            frame(game, RawInput(pressed_keys=frozenset({"left"})))
            seen.add(game.player.chomp_frame)
        self.assertEqual(seen, {1, 2})
        self.assertEqual(game.player.direction, Direction.NONE)
        for _ in range(30):
            frame(game)
            self.assertEqual(game.player.chomp_frame, 1)
        # Existing dot pause closes the mouth; it is not lengthened for animation.
        game.player.teleport(8, 1)
        frame(game, dt=0)
        self.assertEqual(game.player.chomp_frame, 1)
        self.assertEqual(game.player.pause_timer, config.DOT_EAT_PAUSE_SECONDS)
        self.assertEqual(self.feedback_text(game), [])  # no ordinary-dot label

    def test_animation_is_distance_linked_not_elapsed_time_and_read_only(self):
        maze = levels.build_maze(1)
        for speed in (3, 9):
            player = Scotty(5, 1, speed)
            player.queue_direction(Direction.RIGHT)
            player.update(maze, 0.6 / speed)
            self.assertEqual(player.chomp_frame, 2)
            self.assertAlmostEqual(player.chomp_travel, 0.6)
            before = copy.deepcopy(vars(player))
            for _ in range(100):
                self.assertEqual(player.chomp_frame, 2)
            self.assertEqual(vars(player), before)

    def test_power_and_each_combo_are_one_shot_and_expire_without_clearing_gameplay(self):
        game = playing_game()
        collect_power(game)
        self.assertIn("POWER PELLET", self.feedback_text(game))
        stamp = game.last_power_at
        for points, ghost in zip(config.GHOST_COMBO_SCORES, game.ghosts.values()):
            ghost.teleport(*game.player.tile)
            frame(game, dt=0)
            self.assertEqual(game.last_ghost_eaten_points, points)
            self.assertIn(f"+{points}  GHOST CHAIN", self.feedback_text(game))
            before = (game.score.score, game.last_ghost_eaten_at)
            frame(game, dt=0)
            self.assertEqual((game.score.score, game.last_ghost_eaten_at), before)
            self.assertEqual(ghost.mode, GhostMode.EATEN)
        self.assertEqual(game.last_power_at, stamp)
        # Expiry is visual only. No record or combo is mutated by drawing.
        park_ghosts(game)
        game.player.teleport(1, 1)
        for _ in range(90):
            frame(game)
        self.assertEqual(self.feedback_text(game), [])
        self.assertEqual(game.score.ghost_chain, 4)

    def test_real_extra_life_award_is_brief_and_not_retriggered(self):
        game = playing_game()
        park_ghosts(game)
        game.score.score = config.EXTRA_LIFE_THRESHOLD - config.PELLET_SCORE
        game.player.teleport(3, 1)
        frame(game, dt=0)
        self.assertEqual(game.score.lives, config.STARTING_LIVES + 1)
        self.assertIn("+1 LIFE", self.feedback_text(game))
        stamp = game.last_extra_life_at
        game.player.teleport(4, 1)
        frame(game)
        self.assertEqual(game.last_extra_life_at, stamp)
        game.player.teleport(*game.maze.player_start)
        for _ in range(120):
            frame(game)
        self.assertNotIn("+1 LIFE", self.feedback_text(game))
        self.assertEqual(game.score.lives, config.STARTING_LIVES + 1)

    def test_life_award_is_observed_before_same_frame_death(self):
        game = playing_game()
        game.score.score = config.EXTRA_LIFE_THRESHOLD - config.PELLET_SCORE
        game.player.teleport(3, 1)
        catch_player(game)
        self.assertEqual(game.score.lives, config.STARTING_LIVES)
        self.assertIn("+1 LIFE", self.feedback_text(game))
        self.assertIn("CAUGHT", self.feedback_text(game))

    def test_real_event_pause_freezes_effect_pixels_snapshot_rng_and_expiry(self):
        game = playing_game()
        game.score.score = config.EXTRA_LIFE_THRESHOLD - config.POWER_PELLET_SCORE
        collect_power(game)
        ghost = game.ghosts["gates"]
        ghost.teleport(*game.player.tile)
        frame(game, dt=0)
        before = snapshot(game)
        render.draw_frame(self.screen, game)
        pixels = pygame.image.tostring(self.screen, "RGB")
        frame(game, BACKS[0])
        with patch.object(render, "_draw_pause_screen"):
            for _ in range(30):
                frame(game, dt=1)
                render.draw_frame(self.screen, game)
                self.assertEqual(pygame.image.tostring(self.screen, "RGB"), pixels)
        self.assertEqual(snapshot(game), before)
        frame(game, START)
        self.assertEqual(snapshot(game), before)
        self.assertIn("+200  GHOST CHAIN", self.feedback_text(game))

    def test_clear_all_tiers_via_last_pellet_without_extra_delays(self):
        game = playing_game()
        for level in range(1, 12):
            self.assertEqual(game.score.level, level)
            self.assertEqual(game.player.speed, levels.pacman_normal_speed(level))
            clear_maze(game)
            self.assertEqual(game.state_timer, LEVEL_CLEAR_SECONDS)
            self.assertIn("NEXT  " + render._maze_label(level + 1), self.feedback_text(game))
            frame(game, dt=LEVEL_CLEAR_SECONDS)
            self.assertEqual(game.state, GameState.READY)
            self.assertEqual(game.maze.name, levels.name_for_level(level + 1))
            self.assertEqual(game.maze.pellets_remaining, game.maze.total_pellets)
            self.assertIsNone(game.last_ghost_eaten_points)
            self.assertEqual(game.last_power_at, -999)
            self.assertEqual(game.state_timer, READY_SECONDS)
            frame(game, dt=READY_SECONDS)
            self.assertEqual(game.state, GameState.PLAYING)
        self.assertIn("TIER 10 OF 10", render._maze_label(12))

    def test_death_respawns_same_maze_and_clears_old_feedback(self):
        game = playing_game()
        collect_power(game)
        pellets = game.maze.pellets_remaining
        catch_player(game)
        self.assertEqual(game.state_timer, DYING_SECONDS)
        self.assertIn("CAUGHT", self.feedback_text(game))
        frame(game, dt=DYING_SECONDS)
        self.assertEqual(game.state, GameState.READY)
        self.assertEqual(game.score.level, 1)
        self.assertEqual(game.maze.pellets_remaining, pellets)
        self.assertIsNone(game.last_power_tile)
        self.assertEqual(game.player.chomp_frame, 1)

    def test_render_frequency_never_changes_simulation_or_rng(self):
        game = playing_game()
        collect_power(game)
        other = copy.deepcopy(game)
        for _ in range(240):
            frame(game)
            frame(other)
            before = snapshot(game)
            for _ in range(3):
                render.draw_frame(self.screen, game)
            self.assertEqual(snapshot(game), before)
            self.assertEqual(snapshot(game), snapshot(other))

    def test_caches_are_bounded_and_static_geometry_is_reused(self):
        game = playing_game()
        render.draw_frame(self.screen, game)
        cached = render._maze_structure.cache_info()
        for _ in range(20):
            render.draw_frame(self.screen, game)
        self.assertEqual(render._maze_structure.cache_info().misses, cached.misses)
        self.assertEqual(render._maze_structure.cache_info().maxsize, 4)
        self.assertEqual(render._faded.cache_info().maxsize, 32)

    def test_keyboard_retry_aliases_reset_run_and_consume_held_steering(self):
        for key in ("return", "enter", "space"):
            game = playing_game()
            collect_power(game)
            game.score.lives = 1
            game.score.score = 12340
            catch_player(game)
            frame(game, dt=DYING_SECONDS)
            self.assertEqual(game.state, GameState.GAME_OVER)
            self.assertEqual(game.result_index, 0)
            old = (game.player, game.maze, game.score, game.ghosts)
            retry = RawInput(pressed_keys=frozenset({key, "up"}))
            # Up and Down each toggle the two-result menu; choose Play Again.
            frame(game, RawInput(pressed_keys=frozenset({"down"})))
            frame(game)
            frame(game, retry)
            self.assertEqual(game.state, GameState.READY)
            self.assertEqual((game.score.score, game.score.level, game.score.lives),
                             (0, 1, config.STARTING_LIVES))
            self.assertEqual(game.score.high_score, 12340)
            self.assertEqual(game.maze.pellets_remaining, game.maze.total_pellets)
            self.assertFalse(game.fruit_active)
            self.assertEqual(game.fruit_timer, 0)
            self.assertEqual(game.score.ghost_chain, 0)
            self.assertFalse(game.score._extra_life_awarded)
            for old_obj, new_obj in zip(old, (game.player, game.maze, game.score, game.ghosts)):
                self.assertIsNot(old_obj, new_obj)
            for _ in range(150):
                frame(game, retry)
                self.assertEqual(game.player.queued_direction, Direction.NONE)
            frame(game)
            frame(game, RawInput(pressed_keys=frozenset({"left"})))
            self.assertEqual(game.player.direction, Direction.LEFT)

    def test_result_entry_consumes_held_direction_and_start_but_never_a(self):
        game = playing_game()
        game.score.lives = 1
        held = RawInput(pressed_buttons=START.pressed_buttons, axes=((0.0, 1.0),))
        catch_player(game, held)
        frame(game, held, dt=DYING_SECONDS)
        for _ in range(30):
            frame(game, held)
            self.assertEqual(game.state, GameState.GAME_OVER)
            self.assertEqual(game.result_index, 0)
        frame(game)
        frame(game, A)
        self.assertEqual(game.state, GameState.GAME_OVER)
        frame(game, START)
        self.assertEqual(game.state, GameState.READY)

    def test_both_keyboard_navigation_sets_and_result_main_menu(self):
        for down, up in (("down", "up"), ("s", "w")):
            game = playing_game()
            game.score.lives = 1
            catch_player(game)
            frame(game, dt=DYING_SECONDS)
            for key, expected in ((down, 1), (up, 0), (down, 1)):
                frame(game, RawInput(pressed_keys=frozenset({key})))
                self.assertEqual(game.result_index, expected)
                frame(game)
            frame(game, START)
            self.assertEqual(game.state, GameState.ATTRACT)

    def test_each_controller_hardware_slot_can_retry_and_pause_without_a(self):
        for device in (11, 22):
            game = playing_game()
            game.score.lives = 1
            catch_player(game)
            frame(game, dt=DYING_SECONDS)
            def poll(kind, button):
                event = pygame.event.Event(kind, instance_id=device, button=button)
                with patch("pygame.event.get", return_value=[event]):
                    frame(game, game.poll_hardware())
            poll(pygame.JOYBUTTONDOWN, config.BUTTON_A)
            self.assertEqual(game.state, GameState.GAME_OVER)
            poll(pygame.JOYBUTTONDOWN, config.BUTTON_START)
            self.assertEqual(game.state, GameState.READY)
            poll(pygame.JOYBUTTONUP, config.BUTTON_START)
            poll(pygame.JOYBUTTONDOWN, config.BUTTON_B)
            self.assertEqual(game.state, GameState.PAUSED)
            poll(pygame.JOYBUTTONUP, config.BUTTON_B)
            poll(pygame.JOYBUTTONDOWN, config.BUTTON_START)
            self.assertEqual(game.state, GameState.READY)

    def test_result_navigation_from_either_stick_is_edge_triggered(self):
        for slot in (0, 1):
            game = playing_game()
            game.score.lives = 1
            catch_player(game)
            frame(game, dt=DYING_SECONDS)
            axes = [(0, 0), (0, 0)]
            axes[slot] = (0, 1)
            down = RawInput(axes=tuple(axes))
            for _ in range(30):
                frame(game, down)
                self.assertEqual(game.result_index, 1)
            frame(game)
            frame(game, down)
            self.assertEqual(game.result_index, 0)
            frame(game, START)
            self.assertEqual(game.state, GameState.READY)

    def test_all_back_aliases_return_one_level_and_help_keeps_focus(self):
        for back in BACKS:
            game = playing_game()
            game.score.lives = 1
            catch_player(game)
            frame(game, dt=DYING_SECONDS)
            frame(game, back)
            self.assertEqual(game.state, GameState.ATTRACT)
            for _ in range(30):
                frame(game, back)
            frame(game)
            frame(game, RawInput(pressed_keys=frozenset({"s"})))
            frame(game, START)
            self.assertEqual(game.state, GameState.HOW_TO_PLAY)
            frame(game)
            frame(game, back)
            self.assertEqual(game.state, GameState.ATTRACT)
            self.assertEqual(game.menu_index, 1)
