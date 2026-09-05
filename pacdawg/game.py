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
    ATTRACT = auto()  # the main menu
    HOW_TO_PLAY = auto()
    READY = auto()
    PLAYING = auto()
    DYING = auto()
    LEVEL_CLEAR = auto()
    GAME_OVER = auto()


READY_SECONDS = 2.0
DYING_SECONDS = 1.5
LEVEL_CLEAR_SECONDS = 2.0
COLLISION_DISTANCE_SQ = 0.36  # ~0.6 tiles: catches near-misses, not just exact overlap

# Main menu entries, in display/selection order.
MENU_START_GAME = "START GAME"
MENU_HOW_TO_PLAY = "HOW TO PLAY"
MENU_EXIT_TO_GALLERY = "EXIT TO GALLERY"
MENU_ITEMS = (MENU_START_GAME, MENU_HOW_TO_PLAY, MENU_EXIT_TO_GALLERY)

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

        # pygame handles, created lazily by run()/init_display()
        self.screen = None
        self.clock = None
        self.joysticks: Dict[int, "pygame.joystick.Joystick"] = {}
        self.pressed_keys: Set[str] = set()
        self.pressed_buttons: Set[int] = set()

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
        self.score = ScoreBoard()
        self._start_level(1)
        self.state = GameState.READY
        self.state_timer = READY_SECONDS

    def _start_level(self, level: int) -> None:
        self.score.level = level
        self.maze = levels.build_maze(level)
        self.player = self._make_player(self.maze, level)
        self.ghosts = create_ghosts(self.maze, level)
        self.scatter_clock = ScatterChaseClock(levels.scatter_chase_timetable_for_level(level))
        self.fruit_active = False
        self.fruit_tile = None
        self.fruit_thresholds_hit = set()
        self.life_elapsed = 0.0
        self.dot_counter_mode = "personal"
        self._house_order_index = 0
        self._house_dot_counter = 0
        self._global_dot_counter = 0
        self._time_since_last_pellet = 0.0
        self.elroy_unlocked = True

    def _reset_positions_same_level(self) -> None:
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

    # -- pure per-frame update --------------------------------------------------
    def update(self, dt: float, raw: RawInput) -> None:
        if self._input_settle_remaining > 0.0:
            self._input_settle_remaining = max(0.0, self._input_settle_remaining - dt)

        if self.state is GameState.ATTRACT:
            self._update_menu(raw)
            return

        if self.state is GameState.HOW_TO_PLAY:
            if self._menu_confirm_pressed(raw):  # also allowed, friendlier than back-only
                self.state = GameState.ATTRACT
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
            if self._menu_confirm_pressed(raw):
                self.state = GameState.ATTRACT
                self.menu_index = 0
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

        self._handle_pellets()
        self._handle_fruit(dt)
        self._handle_ghost_collisions()

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
            threshold = levels.global_dot_counter_threshold(name, self.maze.total_pellets)
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

    # -- back-one-level contract ---------------------------------------------------
    def maybe_go_back(self, raw: RawInput) -> None:
        """P1, Esc, Backspace, and button B are all equivalent aliases of
        a single "go back one level" action (this club's cross-game
        arcade contract), used identically from *every* state:

        - From the main menu (ATTRACT), back means exit to the gallery
          (``sys.exit(0)``) -- there is nothing above the menu to go
          back to, so this is still the launcher's documented top-level
          quit path.
        - From every other state -- HOW_TO_PLAY, or any state of a game
          in progress (READY/PLAYING/DYING/LEVEL_CLEAR/GAME_OVER) --
          back returns to the main menu, treating a game in progress as
          abandoned (see _return_to_menu_abandoning_game()).

        So leaving mid-game takes two presses: once back to the menu,
        once more to exit. That is deliberate -- it makes an accidental
        press recoverable instead of instantly dumping a visitor out.

        Edge-triggered with a single armed/disarmed latch tracked
        against the raw physical signal (not against what it currently
        does): it disarms every frame any of the four controls is held
        and re-arms the instant none of them are, regardless of state.
        That one mechanism guards two residue problems: (1) a control
        already held over from process startup (see init_display())
        can't cause an instant unwanted level change, and (2) holding
        the same physical control through a state transition (e.g.
        gameplay -> menu) can't chain straight through a *second*
        transition (menu -> exit) in the same hold -- it must be seen
        released and pressed again. This matters more now than it used
        to: a chained double-transition here would take a visitor from
        gameplay straight out of the game, which is exactly what the
        two-press design exists to prevent.
        """
        active = input_mod.wants_go_back(raw)
        was_armed = self._back_armed
        self._back_armed = not active

        if not (active and was_armed):
            return

        if self.state is GameState.ATTRACT:
            self._exit_to_gallery()
        else:
            self._return_to_menu_abandoning_game()

    def _return_to_menu_abandoning_game(self) -> None:
        """Shared "go back to the main menu" landing spot for every
        non-ATTRACT state: a game in progress (if any) is treated as
        abandoned rather than paused -- the high score is committed
        (harmless no-op if it isn't a new one) so nothing earned is
        lost, and the menu comes up cleanly. new_game() always fully
        reinitializes score/level/ghosts from scratch, so START GAME
        after this is guaranteed to be a genuinely fresh run; nothing
        about the abandoned game leaks forward."""
        self.score.commit_high_score()
        self.state = GameState.ATTRACT
        self.menu_index = 0

    def _exit_to_gallery(self) -> None:
        """The top-level exit path: back from the main menu, or the
        menu's EXIT TO GALLERY entry. Commits the high score, then quits
        via sys.exit(0) -- the documented contract the launcher relies
        on to reclaim control."""
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
        for joy in self.joysticks.values():
            try:
                for button in range(joy.get_numbuttons()):
                    if joy.get_button(button):
                        pressed_buttons.add(button)
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

        return RawInput(
            axes=self._read_axes(),
            pressed_keys=frozenset(self.pressed_keys),
            pressed_buttons=frozenset(self.pressed_buttons),
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
