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

from . import config, demo_ai, input as input_mod, levels
from .entities import Direction, Scotty
from .ghosts import Ghost, GhostMode, ScatterChaseClock, apply_phase_change, create_ghosts
from .input import RawInput
from .maze import Maze
from .score import ScoreBoard

Coord = Tuple[int, int]


class GameState(Enum):
    ATTRACT = auto()  # the main menu
    HOW_TO_PLAY = auto()
    READY = auto()
    PLAYING = auto()
    DYING = auto()
    LEVEL_CLEAR = auto()
    PAUSED = auto()
    GAME_OVER = auto()
    DEMO = auto()  # self-playing attract-mode demo, entered after idling on ATTRACT


READY_SECONDS = 2.0
DYING_SECONDS = 1.5
LEVEL_CLEAR_SECONDS = 2.0
COLLISION_DISTANCE_SQ = 0.36  # ~0.6 tiles: catches near-misses, not just exact overlap

# Main menu entries, in display/selection order.
MENU_START_GAME = "START GAME"
MENU_HOW_TO_PLAY = "HOW TO PLAY"
MENU_EXIT_TO_GALLERY = "EXIT TO GALLERY"
MENU_ITEMS = (MENU_START_GAME, MENU_HOW_TO_PLAY, MENU_EXIT_TO_GALLERY)
PAUSE_ITEMS = ("RESUME", MENU_HOW_TO_PLAY, "MAIN MENU")
RESULT_ITEMS = ("PLAY AGAIN", "MAIN MENU")
ACTIVE_STATES = (GameState.READY, GameState.PLAYING, GameState.DYING, GameState.LEVEL_CLEAR)

