"""Central tunables for PacDawg.

Every knob that affects difficulty, timing, layout geometry, or input
mapping lives here so the rest of the codebase never hard-codes a magic
number. Modules other than :mod:`pacdawg.render`, :mod:`pacdawg.assets`
and :mod:`pacdawg.game` avoid importing :mod:`pygame` so that game logic
stays testable without a display.
"""
from __future__ import annotations

from pathlib import Path

# --- Screen / arcade cabinet -------------------------------------------------
# The cabinet's display is fixed at 800x600; the launcher does not resize us.
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
FPS = 60
WINDOW_TITLE = "PacDawg"

# --- Maze geometry ------------------------------------------------------------
TILE_SIZE = 20
MAZE_COLS = 33
MAZE_ROWS = 27
MAZE_OFFSET_X = (SCREEN_WIDTH - MAZE_COLS * TILE_SIZE) // 2  # 70
MAZE_OFFSET_Y = 40  # leaves a 40px HUD strip above and a 20px strip below

# --- Movement -----------------------------------------------------------------
# Speeds are expressed in tiles-per-second; render/entities convert to
# pixels-per-frame using FPS.
BASE_PLAYER_SPEED = 8.0
BASE_GHOST_SPEED = 7.0
FRIGHTENED_GHOST_SPEED = 4.0
EATEN_GHOST_SPEED = 14.0
TUNNEL_SPEED_MULTIPLIER = 0.5

# Per-level speed multipliers (index 0 == level 1). Levels beyond the list
# reuse the last entry, so the game keeps getting harder without needing an
# unbounded table.
LEVEL_SPEED_MULTIPLIERS = [1.0, 1.05, 1.1, 1.15, 1.2, 1.25, 1.3]
LEVEL_FRIGHTENED_SECONDS = [7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0]
FRIGHTENED_FLASH_SECONDS = 2.0  # tail end of frightened spent flashing
FRIGHTENED_FLASH_INTERVAL = 0.2

# --- Scatter / chase timetable (seconds), per phase, repeating -----------------
# Classic arcade maze-chase games alternate scatter and chase in bursts that
# shorten as levels progress; ours follows the same shape with original
# numbers tuned for our maze size.
SCATTER_CHASE_TIMETABLE = [
    ("scatter", 7.0),
    ("chase", 20.0),
    ("scatter", 7.0),
    ("chase", 20.0),
    ("scatter", 5.0),
    ("chase", 20.0),
    ("scatter", 5.0),
    ("chase", 1_000_000.0),  # effectively "forever" -- final chase phase
]

# --- Ghost house ----------------------------------------------------------------
# Seconds after a level/life begins before each ghost leaves the house.
GHOST_RELEASE_DELAYS = {
    "gates": 0.0,
    "hunt": 2.0,
    "wean": 5.0,
    "doherty": 8.0,
}
# A ghost is also released early once this many pellets have been eaten,
# regardless of its timer (per-ghost, tuned by house order).
GHOST_RELEASE_PELLET_COUNTS = {
    "gates": 0,
    "hunt": 0,
    "wean": 30,
    "doherty": 60,
}

# --- Scoring --------------------------------------------------------------------
PELLET_SCORE = 10
POWER_PELLET_SCORE = 50
GHOST_COMBO_SCORES = [200, 400, 800, 1600]  # 1st, 2nd, 3rd, 4th ghost in a chain
EXTRA_LIFE_THRESHOLD = 10_000
STARTING_LIVES = 3

FRUIT_SCORE_BY_LEVEL = [100, 300, 500, 700, 1000, 2000, 3000, 5000]
FRUIT_PELLET_THRESHOLDS = (70, 170)  # pellets-eaten counts that spawn fruit
FRUIT_LIFETIME_SECONDS = 10.0

# --- Persistence ------------------------------------------------------------------
# Resolved from this file's location, never from the current working
# directory, so the high score survives regardless of where the launcher
# sets cwd. The cabinet's filesystem may be read-only for a game's checkout;
# score.py must degrade gracefully if this can't be written.
HIGHSCORE_PATH = Path(__file__).resolve().parent.parent / "highscore.json"

# --- Input ------------------------------------------------------------------------
# Arcade cabinet button numbers (verified on the physical cabinet).
BUTTON_B = 0
BUTTON_A = 1
BUTTON_X = 2
BUTTON_Y = 3
BUTTON_COIN = 4
BUTTON_P1 = 5  # must exit the game immediately, from any state
BUTTON_SELECT = 8
BUTTON_START = 9

CONFIRM_BUTTONS = (BUTTON_A, BUTTON_START)
EXIT_BUTTONS = (BUTTON_P1,)

JOYSTICK_AXIS_X = 0
JOYSTICK_AXIS_Y = 1
JOYSTICK_DEADZONE = 0.5
