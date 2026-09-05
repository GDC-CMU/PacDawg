"""Single point of access for all gameplay art.

Every PNG the game draws is declared once in :data:`SPRITE_SPECS`:
logical name -> (relative path under ``assets/``, nominal pixel size).
Nothing else in the codebase should ever read an asset file path
directly -- that table is the contract with whoever supplies real art
(see ``assets/README.md``).

Paths are resolved from this file's location via ``__file__``, never
from the current working directory, since the launcher may spawn the
game from anywhere. A missing or unreadable file never crashes the
game: :func:`get` falls back to a bright magenta placeholder and logs
exactly one warning to stderr per sprite name.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Set, Tuple

import pygame

ASSETS_ROOT = Path(__file__).resolve().parent.parent / "assets"

Size = Tuple[int, int]

# name -> (relative path under assets/, nominal pixel size)
SPRITE_SPECS: Dict[str, Tuple[str, Size]] = {
    "wall": ("sprites/wall.png", (20, 20)),
    "pellet": ("sprites/pellet.png", (20, 20)),
    "power_pellet": ("sprites/power_pellet.png", (20, 20)),
    "gate": ("sprites/gate.png", (20, 20)),
    "scotty_up_1": ("sprites/scotty_up_1.png", (20, 20)),
    "scotty_up_2": ("sprites/scotty_up_2.png", (20, 20)),
    "scotty_down_1": ("sprites/scotty_down_1.png", (20, 20)),
    "scotty_down_2": ("sprites/scotty_down_2.png", (20, 20)),
    "scotty_left_1": ("sprites/scotty_left_1.png", (20, 20)),
    "scotty_left_2": ("sprites/scotty_left_2.png", (20, 20)),
    "scotty_right_1": ("sprites/scotty_right_1.png", (20, 20)),
    "scotty_right_2": ("sprites/scotty_right_2.png", (20, 20)),
    "ghost_gates_1": ("sprites/ghost_gates_1.png", (20, 20)),
    "ghost_gates_2": ("sprites/ghost_gates_2.png", (20, 20)),
    "ghost_hunt_1": ("sprites/ghost_hunt_1.png", (20, 20)),
    "ghost_hunt_2": ("sprites/ghost_hunt_2.png", (20, 20)),
    "ghost_wean_1": ("sprites/ghost_wean_1.png", (20, 20)),
    "ghost_wean_2": ("sprites/ghost_wean_2.png", (20, 20)),
    "ghost_doherty_1": ("sprites/ghost_doherty_1.png", (20, 20)),
    "ghost_doherty_2": ("sprites/ghost_doherty_2.png", (20, 20)),
    "ghost_frightened_1": ("sprites/ghost_frightened_1.png", (20, 20)),
    "ghost_frightened_2": ("sprites/ghost_frightened_2.png", (20, 20)),
    "ghost_frightened_flash_1": ("sprites/ghost_frightened_flash_1.png", (20, 20)),
    "ghost_frightened_flash_2": ("sprites/ghost_frightened_flash_2.png", (20, 20)),
    "eyes_up": ("sprites/eyes_up.png", (20, 20)),
    "eyes_down": ("sprites/eyes_down.png", (20, 20)),
    "eyes_left": ("sprites/eyes_left.png", (20, 20)),
    "eyes_right": ("sprites/eyes_right.png", (20, 20)),
    "life_icon": ("sprites/life_icon.png", (16, 16)),
    "fruit_0": ("sprites/fruit_0.png", (20, 20)),
    "fruit_1": ("sprites/fruit_1.png", (20, 20)),
    "fruit_2": ("sprites/fruit_2.png", (20, 20)),
    "fruit_3": ("sprites/fruit_3.png", (20, 20)),
    "fruit_4": ("sprites/fruit_4.png", (20, 20)),
    "fruit_5": ("sprites/fruit_5.png", (20, 20)),
    "fruit_6": ("sprites/fruit_6.png", (20, 20)),
    "fruit_7": ("sprites/fruit_7.png", (20, 20)),
}

PLACEHOLDER_COLOR = (255, 0, 255)  # unmissable magenta

_cache: Dict[str, "pygame.Surface"] = {}
_warned: Set[str] = set()


def _placeholder(size: Size) -> "pygame.Surface":
    surface = pygame.Surface(size)
    surface.fill(PLACEHOLDER_COLOR)
    pygame.draw.line(surface, (0, 0, 0), (0, 0), (size[0] - 1, size[1] - 1), 2)
    pygame.draw.line(surface, (0, 0, 0), (0, size[1] - 1), (size[0] - 1, 0), 2)
    return surface


def get(name: str) -> "pygame.Surface":
    """Return the cached, tile-scaled surface for a logical sprite name.

    Loads and scales at most once per name; safe to call every frame.
    """
    if name in _cache:
        return _cache[name]

    if name not in SPRITE_SPECS:
        raise KeyError(f"pacdawg.assets: no such sprite declared: {name!r}")

    rel_path, size = SPRITE_SPECS[name]
    path = ASSETS_ROOT / rel_path
    try:
        surface = pygame.image.load(str(path))
        if pygame.display.get_surface() is not None:
            surface = surface.convert_alpha()
    except (pygame.error, FileNotFoundError, OSError) as exc:
        if name not in _warned:
            print(
                f"pacdawg: missing or unreadable asset '{rel_path}' ({exc}); "
                "using placeholder",
                file=sys.stderr,
            )
            _warned.add(name)
        surface = _placeholder(size)

    if surface.get_size() != tuple(size):
        surface = pygame.transform.smoothscale(surface, size)

    _cache[name] = surface
    return surface


def preload_all() -> None:
    """Force every declared sprite through :func:`get` once, up front."""
    for name in SPRITE_SPECS:
        get(name)


def clear_cache() -> None:
    """Drop cached surfaces and warning state (used by tests)."""
    _cache.clear()
    _warned.clear()
