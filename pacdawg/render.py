"""Rendering: draws only from :mod:`pacdawg.assets` surfaces, plus HUD text.

This is the one module that turns tile/game state into pixels. It never
draws gameplay art procedurally -- every sprite comes from a PNG loaded
through :mod:`pacdawg.assets`. Only HUD text (score, lives count,
prompts) is drawn with pygame fonts, which is ordinary UI chrome, not
gameplay art, and unaffected by an art swap.
"""
from __future__ import annotations

from typing import Tuple

import pygame

from . import assets, config
from .entities import Direction
from .game import Game, GameState
from .ghosts import Ghost, GhostMode
from .maze import Maze

BACKGROUND_COLOR = (0, 0, 0)
HUD_TEXT_COLOR = (255, 255, 255)
HUD_ACCENT_COLOR = (255, 210, 90)

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


def _draw_maze(screen, maze: Maze) -> None:
    wall_sprite = assets.get("wall")
    gate_sprite = assets.get("gate")
    pellet_sprite = assets.get("pellet")
    power_sprite = assets.get("power_pellet")

    for col, row in maze.walls:
        x, y = tile_to_pixel(col, row)
        screen.blit(wall_sprite, (round(x), round(y)))
    for col, row in maze.gates:
        x, y = tile_to_pixel(col, row)
        screen.blit(gate_sprite, (round(x), round(y)))
    for col, row in maze.pellets:
        _blit_centered(screen, pellet_sprite, col, row)
    for col, row in maze.power_pellets:
        _blit_centered(screen, power_sprite, col, row)


def _anim_frame(total_time: float) -> int:
    return 1 + int(total_time / _ANIM_INTERVAL) % 2


def _draw_scotty(screen, game: Game, total_time: float) -> None:
    frame = _anim_frame(total_time)
    facing_name = _DIRECTION_NAMES[game.player.facing]
    sprite = assets.get(f"scotty_{facing_name}_{frame}")
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


def _center_text(screen, font, text, color, y_offset) -> None:
    surface = font.render(text, True, color)
    rect = surface.get_rect(center=(config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT // 2 + y_offset))
    screen.blit(surface, rect)


def _draw_hud(screen, game: Game) -> None:
    small = _font(20)
    big = _font(30)

    score_surface = small.render(f"SCORE {game.score.score:06d}", True, HUD_TEXT_COLOR)
    screen.blit(score_surface, (16, 10))

    high_surface = small.render(f"HIGH {game.score.high_score:06d}", True, HUD_ACCENT_COLOR)
    high_rect = high_surface.get_rect(midtop=(config.SCREEN_WIDTH // 2, 10))
    screen.blit(high_surface, high_rect)

    level_surface = small.render(f"LEVEL {game.score.level}", True, HUD_TEXT_COLOR)
    level_rect = level_surface.get_rect(topright=(config.SCREEN_WIDTH - 16, 10))
    screen.blit(level_surface, level_rect)

    life_icon = assets.get("life_icon")
    for i in range(max(0, game.score.lives - 1)):
        x = 16 + i * (life_icon.get_width() + 6)
        y = config.SCREEN_HEIGHT - life_icon.get_height() - 4
        screen.blit(life_icon, (x, y))

    if game.state is GameState.ATTRACT:
        _center_text(screen, big, "PACDAWG", HUD_ACCENT_COLOR, -20)
        _center_text(screen, small, "PRESS START", HUD_TEXT_COLOR, 20)
    elif game.state is GameState.READY:
        _center_text(screen, big, "READY!", HUD_ACCENT_COLOR, 0)
    elif game.state is GameState.GAME_OVER:
        _center_text(screen, big, "GAME OVER", HUD_ACCENT_COLOR, -20)
        _center_text(screen, small, "PRESS START", HUD_TEXT_COLOR, 20)


def draw_frame(screen, game: Game) -> None:
    """Render one full frame from the current game state."""
    total_time = pygame.time.get_ticks() / 1000.0
    screen.fill(BACKGROUND_COLOR)
    _draw_maze(screen, game.maze)
    _draw_fruit(screen, game)
    if game.state is not GameState.ATTRACT:
        _draw_scotty(screen, game, total_time)
        for ghost in game.ghosts.values():
            _draw_ghost(screen, ghost, total_time)
    _draw_hud(screen, game)
