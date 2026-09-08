"""Rendering: draws only from :mod:`pacdawg.assets` surfaces, plus HUD text.

This is the one module that turns tile/game state into pixels. It never
draws gameplay art procedurally -- every sprite comes from a PNG loaded
through :mod:`pacdawg.assets`. Only HUD text (score, lives count,
prompts) is drawn with pygame fonts, which is ordinary UI chrome, not
gameplay art, and unaffected by an art swap.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Tuple

import pygame

from . import assets, config, levels
from .entities import Direction
from .game import (
    ACTIVE_STATES, DYING_SECONDS, LEVEL_CLEAR_SECONDS, READY_SECONDS,
    Game, GameState, MENU_ITEMS, PAUSE_ITEMS, RESULT_ITEMS,
)
from .ghosts import Ghost, GhostMode
from .maze import Maze

BACKGROUND_COLOR = (0, 0, 0)
HUD_TEXT_COLOR = (255, 255, 255)
HUD_ACCENT_COLOR = (255, 210, 90)
HUD_DIM_COLOR = (150, 150, 150)
UI_PANEL_COLOR = (8, 10, 16)
UI_RULE_COLOR = (45, 62, 91)
UI_MUTED_COLOR = (182, 186, 196)
UI_ROW_WIDTH = 392
UI_ROW_HEIGHT = 50
POWER_COLOR = (120, 194, 255)
CAUGHT_COLOR = (248, 128, 128)
POWER_FEEDBACK_SECONDS = 1.0
COMBO_FEEDBACK_SECONDS = 1.2
LIFE_FEEDBACK_SECONDS = 1.8

# Ghost display colors/roles for the attract screen's cast roster --
# matches the sprite colors declared in tools/generate_placeholders.py.
GHOST_DISPLAY_ORDER = ("gates", "hunt", "wean", "doherty")
GHOST_DISPLAY_COLORS = {
    "gates": (248, 104, 104),
    "hunt": (255, 128, 200),
    "wean": (64, 200, 220),
    "doherty": (240, 150, 60),
}
GHOST_ROLE_TEXT = {
    "gates": "DIRECT CHASER",
    "hunt": "AMBUSHER",
    "wean": "FLANKER",
    "doherty": "SHY RETREATER",
}
_ANIM_INTERVAL = 0.12

_DIRECTION_NAMES = {
    Direction.UP: "up",
    Direction.DOWN: "down",
    Direction.LEFT: "left",
    Direction.RIGHT: "right",
    Direction.NONE: "right",
}

_font_cache = {}


def _font(size: int) -> "pygame.font.Font":
    if size not in _font_cache:
        _font_cache[size] = pygame.font.Font(None, size)
    return _font_cache[size]


def tile_to_pixel(col: float, row: float) -> Tuple[float, float]:
    x = config.MAZE_OFFSET_X + col * config.TILE_SIZE
    y = config.MAZE_OFFSET_Y + row * config.TILE_SIZE
    return x, y


def _blit_centered(screen, surface, col: float, row: float) -> None:
    x, y = tile_to_pixel(col, row)
    rect = surface.get_rect(
        center=(round(x + config.TILE_SIZE / 2), round(y + config.TILE_SIZE / 2))
    )
    screen.blit(surface, rect)


@lru_cache(maxsize=4)
def _maze_structure(walls, gates, wall_sprite, gate_sprite):
    """Cache immutable geometry, not mutable pellets or game objects."""
    surface = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.SRCALPHA)
    for tiles, sprite in ((walls, wall_sprite), (gates, gate_sprite)):
        for col, row in tiles:
            x, y = tile_to_pixel(col, row)
            surface.blit(sprite, (round(x), round(y)))
    return surface


def _draw_maze(screen, maze: Maze) -> None:
    screen.blit(_maze_structure(frozenset(maze.walls), frozenset(maze.gates),
                               assets.get("wall"), assets.get("gate")), (0, 0))
    pellet_sprite = assets.get("pellet")
    power_sprite = assets.get("power_pellet")

    for col, row in maze.pellets:
        _blit_centered(screen, pellet_sprite, col, row)
    for col, row in maze.power_pellets:
        _blit_centered(screen, power_sprite, col, row)


def _anim_frame(total_time: float) -> int:
    return 1 + int(total_time / _ANIM_INTERVAL) % 2


def _draw_scotty(screen, game: Game, total_time: float) -> None:
    phase = game.paused_state or game.state
    frame = game.player.chomp_frame if phase in (GameState.PLAYING, GameState.DEMO) else 1
    facing_name = _DIRECTION_NAMES[game.player.facing]
    sprite = assets.get(f"scotty_{facing_name}_{frame}")
    if phase is GameState.DYING:
        elapsed = DYING_SECONDS - game.state_timer
        sprite = _faded(sprite, min(7, int(elapsed / DYING_SECONDS * 8)))
    _blit_centered(screen, sprite, game.player.x, game.player.y)


def _draw_ghost(screen, ghost: Ghost, total_time: float) -> None:
    frame = _anim_frame(total_time)
    if ghost.mode is GhostMode.EATEN:
        direction_name = _DIRECTION_NAMES.get(ghost.direction, "down")
        sprite = assets.get(f"eyes_{direction_name}")
    elif ghost.mode is GhostMode.FRIGHTENED:
        if ghost.is_flashing:
            sprite = assets.get(f"ghost_frightened_flash_{frame}")
        else:
            sprite = assets.get(f"ghost_frightened_{frame}")
    else:
        sprite = assets.get(f"ghost_{ghost.name}_{frame}")
    _blit_centered(screen, sprite, ghost.x, ghost.y)


def _draw_fruit(screen, game: Game) -> None:
    if not game.fruit_active or game.fruit_tile is None:
        return
    index = (game.score.level - 1) % 8
    sprite = assets.get(f"fruit_{index}")
    col, row = game.fruit_tile
    _blit_centered(screen, sprite, col, row)


def _center_text_at(screen, font, text, color, y: int) -> None:
    surface = _font_text(font, text, color)
    rect = surface.get_rect(center=(config.SCREEN_WIDTH // 2, y))
    screen.blit(surface, rect)


def _draw_menu_item(screen, font, text, color, y: int, selected: bool) -> None:
    """Stable geometry and type; the inset marker makes focus non-color-only."""
    surface = _font_text(font, text, (20, 16, 8) if selected else color)
    rect = surface.get_rect(center=(config.SCREEN_WIDTH // 2, y))
    bar = pygame.Rect(0, 0, UI_ROW_WIDTH, UI_ROW_HEIGHT)
    bar.center = rect.center
    if selected:
        pygame.draw.rect(screen, HUD_ACCENT_COLOR, bar, border_radius=5)
        sprite = _portrait(assets.get("scotty_right_1"), 28)
        screen.blit(sprite, sprite.get_rect(center=(bar.left + 28, y)))
    else:
        pygame.draw.line(screen, UI_RULE_COLOR, (bar.left, bar.bottom), (bar.right, bar.bottom))
    screen.blit(surface, rect)


@lru_cache(maxsize=16)
def _portrait(sprite, size: int):
    """Nearest-neighbor UI scaling only; never changes source gameplay art."""
    return pygame.transform.scale(sprite, (size, size))

@lru_cache(maxsize=32)
def _faded(sprite, step: int):
    surface = sprite.copy()
    surface.set_alpha(255 - step * 28)
    return surface


@lru_cache(maxsize=256)
def _font_text(font, text: str, color):
    """Bound score/event text too; no unbounded per-score surface dictionary."""
    return font.render(text, True, color)


@lru_cache(maxsize=8)
def _veil(width: int, height: int, alpha: int):
    surface = pygame.Surface((width, height), pygame.SRCALPHA)
    surface.fill((0, 0, 0, alpha))
    return surface


@lru_cache(maxsize=2)
def _menu_background(wall_sprite):
    # Keyed by the loaded wall surface, so asset cache reloads invalidate it.
    surface = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    surface.fill(BACKGROUND_COLOR)
    _draw_maze(surface, levels.build_maze(1))
    surface.blit(_veil(config.SCREEN_WIDTH, config.SCREEN_HEIGHT, 165), (0, 0))
    return surface


def clear_caches() -> None:
    """Release display/font resources before SDL teardown (also used by tests)."""
    _font_cache.clear()
    _portrait.cache_clear()
    _veil.cache_clear()
    _menu_background.cache_clear()
    _maze_structure.cache_clear()
    _faded.cache_clear()
    _font_text.cache_clear()


def _panel(screen, rect) -> None:
    pygame.draw.rect(screen, UI_PANEL_COLOR, rect, border_radius=8)
    pygame.draw.rect(screen, UI_RULE_COLOR, rect, width=1, border_radius=8)


def _text_at(screen, text, size, color, center) -> None:
    surface = _font_text(_font(size), text, color)
    screen.blit(surface, surface.get_rect(center=center))


def _controls(game: Game):
    return ("START", "B / P1") if game.using_gamepad else ("ENTER / SPACE", "ESC")


def _navigation_hint(game: Game) -> str:
    return "STICK UP / DOWN" if game.using_gamepad else "UP / DOWN  or  W / S"


def _maze_label(level: int) -> str:
    count = len(config.DIFFICULTY_BY_LEVEL)
    tier = min(max(1, level), count)
    return f"{levels.name_for_level(level).upper()}  /  TIER {tier} OF {count}"


def _draw_attract_screen(screen, game: Game, total_time: float) -> None:
    screen.blit(_menu_background(assets.get("wall")), (0, 0))
    _panel(screen, (116, 32, 568, 544))
    _center_text_at(screen, _font(68), "PACDAWG", HUD_ACCENT_COLOR, 82)
    _center_text_at(screen, _font(26), f"HIGH SCORE  {game.score.high_score:06d}", UI_MUTED_COLOR, 130)

    cast = ("scotty", *GHOST_DISPLAY_ORDER)
    for i, name in enumerate(cast):
        x = 208 + i * 96
        key = "scotty_right_1" if name == "scotty" else f"ghost_{name}_1"
        sprite = _portrait(assets.get(key), 40)
        screen.blit(sprite, sprite.get_rect(center=(x, 198)))
        color = GHOST_DISPLAY_COLORS.get(name, HUD_TEXT_COLOR)
        _text_at(screen, name.upper(), 22, color, (x, 236))

    for i, item in enumerate(MENU_ITEMS):
        _draw_menu_item(screen, _font(32), item, HUD_TEXT_COLOR, 306 + i * 62, i == game.menu_index)

    context = (_maze_label(1), "Controls, ghost personalities and scoring.",
               "Return to the arcade gallery.")[game.menu_index]
    _text_at(screen, context, 22, UI_MUTED_COLOR, (400, 474))
    select, back = _controls(game)
    nav = _navigation_hint(game)
    _center_text_at(screen, _font(24), f"{nav}  Choose", UI_MUTED_COLOR, 508)
    _center_text_at(screen, _font(24), f"{select}  Select     {back}  Gallery", HUD_TEXT_COLOR, 544)


def _draw_how_to_play_screen(screen, game: Game) -> None:
    screen.blit(_menu_background(assets.get("wall")), (0, 0))
    _panel(screen, (92, 24, 616, 552))
    _center_text_at(screen, _font(44), "HOW TO PLAY", HUD_ACCENT_COLOR, 64)
    _text_at(screen, "CONTROLS", 22, UI_MUTED_COLOR, (400, 108))
    controls = (
        ("Either joystick", "Move Scotty"),
        ("Start (not A)", "Select menus"),
        ("B / P1", "Pause / resume"),
    ) if game.using_gamepad else (
        ("Arrows / WASD", "Move Scotty"),
        ("Enter / Space", "Select menus"),
        ("Esc / Backspace", "Pause / resume"),
    )
    for i, (key, action) in enumerate(controls):
        y = 140 + i * 34
        screen.blit(_font_text(_font(26), key, HUD_ACCENT_COLOR), (116, y - 10))
        screen.blit(_font_text(_font(26), action, HUD_TEXT_COLOR), (396, y - 10))
    pygame.draw.line(screen, UI_RULE_COLOR, (116, 242), (684, 242))
    _center_text_at(screen, _font(26), "Clear every pellet to reach the next maze.", HUD_TEXT_COLOR, 274)
    _center_text_at(screen, _font(24), "Power pellets turn ghosts blue. Eat them while you can.", UI_MUTED_COLOR, 304)

    for i, name in enumerate(GHOST_DISPLAY_ORDER):
        x = 196 + i * 136
        sprite = _portrait(assets.get(f"ghost_{name}_1"), 32)
        screen.blit(sprite, sprite.get_rect(center=(x, 356)))
        _text_at(screen, name.upper(), 22, GHOST_DISPLAY_COLORS[name], (x, 390))
        _text_at(screen, GHOST_ROLE_TEXT[name], 20, UI_MUTED_COLOR, (x, 412))

    _center_text_at(screen, _font(24), "Pellet 10 pts     Power pellet 50 pts", HUD_TEXT_COLOR, 452)
    _center_text_at(screen, _font(24), "Ghost chain  200 / 400 / 800 / 1600", HUD_TEXT_COLOR, 478)
    _center_text_at(screen, _font(22), "Extra life at 10,000 points", HUD_ACCENT_COLOR, 504)
    select, back = _controls(game)
    destination = "Back to Pause" if game.paused_state is not None else "Main Menu"
    _center_text_at(screen, _font(24), f"{select} / {back}  {destination}", UI_MUTED_COLOR, 550)


def _draw_pause_screen(screen, game: Game) -> None:
    screen.blit(_veil(config.SCREEN_WIDTH, config.SCREEN_HEIGHT, 110), (0, 0))
    _panel(screen, (168, 84, 464, 432))
    _center_text_at(screen, _font(48), "PAUSED", HUD_ACCENT_COLOR, 128)
    _text_at(screen, _maze_label(game.score.level), 22, UI_MUTED_COLOR, (400, 172))
    for i, item in enumerate(PAUSE_ITEMS):
        _draw_menu_item(screen, _font(32), item, HUD_TEXT_COLOR, 232 + i * 62, i == game.pause_index)
    context = {
        "RESUME": "Continue from this exact moment.",
        "HOW TO PLAY": "Review controls and rules; the run stays paused.",
        "MAIN MENU": "Ends this run; keeps your high score.",
    }[PAUSE_ITEMS[game.pause_index]]
    _text_at(screen, context, 22, UI_MUTED_COLOR, (400, 412))
    select, back = _controls(game)
    # A one-time, restrained prompt fade uses only the pause UI clock.
    # Nothing in the gameplay backdrop depends on elapsed wall time.
    shade = 182 + round(30 * min(1.0, game.pause_ui_time / 0.15))
    _center_text_at(screen, _font(22), f"{select}  Select     {back}  Resume", (shade,) * 3, 462)
    _text_at(screen, f"{_navigation_hint(game)}  Choose", 20, UI_MUTED_COLOR, (400, 488))


def _draw_game_over_screen(screen, game: Game) -> None:
    screen.blit(_veil(config.SCREEN_WIDTH, config.SCREEN_HEIGHT, 110), (0, 0))
    _panel(screen, (152, 82, 496, 450))
    _center_text_at(screen, _font(48), "GAME OVER", HUD_ACCENT_COLOR, 128)
    _text_at(screen, f"LEVEL {game.score.level}  /  {game.maze.name.upper()}", 22, UI_MUTED_COLOR, (400, 166))
    _center_text_at(screen, _font(24), "FINAL SCORE", UI_MUTED_COLOR, 206)
    _center_text_at(screen, _font(56), f"{game.score.score:06d}", HUD_TEXT_COLOR, 246)
    _center_text_at(screen, _font(24), f"HIGH SCORE  {game.score.high_score:06d}", HUD_ACCENT_COLOR, 288)
    for i, item in enumerate(RESULT_ITEMS):
        _draw_menu_item(screen, _font(32), item, HUD_TEXT_COLOR, 348 + i * 62, i == game.result_index)
    context = "Fresh run from The Cut, tier 1." if game.result_index == 0 else "Return to the main menu."
    _text_at(screen, context, 22, UI_MUTED_COLOR, (400, 458))
    select, back = _controls(game)
    _center_text_at(screen, _font(22), f"{select}  Select     {back}  Main Menu", HUD_TEXT_COLOR, 490)
    _text_at(screen, f"{_navigation_hint(game)}  Choose", 20, UI_MUTED_COLOR, (400, 515))


def _draw_hud(screen, game: Game, total_time: float = 0.0, phase=None) -> None:
    phase = phase or game.state
    small = _font(20)

    score_surface = _font_text(small, f"SCORE {game.score.score:06d}", HUD_TEXT_COLOR)
    screen.blit(score_surface, (16, 10))

    if _reward_caption(game) is None:
        high_surface = _font_text(small, f"HIGH {game.score.high_score:06d}", HUD_ACCENT_COLOR)
        high_rect = high_surface.get_rect(midtop=(config.SCREEN_WIDTH // 2, 10))
        screen.blit(high_surface, high_rect)

    if phase is GameState.DEMO:
        # "LEVEL" isn't meaningful for the demo -- a restrained, slowly
        # pulsing "DEMO" tag in the same slot makes it unmistakable this
        # is a self-playing showcase, not a stuck real game.
        pulse_on = int(total_time / 0.5) % 2 == 0
        demo_color = HUD_ACCENT_COLOR if pulse_on else HUD_DIM_COLOR
        demo_surface = _font_text(small, "DEMO", demo_color)
        demo_rect = demo_surface.get_rect(topright=(config.SCREEN_WIDTH - 16, 10))
        screen.blit(demo_surface, demo_rect)
        if _reward_caption(game) is None:
            _text_at(screen, "PACDAWG", 18, HUD_ACCENT_COLOR, (400, 31))
    else:
        level_surface = _font_text(small, f"LEVEL {game.score.level}", HUD_TEXT_COLOR)
        level_rect = level_surface.get_rect(topright=(config.SCREEN_WIDTH - 16, 10))
        screen.blit(level_surface, level_rect)

    life_icon = assets.get("life_icon")
    for i in range(max(0, game.score.lives - 1)):
        x = 16 + i * (life_icon.get_width() + 6)
        y = config.SCREEN_HEIGHT - life_icon.get_height() - 4
        screen.blit(life_icon, (x, y))

    if phase in ACTIVE_STATES:
        hint_font = _font(18)
        pad = game.paused_using_gamepad if game.state is GameState.PAUSED else game.using_gamepad
        back = "B / P1" if pad else "ESC"
        hint_surface = _font_text(hint_font, f"{back}: PAUSE", HUD_DIM_COLOR)
        hint_rect = hint_surface.get_rect(bottomright=(config.SCREEN_WIDTH - 12, config.SCREEN_HEIGHT - 6))
        screen.blit(hint_surface, hint_rect)

def _reward_caption(game: Game):
    age = game.gameplay_time - game.last_ghost_eaten_at
    if game.last_ghost_eaten_points is not None and 0 <= age < COMBO_FEEDBACK_SECONDS:
        return f"+{game.last_ghost_eaten_points}  GHOST CHAIN", HUD_ACCENT_COLOR
    if 0 <= game.gameplay_time - game.last_power_at < POWER_FEEDBACK_SECONDS:
        return "POWER PELLET", POWER_COLOR
    return None


def _draw_feedback(screen, game: Game, phase: GameState) -> None:
    """Read-only, fixed event slots. No particles, RNG, or render-side expiry."""
    now = game.gameplay_time
    power_age = now - game.last_power_at
    if 0 <= power_age < 0.55 and game.last_power_tile is not None:
        x, y = tile_to_pixel(*game.last_power_tile)
        radius = 12 + round(14 * power_age / 0.55)
        pygame.draw.circle(screen, POWER_COLOR, (round(x + 10), round(y + 10)), radius, 1)

    # Temporarily replace the secondary HIGH statistic, not score/level/lives.
    # One larger event caption fits inside the unchanged 40px HUD strip.
    caption = _reward_caption(game)
    if caption is not None:
        _text_at(screen, caption[0], 28, caption[1], (400, 20))

    if 0 <= now - game.last_extra_life_at < LIFE_FEEDBACK_SECONDS:
        _text_at(screen, "+1 LIFE", 22, HUD_ACCENT_COLOR, (400, 590))

    if phase not in (GameState.READY, GameState.DYING, GameState.LEVEL_CLEAR):
        return
    if phase is GameState.READY:
        title, detail, color, duration = "READY!", _maze_label(game.score.level), HUD_ACCENT_COLOR, READY_SECONDS
    elif phase is GameState.LEVEL_CLEAR:
        title, detail, color, duration = "MAZE CLEAR", "NEXT  " + _maze_label(game.score.level + 1), HUD_ACCENT_COLOR, LEVEL_CLEAR_SECONDS
    else:
        remaining = game.score.lives
        detail = f"{remaining} {'life' if remaining == 1 else 'lives'} left" if remaining else "Final score coming up"
        title, color, duration = "CAUGHT", CAUGHT_COLOR, DYING_SECONDS
        x, y = tile_to_pixel(game.player.x, game.player.y)
        elapsed = max(0.0, duration - game.state_timer)
        if elapsed < 0.7:
            pygame.draw.circle(screen, color, (round(x + 10), round(y + 10)), 14 + round(elapsed * 20), 1)
    _panel(screen, (160, 262, 480, 94))
    _text_at(screen, title, 34, color, (400, 287))
    _text_at(screen, detail, 24, HUD_TEXT_COLOR, (400, 324))
    # This line spends the existing phase time; it never delays progression.
    fraction = max(0.0, min(1.0, game.state_timer / duration))
    pygame.draw.line(screen, color, (180, 350), (180 + round(440 * fraction), 350), 2)


def draw_frame(screen, game: Game) -> None:
    """Render one full frame from the current game state."""
    total_time = game.gameplay_time
    screen.fill(BACKGROUND_COLOR)
    if game.state is GameState.ATTRACT:
        _draw_attract_screen(screen, game, total_time)
        return
    if game.state is GameState.HOW_TO_PLAY:
        _draw_how_to_play_screen(screen, game)
        return
    _draw_maze(screen, game.maze)
    _draw_fruit(screen, game)
    _draw_scotty(screen, game, total_time)
    for ghost in game.ghosts.values():
        _draw_ghost(screen, ghost, total_time)
    _draw_hud(screen, game, total_time, game.paused_state)
    _draw_feedback(screen, game, game.paused_state or game.state)
    if game.state is GameState.PAUSED:
        _draw_pause_screen(screen, game)
    elif game.state is GameState.GAME_OVER:
        _draw_game_over_screen(screen, game)