# Ghost-house release preference order (Dossier Ch. 2): only the single
# most-preferred ghost still waiting inside accrues a dot counter at a
# time. Gates (Blinky) is never part of this at all.
HOUSE_RELEASE_ORDER = ("hunt", "wean", "doherty")


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
        self.player: Scotty = self._make_player(self.maze, 1)
        self.ghosts: Dict[str, Ghost] = create_ghosts(self.maze, 1)
        self.scatter_clock = ScatterChaseClock(levels.scatter_chase_timetable_for_level(1))
        self.fruit_active = False
        self.fruit_tile: Optional[Coord] = None
        self.fruit_timer = 0.0
        self.fruit_thresholds_hit: Set[int] = set()
        self.life_elapsed = 0.0
        self.last_ghost_eaten_points: Optional[int] = None
        self.last_ghost_eaten_at: float = -999.0
        self.last_power_at = -999.0
        self.last_power_tile: Optional[Coord] = None
        self.last_extra_life_at = -999.0

        # Ghost-house release bookkeeping (Dossier Ch. 2, "Home Sweet Home").
        self.dot_counter_mode = "personal"  # or "global", after a life is lost
        self._house_order_index = 0  # index into HOUSE_RELEASE_ORDER
        self._house_dot_counter = 0
        self._global_dot_counter = 0
        self._time_since_last_pellet = 0.0

        # Cruise Elroy (Gates/Blinky speed-up); unlocked means "allowed to
        # activate" -- true from a fresh level, false after a life is lost
        # until Doherty (the last-preference ghost) leaves the house again.
        self.elroy_unlocked = True

        # Main menu / HOW TO PLAY navigation state.
        self.menu_index = 0
        self._menu_last_direction: Optional[Direction] = None
        self._menu_last_confirm = False
        self.pause_index = 0
        self.result_index = 0
        self.paused_state: Optional[GameState] = None
        self.pause_ui_time = 0.0
        self.paused_using_gamepad = False
        self.gameplay_time = 0.0  # sprite clock: never advances while paused
        self._transition_pending = False
        self._gameplay_direction_blocked = False
        self.using_gamepad = False

        # Attract mode: how long the main menu has sat with no genuine
        # input (see config.DEMO_IDLE_SECONDS and _any_genuine_input()).
        # Reset to 0 every time ATTRACT is (re)entered from anywhere, so
        # it always re-arms for another full idle period. _pre_demo_score
        # holds the real ScoreBoard while a demo is running -- see
        # _enter_demo()/_exit_demo() -- and is None the rest of the time.
        self._menu_idle_seconds = 0.0
        self._pre_demo_score: Optional[ScoreBoard] = None

        # pygame handles, created lazily by run()/init_display()
        self.screen = None
        self.clock = None
        self.joysticks: Dict[int, "pygame.joystick.Joystick"] = {}
        self.pressed_keys: Set[str] = set()
        self._keyboard_direction_order = []
        self.pressed_buttons: Set[int] = set()
        self._buttons_by_joystick: Dict[int, Set[int]] = {}

        # Startup input-residue guard (see config.INPUT_SETTLE_SECONDS):
        # the gallery may hand us a still-held select button, so confirm
        # is ignored for a short settle window. The single "go back"
        # action (P1/Esc/B/Backspace -- see maybe_go_back()) has its own
        # "armed" latch that is true whenever none of those four are
        # currently held, and only lets a back-navigation fire while
        # armed -- so a control already held (at startup, or carried over
        # from a screen it just navigated away from) must be seen
        # released at least once before it can trigger another level
        # change. Defaults to "clean start" here; init_display()
        # re-derives it from real hardware state.
        self._input_settle_remaining = 0.0
        self._back_armed = True

    # -- setup helpers --------------------------------------------------------
    @staticmethod
    def _make_player(maze: Maze, level: int) -> Scotty:
        col, row = maze.player_start
        return Scotty(col, row, levels.pacman_normal_speed(level))

    def new_game(self) -> None:
        self.paused_state = None
        self.gameplay_time = 0.0
        # Preserve even an in-memory best if persistence is unavailable.
        self.score = ScoreBoard(high_score=max(self.score.high_score, self.score.score))
        self.result_index = 0
        self._start_level(1)
        self.state = GameState.READY
        self.state_timer = READY_SECONDS

    def _start_level(self, level: int) -> None:
        self._reset_feedback()
        self.score.level = level
        self.maze = levels.build_maze(level)
        self.player = self._make_player(self.maze, level)
        self.ghosts = create_ghosts(self.maze, level)
        self.scatter_clock = ScatterChaseClock(levels.scatter_chase_timetable_for_level(level))
        self.fruit_active = False
        self.fruit_tile = None
        self.fruit_timer = 0.0
        self.fruit_thresholds_hit = set()
        self.life_elapsed = 0.0
        self.dot_counter_mode = "personal"
        self._house_order_index = 0
        self._house_dot_counter = 0
        self._global_dot_counter = 0
        self._time_since_last_pellet = 0.0
        self.elroy_unlocked = True

    def _reset_positions_same_level(self) -> None:
        self._reset_feedback()
        col, row = self.maze.player_start
        self.player.teleport(col, row, Direction.NONE)
        self.player.speed = levels.pacman_normal_speed(self.score.level)
        for name, ghost in self.ghosts.items():
            start_col, start_row = self.maze.ghost_starts[name]
            ghost.teleport(start_col, start_row, Direction.NONE)
            ghost.mode = GhostMode.HOUSE
            ghost.released = False
            ghost.elroy_stage = 0
        self.scatter_clock = ScatterChaseClock(levels.scatter_chase_timetable_for_level(self.score.level))
        self.life_elapsed = 0.0
        # A lost life switches release logic to the global dot counter
        # (Dossier Ch. 2), and Cruise Elroy reverts until Doherty leaves
        # the house again.
        self.dot_counter_mode = "global"
        self._house_order_index = 0
        self._house_dot_counter = 0
        self._global_dot_counter = 0
        self._time_since_last_pellet = 0.0
        self.elroy_unlocked = False

    def _reset_feedback(self) -> None:
        """One slot per meaningful event, cleared across lives/mazes/runs."""
        self.last_ghost_eaten_points = None
        self.last_ghost_eaten_at = -999.0
        self.last_power_at = -999.0
        self.last_power_tile = None
        self.last_extra_life_at = -999.0

    def _collect_and_collide(self, dt: float) -> bool:
        """Keep reward order/RNG identical; observe a life award before death."""
        lives_before = self.score.lives
        self._handle_pellets()
        self._handle_fruit(dt)
        caught = self._handle_ghost_collisions()
        if self.score.lives > lives_before:
            self.last_extra_life_at = self.gameplay_time
        return caught

    # -- pure per-frame update --------------------------------------------------
    def update(self, dt: float, raw: RawInput) -> None:
        if self._input_settle_remaining > 0.0:
            self._input_settle_remaining = max(0.0, self._input_settle_remaining - dt)

        if raw.pressed_buttons or any(input_mod.axis_direction(x, y) for x, y in raw.axes):
            self.using_gamepad = True
        elif raw.pressed_keys:
            self.using_gamepad = False

        # run() checks back BEFORE update(). Neither navigation nor simulation
        # may see that same transition frame, including the resume frame's dt.
        if self._transition_pending:
            self._transition_pending = False
            return

        if self.state is GameState.PAUSED:
            self.pause_ui_time += dt
            self._update_pause(raw)
            return

        if self.state is GameState.ATTRACT:
            if self._any_genuine_input(raw):
                self._menu_idle_seconds = 0.0
            else:
                self._menu_idle_seconds += dt
                if self._menu_idle_seconds >= config.DEMO_IDLE_SECONDS:
                    self._enter_demo()
                    return
            self._update_menu(raw)
            return

        if self.state is GameState.DEMO:
            if self._any_genuine_input(raw):
                self._exit_demo()
                self._consume_transition_input(raw)
                return
            self.gameplay_time += dt
            self._update_demo(dt)
            return

        if self.state is GameState.HOW_TO_PLAY:
            if self._menu_confirm_pressed(raw):  # also allowed, friendlier than back-only
                self._close_help()
                self._consume_transition_input(raw)
            return

        if self.state in ACTIVE_STATES:
            # Track confirm even during play: a held Start must not activate
            # a result or pause menu reached later.
            self._menu_last_confirm = input_mod.wants_confirm(raw)
            self.gameplay_time += dt
            if self._gameplay_direction_blocked:
                if input_mod.resolve_direction(raw) is None:
                    self._gameplay_direction_blocked = False
                else:
                    raw = RawInput(pressed_buttons=raw.pressed_buttons)

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
                    self.result_index = 0
                    self._consume_transition_input(raw)
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
            direction = self._menu_direction_pressed(raw)
            if direction in (Direction.UP, Direction.DOWN):
                self.result_index = (self.result_index + 1) % len(RESULT_ITEMS)
            if self._menu_confirm_pressed(raw):
                if self.result_index == 0:
                    self.new_game()
                else:
                    self._return_to_menu_abandoning_game()
                self._consume_transition_input(raw)
            return

    # -- main menu / how to play --------------------------------------------------
    def _update_menu(self, raw: RawInput) -> None:
        direction = self._menu_direction_pressed(raw)
        if direction is Direction.UP:
            self.menu_index = (self.menu_index - 1) % len(MENU_ITEMS)
        elif direction is Direction.DOWN:
            self.menu_index = (self.menu_index + 1) % len(MENU_ITEMS)
        if self._menu_confirm_pressed(raw):
            self._activate_menu_item()
            self._consume_transition_input(raw)

    def _consume_transition_input(self, raw: RawInput, skip_update: bool = False) -> None:
        """Seed destination edges from the transition's actual held controls."""
        self._menu_last_confirm = input_mod.wants_confirm(raw)
        self._menu_last_direction = input_mod.resolve_direction(raw)
        self._back_armed = not input_mod.wants_go_back(raw)
        self._gameplay_direction_blocked = self._menu_last_direction is not None
        self._transition_pending = skip_update

    def _pause_game(self) -> None:
        self.paused_state = self.state
        self.paused_using_gamepad = self.using_gamepad
        self.state = GameState.PAUSED
        self.pause_index = 0
        self.pause_ui_time = 0.0

    def _resume_game(self) -> None:
        if self.paused_state is not None:
            self.state = self.paused_state
            self.paused_state = None

    def _update_pause(self, raw: RawInput) -> None:
        direction = self._menu_direction_pressed(raw)
        if direction is Direction.UP:
            self.pause_index = (self.pause_index - 1) % len(PAUSE_ITEMS)
        elif direction is Direction.DOWN:
            self.pause_index = (self.pause_index + 1) % len(PAUSE_ITEMS)
        if self._menu_confirm_pressed(raw):
            item = PAUSE_ITEMS[self.pause_index]
            if item == "RESUME":
                self._resume_game()
            elif item == MENU_HOW_TO_PLAY:
                self.state = GameState.HOW_TO_PLAY
            else:
                self._return_to_menu_abandoning_game()
            self._consume_transition_input(raw)

    def _close_help(self) -> None:
        """Help opened from pause returns there, with the run still frozen."""
        if self.paused_state is not None:
            self.state = GameState.PAUSED
        else:
            self._return_to_menu_abandoning_game()

    def _menu_direction_pressed(self, raw: RawInput) -> Optional[Direction]:
        """Edge-triggered steer: fires only the frame a *new* direction is
        pressed, so holding a direction doesn't rapid-fire through every
        menu entry in a single held press."""
        current = input_mod.resolve_direction(raw)
        pressed = current if (current is not None and current is not self._menu_last_direction) else None
        self._menu_last_direction = current
        return pressed

    def _menu_confirm_pressed(self, raw: RawInput) -> bool:
        """Edge-triggered confirm: fires only the frame confirm is newly
        held, so a single button press can't chain through multiple menu
        transitions (e.g. GAME_OVER -> ATTRACT -> START GAME) in one go.

        Belt-and-braces: also ignored entirely during the brief startup
        settle window (config.INPUT_SETTLE_SECONDS), on top of the
        hardware-state seeding done in init_display(). We still track
        ``_menu_last_confirm`` while settling so a button held through the
        whole window is not misread as a fresh press the instant it ends.
        """
        current = input_mod.wants_confirm(raw)
        settling = self._input_settle_remaining > 0.0
        pressed = current and not self._menu_last_confirm and not settling
        self._menu_last_confirm = current
        return pressed

    def _activate_menu_item(self) -> None:
        item = MENU_ITEMS[self.menu_index]
        if item == MENU_START_GAME:
            self.new_game()
        elif item == MENU_HOW_TO_PLAY:
            self.state = GameState.HOW_TO_PLAY
        elif item == MENU_EXIT_TO_GALLERY:
            self._exit_to_gallery()

    # -- attract-mode demo ----------------------------------------------------------
    def _any_genuine_input(self, raw: RawInput) -> bool:
        """True if a direction, confirm, or back control is physically
        active this frame -- used both to drive the main menu's idle
        timer (config.DEMO_IDLE_SECONDS) and to end the demo the instant
        a visitor touches anything. A drifting/noisy stick at rest must
        not count: resolve_direction() already applies the configured
        deadzone, so only a genuine push registers."""
        return (
            input_mod.resolve_direction(raw) is not None
            or input_mod.wants_confirm(raw)
            or input_mod.wants_go_back(raw)
            or config.BUTTON_A in raw.pressed_buttons
        )

    def _enter_demo(self) -> None:
        """Attract mode: reuse the real game systems -- level setup,
        ghost AI, scatter/chase, Cruise Elroy, ghost-house release,
        pellets, fruit, and collisions, all exactly as in real play --
        driven by a simple self-playing AI (see :mod:`pacdawg.demo_ai`)
        instead of real input, so the demo can never drift out of sync
        with the real game.

        The real ScoreBoard (and the persisted high score it holds) is
        saved aside untouched and swapped for a disposable one seeded
        with the same high score, purely so the demo overlay can keep
        showing it; the disposable one is never committed (see
        _exit_demo()), so the demo can never write the real high score.
        """
        self._pre_demo_score = self.score
        self.score = ScoreBoard(high_score=self._pre_demo_score.high_score)
        self._start_level(1)
        self.state = GameState.DEMO

    def _exit_demo(self) -> None:
        """Leave the demo -- on any input, or on back -- and land on the
        main menu without touching real game state: the demo's
        throwaway score is discarded (never committed), and the real
        ScoreBoard saved by _enter_demo() is restored exactly as it was
        before the demo started."""
        if self._pre_demo_score is not None:
            self.score = self._pre_demo_score
            self._pre_demo_score = None
        self._return_to_menu_abandoning_game()

    def _restart_demo(self) -> None:
        """Bounds the demo: if the demo Scotty is caught, or the demo
        maze is somehow cleared, start a fresh demo scene from scratch
        rather than draining lives into a game-over or advancing levels
        forever. A brand-new disposable ScoreBoard (still seeded from,
        and never written back to, the real high score) keeps the demo
        looking like a clean new attempt rather than a continuation."""
        self.score = ScoreBoard(high_score=self.score.high_score)
        self._start_level(1)

    def _update_demo(self, dt: float) -> None:
        """One demo tick: identical machinery to _update_playing() --
        ghost AI, scatter/chase, Cruise Elroy, ghost-house release,
        pellets, fruit, collisions -- with only two differences, both
        inherent to it being a demo rather than real play: the steering
        source (demo_ai instead of real input) and what happens on
        death/level-clear (_restart_demo() instead of the real
        lives/game-over/level-advance flow)."""
        direction = demo_ai.choose_direction(self.maze, self.player, self.ghosts)
        if direction is not None:
            self.player.queue_direction(direction)

        any_frightened = any(g.mode is GhostMode.FRIGHTENED for g in self.ghosts.values())
        self.player.speed = (
            levels.pacman_frightened_speed(self.score.level)
            if any_frightened
            else levels.pacman_normal_speed(self.score.level)
        )
        self.player.update(self.maze, dt)

        self._release_ghosts_if_due()
        self._update_cruise_elroy()

        if not any_frightened:
            phase_changed = self.scatter_clock.update(dt)
            if phase_changed:
                apply_phase_change(self.ghosts, self.scatter_clock.phase)

        for ghost in self.ghosts.values():
            ghost.update(self.maze, dt, self.player, self.ghosts, self.scatter_clock.phase, self.rng)

        if self._collect_and_collide(dt):
            self._restart_demo()
            return

        if self.maze.is_complete:
            self._restart_demo()

    def _update_playing(self, dt: float, raw: RawInput) -> None:
        self.life_elapsed += dt
        self._time_since_last_pellet += dt

        direction = input_mod.resolve_direction(raw)
        if direction is not None:
            self.player.queue_direction(direction)
        # Pac-Man is documented to move faster while frightened is active.
        any_frightened = any(g.mode is GhostMode.FRIGHTENED for g in self.ghosts.values())
        self.player.speed = (
            levels.pacman_frightened_speed(self.score.level)
            if any_frightened
            else levels.pacman_normal_speed(self.score.level)
        )
        self.player.update(self.maze, dt)

        self._release_ghosts_if_due()
        self._update_cruise_elroy()

        # The scatter/chase timer is documented to pause entirely while
        # any ghost is frightened, resuming once frightened mode ends.
        if not any_frightened:
            phase_changed = self.scatter_clock.update(dt)
            if phase_changed:
                apply_phase_change(self.ghosts, self.scatter_clock.phase)

        for ghost in self.ghosts.values():
            ghost.update(self.maze, dt, self.player, self.ghosts, self.scatter_clock.phase, self.rng)

        if self._collect_and_collide(dt):
            self._on_player_caught()
            return

        if self.maze.is_complete:
            self.state = GameState.LEVEL_CLEAR
            self.state_timer = LEVEL_CLEAR_SECONDS

    def _release_ghosts_if_due(self) -> None:
        gates = self.ghosts.get("gates")
        if gates is not None and self._house_ready(gates):
            gates.release()  # Blinky/Gates is never subject to house-release logic

        if self.dot_counter_mode == "personal":
            self._release_via_personal_counter()
        else:
            self._release_via_global_counter()
        self._release_via_timeout()

    @staticmethod
    def _house_ready(ghost: Ghost) -> bool:
        """True if a ghost is in the house and not still dwelling after a
        revival (see config.GHOST_REVIVE_DWELL_SECONDS)."""
        return ghost.mode is GhostMode.HOUSE and ghost.house_dwell_remaining <= 0.0

    def _release_via_personal_counter(self) -> None:
        while self._house_order_index < len(HOUSE_RELEASE_ORDER):
            name = HOUSE_RELEASE_ORDER[self._house_order_index]
            ghost = self.ghosts.get(name)
            if ghost is None or ghost.mode is not GhostMode.HOUSE:
                self._house_order_index += 1
                self._house_dot_counter = 0
                continue
            if not self._house_ready(ghost):
                break  # still dwelling after a revival; try again later
            limit = levels.personal_dot_limit(self.score.level, name, self.maze.total_pellets)
            if self._house_dot_counter >= limit:
                ghost.release()
                self._house_order_index += 1
                self._house_dot_counter = 0
                continue
            break

    def _release_via_global_counter(self) -> None:
        for name in HOUSE_RELEASE_ORDER:
            ghost = self.ghosts.get(name)
            if ghost is None or not self._house_ready(ghost):
                continue
            threshold = levels.global_dot_counter_threshold(
                name, self.maze.total_pellets, level=self.score.level
            )
            if self._global_dot_counter >= threshold:
                ghost.release()
                if name == "doherty":
                    # Deactivates the global counter; personal counters
                    # resume from here (Dossier Ch. 2).
                    self.dot_counter_mode = "personal"
                    self._house_order_index = len(HOUSE_RELEASE_ORDER)
                    self._house_dot_counter = 0

    def _release_via_timeout(self) -> None:
        """Anti-starvation: force a release if Scotty stalls too long."""
        timeout = levels.ghost_release_timeout_seconds(self.score.level)
        if self._time_since_last_pellet < timeout:
            return
        for name in HOUSE_RELEASE_ORDER:
            ghost = self.ghosts.get(name)
            if ghost is not None and self._house_ready(ghost):
                ghost.release()
                self._time_since_last_pellet = 0.0
                break

    def _update_cruise_elroy(self) -> None:
        """Gates (Blinky) speeds up as pellets run low, and once active
        also targets Scotty directly during scatter (Dossier Ch. 4)."""
        gates = self.ghosts.get("gates")
        if gates is None:
            return
        if not self.elroy_unlocked:
            doherty = self.ghosts.get("doherty")
            if doherty is not None and doherty.released:
                self.elroy_unlocked = True
            else:
                return
        stage1, stage2 = levels.elroy_thresholds_for_level(self.score.level, self.maze.total_pellets)
        remaining = self.maze.pellets_remaining
        if remaining <= stage2:
            gates.elroy_stage = 2
        elif remaining <= stage1:
            gates.elroy_stage = 1

    def _handle_pellets(self) -> None:
        col, row = self.player.tile
        eaten = self.maze.eat_at(col, row)
        if eaten == "pellet":
            self.score.add_pellet()
            self.player.pause(config.DOT_EAT_PAUSE_SECONDS)
            self._on_dot_eaten()
        elif eaten == "power":
            self.last_power_at = self.gameplay_time
            self.last_power_tile = (col, row)
            self.score.add_power_pellet()
            self.player.pause(config.POWER_PELLET_EAT_PAUSE_SECONDS)
            self._on_dot_eaten()
            seconds = levels.frightened_seconds_for_level(self.score.level)
            flashes = levels.frightened_flashes_for_level(self.score.level)
            for ghost in self.ghosts.values():
                ghost.frighten(seconds, flashes)

        first_trigger, second_trigger = levels.fruit_pellet_triggers(self.maze.total_pellets)
        for threshold in (first_trigger, second_trigger):
            if threshold in self.fruit_thresholds_hit:
                continue
            if self.maze.pellets_eaten >= threshold:
                self.fruit_thresholds_hit.add(threshold)
                self._spawn_fruit()

    def _on_dot_eaten(self) -> None:
        """Feed whichever ghost-house release counter is currently active,
        and reset the anti-starvation timer (Dossier Ch. 2)."""
        self._time_since_last_pellet = 0.0
        if self.dot_counter_mode == "personal":
            if self._house_order_index < len(HOUSE_RELEASE_ORDER):
                self._house_dot_counter += 1
        else:
            self._global_dot_counter += 1

    def _spawn_fruit(self) -> None:
        exit_col, exit_row = self.maze.player_start
        self.fruit_tile = (exit_col, exit_row)
        self.fruit_active = True
        low, high = config.FRUIT_LIFETIME_SECONDS_RANGE
        self.fruit_timer = self.rng.uniform(low, high)

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

    def _handle_ghost_collisions(self) -> bool:
        """Detect and resolve collisions between the player and every
        hunting/frightened ghost. Eating a frightened ghost is resolved
        right here (identical for real play and the demo); getting
        caught by a hunting ghost is *not* -- this returns True and lets
        the caller decide what "caught" means, since that is the one
        thing that legitimately differs between real play (lose a life)
        and the demo (restart cleanly, see Game._update_demo)."""
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
                self.last_ghost_eaten_at = self.gameplay_time
            else:
                return True
        return False

    def _on_player_caught(self) -> None:
        self.score.lose_life()
        self.player.direction = Direction.NONE
        self.state = GameState.DYING
        self.state_timer = DYING_SECONDS

    # -- back-one-level contract ---------------------------------------------------
    def maybe_go_back(self, raw: RawInput) -> None:
        """B/P1/Esc/Backspace pause or resume a run. Help returns to its
        parent (pause or root menu); result/demo return to the root menu.
        Only the root menu exits.

        Track the raw held signal across every screen and startup. A
        release is required before another back edge, and update() must
        consume the transition frame before doing anything on its destination.
        """
        active = input_mod.wants_go_back(raw)
        was_armed = self._back_armed
        self._back_armed = not active

        if not (active and was_armed):
            return

        if self.state is GameState.ATTRACT:
            self._exit_to_gallery()
        elif self.state is GameState.DEMO:
            self._exit_demo()
        elif self.state in ACTIVE_STATES:
            self._pause_game()
        elif self.state is GameState.PAUSED:
            self._resume_game()
        elif self.state is GameState.HOW_TO_PLAY:
            self._close_help()
        else:
            self._return_to_menu_abandoning_game()
        self._consume_transition_input(raw, skip_update=True)

    def _return_to_menu_abandoning_game(self) -> None:
        """Shared "go back to the main menu" landing spot for every
        non-ATTRACT, non-DEMO state: a game in progress (if any) is
        treated as abandoned rather than paused -- the high score is
        committed (harmless no-op if it isn't a new one) so nothing
        earned is lost, and the menu comes up cleanly with its idle
        timer re-armed for another full config.DEMO_IDLE_SECONDS.
        new_game() always fully reinitializes score/level/ghosts from
        scratch, so START GAME after this is guaranteed to be a
        genuinely fresh run; nothing about the abandoned game leaks
        forward."""
        self.score.commit_high_score()
        self.paused_state = None
        self.menu_index = 1 if self.state is GameState.HOW_TO_PLAY else 0
        self.state = GameState.ATTRACT
        self._menu_idle_seconds = 0.0

    def _exit_to_gallery(self) -> None:
        """The top-level exit path: back from the main menu, or the
        menu's EXIT TO GALLERY entry. Commits the high score, then quits
        via sys.exit(0) -- the documented contract the launcher relies
        on to reclaim control."""
        self.score.commit_high_score()
        from . import render
        render.clear_caches()
        try:
            pygame.quit()
        except Exception:
            pass
        sys.exit(0)

    # -- pygame plumbing ------------------------------------------------------------
    def init_display(self) -> None:
        pygame.init()
        pygame.display.set_caption(config.WINDOW_TITLE)
        # SCALED keeps the game rendering at its logical 800x600 while SDL
        # letterboxes that onto whatever panel is fitted, so the cabinet and a
        # laptop of any resolution both get a correct picture. FULLSCREEN is the
        # default because that is how the cabinet is played; PACDAWG_WINDOWED
        # gives a window for development.
        flags = pygame.SCALED
        if not config.windowed_requested():
            flags |= pygame.FULLSCREEN
        self.screen = pygame.display.set_mode(
            (config.SCREEN_WIDTH, config.SCREEN_HEIGHT), flags
        )
        self.clock = pygame.time.Clock()
        pygame.joystick.init()
        for i in range(pygame.joystick.get_count()):
            self._add_joystick(i)
        # The gallery is left with button 1/A (or Enter) still physically
        # held -- it is how the visitor *selected* PacDawg -- and SDL can
        # surface that held state to us the instant we open the
        # joystick/keyboard (as a synthetic "just pressed" event or as
        # live device state). Flush anything already queued, then seed our
        # own pressed-state from the real hardware so that held control
        # must be released once before it counts as a fresh press, no
        # matter which of those two ways it would otherwise reach us.
        pygame.event.clear()
        self._seed_input_state_from_hardware()

    def _seed_input_state_from_hardware(self) -> None:
        """Prime pressed_keys/pressed_buttons (and the menu's edge- and
        exit-arming latches) from what is *actually* physically held right
        now, instead of an empty set. See init_display()."""
        pressed_keys = set()
        try:
            keys = pygame.key.get_pressed()
            for key_const in range(len(keys)):
                if keys[key_const]:
                    pressed_keys.add(pygame.key.name(key_const))
        except Exception:
            pass  # headless/dummy video driver may not support key state
        pressed_buttons = set()
        self._buttons_by_joystick.clear()
        for instance_id, joy in self.joysticks.items():
            try:
                held = set()
                for button in range(joy.get_numbuttons()):
                    if joy.get_button(button):
                        held.add(button)
                self._buttons_by_joystick[instance_id] = held
                pressed_buttons.update(held)
            except pygame.error:
                continue  # device vanished mid-enumeration; ignore
        self._seed_input_state(pressed_keys, pressed_buttons)

    def _seed_input_state(self, pressed_keys, pressed_buttons) -> None:
        """Prime our tracked pressed-state and the startup guards from an
        explicit already-held set. Split out from
        _seed_input_state_from_hardware() so the "launched with a button
        already held" scenario is directly testable without a real
        display or joystick device.
        """
        self.pressed_keys = set(pressed_keys)
        self._keyboard_direction_order.clear()
        self.pressed_buttons = set(pressed_buttons)
        seeded = RawInput(
            axes=self._read_axes(),
            pressed_keys=frozenset(self.pressed_keys),
            pressed_buttons=frozenset(self.pressed_buttons),
        )
        self._menu_last_confirm = input_mod.wants_confirm(seeded)
        self._menu_last_direction = input_mod.resolve_direction(seeded)
        self._back_armed = not input_mod.wants_go_back(seeded)
        self._input_settle_remaining = config.INPUT_SETTLE_SECONDS
        self.using_gamepad = bool(self.joysticks or pressed_buttons)

    def _read_axes(self) -> tuple:
        axes = []
        for joy in self.joysticks.values():
            try:
                if joy.get_numaxes() >= 2:
                    axes.append(
                        (joy.get_axis(config.JOYSTICK_AXIS_X), joy.get_axis(config.JOYSTICK_AXIS_Y))
                    )
            except pygame.error:
                continue  # disconnected mid-frame; skip it this frame
        return tuple(axes)

    def _add_joystick(self, device_index: int) -> None:
        try:
            joy = pygame.joystick.Joystick(device_index)
            joy.init()
            self.joysticks[joy.get_instance_id()] = joy
            self.using_gamepad = True
        except pygame.error:
            pass  # device vanished between enumeration and init; ignore

    def poll_hardware(self) -> RawInput:
        """Read real pygame events/hardware into a RawInput this frame."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.pressed_keys.add("escape")
            elif event.type == pygame.KEYDOWN:
                key = pygame.key.name(event.key)
                if key not in self.pressed_keys and key in input_mod.KEY_DIRECTIONS:
                    self._keyboard_direction_order.append(key)
                self.pressed_keys.add(key)
            elif event.type == pygame.KEYUP:
                key = pygame.key.name(event.key)
                self.pressed_keys.discard(key)
                if key in self._keyboard_direction_order:
                    self._keyboard_direction_order.remove(key)
            elif event.type == pygame.JOYBUTTONDOWN:
                self._buttons_by_joystick.setdefault(event.instance_id, set()).add(event.button)
            elif event.type == pygame.JOYBUTTONUP:
                self._buttons_by_joystick.setdefault(event.instance_id, set()).discard(event.button)
            elif event.type == pygame.JOYDEVICEADDED:
                self._add_joystick(event.device_index)
            elif event.type == pygame.JOYDEVICEREMOVED:
                self.joysticks.pop(event.instance_id, None)
                self._buttons_by_joystick.pop(event.instance_id, None)
                if not self.joysticks:
                    self.using_gamepad = False

        self.pressed_buttons = set().union(*self._buttons_by_joystick.values())
        return RawInput(
            axes=self._read_axes(),
            pressed_keys=frozenset(self.pressed_keys),
            pressed_buttons=frozenset(self.pressed_buttons),
            keyboard_order=tuple(self._keyboard_direction_order),
        )

    def run(self) -> None:
        """The real, blocking game loop. Never returns except via exit."""
        from . import render  # imported lazily to keep this module importable headless

        self.init_display()
        while True:
            raw = self.poll_hardware()
            self.maybe_go_back(raw)
            dt = self.clock.tick(config.FPS) / 1000.0
            dt = min(dt, 0.25)  # guard against huge stalls tunneling actors through walls
            self.update(dt, raw)
            render.draw_frame(self.screen, self)
            pygame.display.flip()
