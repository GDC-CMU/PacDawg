"""The PacDawg state machine: attract -> ready -> play -> death -> ... .

This is one of the three modules (with :mod:`pacdawg.render` and
:mod:`pacdawg.assets`) allowed to import pygame, since it owns the real
event loop, hardware polling, and timing. All of the actual rules
(movement, targeting, scoring) live in the pure modules and are simply
orchestrated here.
"""
from __future__ import annotations

import random
import sys
from enum import Enum, auto
from typing import Dict, Optional, Set, Tuple

import pygame

from . import config, input as input_mod, levels
from .entities import Direction, Scotty
from .ghosts import Ghost, GhostMode, ScatterChaseClock, apply_phase_change, create_ghosts
from .input import RawInput
from .maze import Maze
from .score import ScoreBoard

Coord = Tuple[int, int]


class GameState(Enum):
    ATTRACT = auto()
    READY = auto()
    PLAYING = auto()
    DYING = auto()
    LEVEL_CLEAR = auto()
    GAME_OVER = auto()


READY_SECONDS = 2.0
DYING_SECONDS = 1.5
LEVEL_CLEAR_SECONDS = 2.0
COLLISION_DISTANCE_SQ = 0.36  # ~0.6 tiles: catches near-misses, not just exact overlap


class Game:
    """Owns all game state and advances it one frame at a time.

    ``update()`` contains no pygame calls and can be driven directly by
    tests with a synthetic :class:`~pacdawg.input.RawInput`. Only
    ``run()`` (and the small helpers it uses to talk to real hardware)
    touch pygame.
    """

    def __init__(self, rng: Optional[random.Random] = None):
        self.rng = rng or random.Random()
        self.state = GameState.ATTRACT
        self.state_timer = 0.0
        self.score = ScoreBoard()
        self.maze: Maze = levels.build_maze(1)
        self.player: Scotty = self._make_player(self.maze)
        self.ghosts: Dict[str, Ghost] = create_ghosts(self.maze, 1)
        self.scatter_clock = ScatterChaseClock()
        self.fruit_active = False
        self.fruit_tile: Optional[Coord] = None
        self.fruit_timer = 0.0
        self.fruit_thresholds_hit: Set[int] = set()
        self.life_elapsed = 0.0
        self.last_ghost_eaten_points: Optional[int] = None
        self.last_ghost_eaten_at: float = -999.0

        # pygame handles, created lazily by run()/init_display()
        self.screen = None
        self.clock = None
        self.joysticks: Dict[int, "pygame.joystick.Joystick"] = {}
        self.pressed_keys: Set[str] = set()
        self.pressed_buttons: Set[int] = set()

    # -- setup helpers --------------------------------------------------------
    @staticmethod
    def _make_player(maze: Maze) -> Scotty:
        col, row = maze.player_start
        return Scotty(col, row, config.BASE_PLAYER_SPEED)

    def new_game(self) -> None:
        self.score = ScoreBoard()
        self._start_level(1)
        self.state = GameState.READY
        self.state_timer = READY_SECONDS

    def _start_level(self, level: int) -> None:
        self.score.level = level
        self.maze = levels.build_maze(level)
        self.player = self._make_player(self.maze)
        speed_mult = levels.speed_multiplier_for_level(level)
        self.player.speed = config.BASE_PLAYER_SPEED * speed_mult
        self.ghosts = create_ghosts(self.maze, level)
        self.scatter_clock = ScatterChaseClock()
        self.fruit_active = False
        self.fruit_tile = None
        self.fruit_thresholds_hit = set()
        self.life_elapsed = 0.0

    def _reset_positions_same_level(self) -> None:
        col, row = self.maze.player_start
        self.player.teleport(col, row, Direction.NONE)
        for name, ghost in self.ghosts.items():
            start_col, start_row = self.maze.ghost_starts[name]
            ghost.teleport(start_col, start_row, Direction.NONE)
            ghost.mode = GhostMode.HOUSE
            ghost.released = False
        self.scatter_clock = ScatterChaseClock()
        self.life_elapsed = 0.0

    # -- pure per-frame update --------------------------------------------------
    def update(self, dt: float, raw: RawInput) -> None:
        if self.state is GameState.ATTRACT:
            if input_mod.wants_confirm(raw):
                self.new_game()
            return

        if self.state is GameState.READY:
            self.state_timer -= dt
            direction = input_mod.resolve_direction(raw)
            if direction is not None:
                self.player.queue_direction(direction)
            if self.state_timer <= 0:
                self.state = GameState.PLAYING
            return

        if self.state is GameState.PLAYING:
            self._update_playing(dt, raw)
            return

        if self.state is GameState.DYING:
            self.state_timer -= dt
            if self.state_timer <= 0:
                if self.score.lives > 0:
                    self._reset_positions_same_level()
                    self.state = GameState.READY
                    self.state_timer = READY_SECONDS
                else:
                    self.score.commit_high_score()
                    self.state = GameState.GAME_OVER
                    self.state_timer = 0.0
            return

        if self.state is GameState.LEVEL_CLEAR:
            self.state_timer -= dt
            if self.state_timer <= 0:
                self.score.advance_level()
                self._start_level(self.score.level)
                self.state = GameState.READY
                self.state_timer = READY_SECONDS
            return

        if self.state is GameState.GAME_OVER:
            if input_mod.wants_confirm(raw):
                self.state = GameState.ATTRACT
            return

    def _update_playing(self, dt: float, raw: RawInput) -> None:
        self.life_elapsed += dt

        direction = input_mod.resolve_direction(raw)
        if direction is not None:
            self.player.queue_direction(direction)
        self.player.update(self.maze, dt)

        self._release_ghosts_if_due()

        phase_changed = self.scatter_clock.update(dt)
        if phase_changed:
            apply_phase_change(self.ghosts, self.scatter_clock.phase)

        for ghost in self.ghosts.values():
            ghost.update(self.maze, dt, self.player, self.ghosts, self.scatter_clock.phase, self.rng)

        self._handle_pellets()
        self._handle_fruit(dt)
        self._handle_ghost_collisions()

        if self.maze.is_complete:
            self.state = GameState.LEVEL_CLEAR
            self.state_timer = LEVEL_CLEAR_SECONDS

    def _release_ghosts_if_due(self) -> None:
        for name, ghost in self.ghosts.items():
            if ghost.mode is not GhostMode.HOUSE:
                continue
            delay = config.GHOST_RELEASE_DELAYS.get(name, 0.0)
            pellet_threshold = config.GHOST_RELEASE_PELLET_COUNTS.get(name, 0)
            if self.life_elapsed >= delay or self.maze.pellets_eaten >= pellet_threshold:
                ghost.release()

    def _handle_pellets(self) -> None:
        col, row = self.player.tile
        eaten = self.maze.eat_at(col, row)
        if eaten == "pellet":
            self.score.add_pellet()
        elif eaten == "power":
            self.score.add_power_pellet()
            seconds = levels.frightened_seconds_for_level(self.score.level)
            for ghost in self.ghosts.values():
                ghost.frighten(seconds)

        for threshold in config.FRUIT_PELLET_THRESHOLDS:
            if threshold in self.fruit_thresholds_hit:
                continue
            if self.maze.pellets_eaten >= threshold:
                self.fruit_thresholds_hit.add(threshold)
                self._spawn_fruit()

    def _spawn_fruit(self) -> None:
        exit_col, exit_row = self.maze.player_start
        self.fruit_tile = (exit_col, exit_row)
        self.fruit_active = True
        self.fruit_timer = config.FRUIT_LIFETIME_SECONDS

    def _handle_fruit(self, dt: float) -> None:
        if not self.fruit_active:
            return
        self.fruit_timer -= dt
        if self.fruit_timer <= 0:
            self.fruit_active = False
            return
        if self.player.tile == self.fruit_tile:
            points = levels.fruit_score_for_level(self.score.level)
            self.score.add_fruit(points)
            self.fruit_active = False

    def _handle_ghost_collisions(self) -> None:
        px, py = self.player.x, self.player.y
        for ghost in self.ghosts.values():
            if ghost.mode not in (GhostMode.CHASE, GhostMode.SCATTER, GhostMode.FRIGHTENED):
                continue
            dist_sq = (ghost.x - px) ** 2 + (ghost.y - py) ** 2
            if dist_sq > COLLISION_DISTANCE_SQ:
                continue
            if ghost.mode is GhostMode.FRIGHTENED:
                ghost.get_eaten()
                self.last_ghost_eaten_points = self.score.add_ghost_eaten()
                self.last_ghost_eaten_at = self.life_elapsed
            else:
                self._on_player_caught()
                return

    def _on_player_caught(self) -> None:
        self.score.lose_life()
        self.player.direction = Direction.NONE
        self.state = GameState.DYING
        self.state_timer = DYING_SECONDS

    # -- exit contract ------------------------------------------------------------
    def maybe_exit(self, raw: RawInput) -> None:
        """P1 (button 5) or Esc must exit immediately, from any state."""
        if input_mod.wants_exit(raw):
            self.score.commit_high_score()
            try:
                pygame.quit()
            except Exception:
                pass
            sys.exit(0)

    # -- pygame plumbing ------------------------------------------------------------
    def init_display(self) -> None:
        pygame.init()
        pygame.display.set_caption(config.WINDOW_TITLE)
        self.screen = pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
        self.clock = pygame.time.Clock()
        pygame.joystick.init()
        for i in range(pygame.joystick.get_count()):
            self._add_joystick(i)

    def _add_joystick(self, device_index: int) -> None:
        try:
            joy = pygame.joystick.Joystick(device_index)
            joy.init()
            self.joysticks[joy.get_instance_id()] = joy
        except pygame.error:
            pass  # device vanished between enumeration and init; ignore

    def poll_hardware(self) -> RawInput:
        """Read real pygame events/hardware into a RawInput this frame."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.pressed_keys.add("escape")
            elif event.type == pygame.KEYDOWN:
                self.pressed_keys.add(pygame.key.name(event.key))
            elif event.type == pygame.KEYUP:
                self.pressed_keys.discard(pygame.key.name(event.key))
            elif event.type == pygame.JOYBUTTONDOWN:
                self.pressed_buttons.add(event.button)
            elif event.type == pygame.JOYBUTTONUP:
                self.pressed_buttons.discard(event.button)
            elif event.type == pygame.JOYDEVICEADDED:
                self._add_joystick(event.device_index)
            elif event.type == pygame.JOYDEVICEREMOVED:
                self.joysticks.pop(event.instance_id, None)

        axes = []
        for joy in self.joysticks.values():
            try:
                if joy.get_numaxes() >= 2:
                    axes.append(
                        (joy.get_axis(config.JOYSTICK_AXIS_X), joy.get_axis(config.JOYSTICK_AXIS_Y))
                    )
            except pygame.error:
                continue  # disconnected mid-frame; skip it this frame

        return RawInput(
            axes=tuple(axes),
            pressed_keys=frozenset(self.pressed_keys),
            pressed_buttons=frozenset(self.pressed_buttons),
        )

    def run(self) -> None:
        """The real, blocking game loop. Never returns except via exit."""
        from . import render  # imported lazily to keep this module importable headless

        self.init_display()
        while True:
            raw = self.poll_hardware()
            self.maybe_exit(raw)
            dt = self.clock.tick(config.FPS) / 1000.0
            dt = min(dt, 0.25)  # guard against huge stalls tunneling actors through walls
            self.update(dt, raw)
            render.draw_frame(self.screen, self)
            pygame.display.flip()
