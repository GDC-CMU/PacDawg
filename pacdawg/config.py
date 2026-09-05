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

# --- Movement ------------------------------------------------------------------
# Speed and timing constants below are transcribed from Jamey Pittman's
# "The Pac-Man Dossier" (a ROM disassembly-derived reference), cross
# checked against Don Hodges' Z80 analysis and two high-fidelity clones.
# Where noted, a value is scaled for our maze (which is not the original's
# 28x36 grid with 244 dots) or is a documented, deliberate approximation
# rather than an exact ROM constant.

# 100% speed = 1.25 px/frame @ 60.606 Hz = 75.75757625 px/sec on an 8x8px
# tile grid = 9.4697 tiles/sec. We (like the reference clones) run a flat
# 60 Hz update, which the Dossier itself notes is ~1% slower than the true
# arcade timing -- an accepted, documented simplification.
BASE_SPEED_TILES_PER_SEC = 75.75757625 / 8.0  # 9.46969703125

# Per-level speed percentages of BASE_SPEED_TILES_PER_SEC, banded by level:
# band 0 = level 1, band 1 = levels 2-4, band 2 = levels 5-20, band 3 = 21+.
# (Dossier Table A.1 / the condensed Chapter 2 speed table.)
PACMAN_NORMAL_PCT_BY_BAND = (80, 90, 100, 90)
PACMAN_FRIGHTENED_PCT_BY_BAND = (90, 95, 100, 90)  # Pac-Man moves faster while frightened is active
GHOST_NORMAL_PCT_BY_BAND = (75, 85, 95, 95)
GHOST_FRIGHTENED_PCT_BY_BAND = (50, 55, 60, 60)
GHOST_TUNNEL_PCT_BY_BAND = (40, 45, 50, 50)
ELROY_1_PCT_BY_BAND = (80, 90, 100, 100)
ELROY_2_PCT_BY_BAND = (85, 95, 105, 105)  # the only speed above 100% in the game

# Eaten-ghost ("eyes") and in-house pacing speeds are explicitly documented
# as *undocumented* by the Dossier; both reference clones estimate them.
# We follow floooh/pacman.c's estimate of ~1.5x normal ghost speed for eyes
# and ~0.5x for in-house pacing.
EYES_SPEED_MULTIPLIER = 1.5  # of GHOST_NORMAL_PCT_BY_BAND for the level
HOUSE_PACE_SPEED_MULTIPLIER = 0.5

# The Dossier's own "~71%/~79%/~87%" Pac-Man "dots speed" figures are not
# separate tunables: they are the *emergent* result of Pac-Man freezing for
# one game tick per regular dot eaten (three ticks for a power pellet). We
# reproduce that mechanically (Scotty.pause()) rather than hard-coding an
# approximated percentage, which the Dossier confirms is the more accurate
# model (its own numbers are only self-consistent under this derivation).
DOT_EAT_PAUSE_SECONDS = 1.0 / 60.0
POWER_PELLET_EAT_PAUSE_SECONDS = 3.0 / 60.0

# --- Scatter / Chase timetable (seconds), banded by level (Dossier Ch. 2) -------
# The third "chase" balloons past 17 minutes and the fourth "scatter" is a
# genuine but blink-and-you-miss-it 1/60s on every level after the first,
# which reads as a simple direction reversal. The scatter/chase timer
# pauses entirely while any ghost is frightened, and resumes afterward.
SCATTER_CHASE_SECONDS_BY_BAND = {
    1: (7.0, 20.0, 7.0, 20.0, 5.0, 20.0, 5.0),
    "2-4": (7.0, 20.0, 7.0, 20.0, 5.0, 1033.0, 1.0 / 60.0),
    "5+": (5.0, 20.0, 5.0, 20.0, 5.0, 1037.0, 1.0 / 60.0),
}

# --- Arcade-fair opening override (DELIBERATE DEVIATION from the Dossier) -------
# The documented table above always opens a level/life in scatter (7s on
# level 1). That is faithful to the original, but this is a club-fair
# cabinet where a visitor typically plays for 30-60 seconds total --
# spending the first third of that watching ghosts walk to their corners
# and orbit there, with no threat, reads as broken AI rather than
# authentic pacing. We deliberately open every level/life in CHASE
# instead; the documented table itself (SCATTER_CHASE_SECONDS_BY_BAND) is
# left untouched, and every *later* scatter/chase phase in the cycle
# keeps its documented duration -- only the opening burst is overridden.
# See levels.scatter_chase_timetable_for_level(), which applies this, and
# levels.documented_scatter_chase_timetable_for_level(), which does not.
#
# To restore the authentic Dossier opening (scatter first, for the
# documented duration), set OPEN_IN_CHASE = False.
OPEN_IN_CHASE = True
# When OPEN_IN_CHASE is True, the opening scatter burst's documented
# duration is replaced with this many seconds before falling through to
# the rest of the documented timetable. 0.0 skips the opening scatter
# burst entirely (ghosts leave the house straight into chase); a small
# positive value keeps a brief opening scatter instead of removing it.
OPENING_SCATTER_OVERRIDE_SECONDS = 0.0

# --- Frightened duration & flash count, per level (Dossier Table A.1) -----------
# Deliberately non-monotonic (levels 6, 10, and 14 jump back up) -- this is
# real, confirmed independently by two clones, not a transcription error.
# Levels 17, 19, 20, and 21+ are genuinely 0 seconds (no frightened mode).
FRIGHTENED_SECONDS_BY_LEVEL = (6, 5, 4, 3, 2, 5, 2, 2, 1, 5, 2, 1, 1, 3, 1, 1, 0, 1, 0, 0)
FRIGHTENED_FLASHES_BY_LEVEL = (5, 5, 5, 5, 5, 5, 5, 5, 3, 5, 5, 3, 3, 5, 3, 3, 0, 3, 0, 0)
# "The ghosts change colors every 14 game cycles when they start flashing" --
# Pittman. One flash = 2 x 14 frames (blue, then white).
FRIGHTENED_FLASH_TOGGLE_SECONDS = 14.0 / 60.0

# --- Cruise Elroy (Blinky/Gates speed-up) ---------------------------------------
# Dots-*remaining* thresholds, indexed by level (1-21, clamped beyond), out
# of the original maze's 244 total dots. Our maze has a different pellet
# count, so these are scaled proportionally at lookup time (see
# levels.elroy_thresholds_for_level) rather than copied raw.
ELROY_1_DOTS_LEFT_BY_LEVEL = (20, 30, 40, 40, 40, 50, 50, 50, 60, 60, 60, 80, 80, 80, 100, 100, 100, 100, 120, 120, 120)
ELROY_2_DOTS_LEFT_BY_LEVEL = (10, 15, 20, 20, 20, 25, 25, 25, 30, 30, 30, 40, 40, 40, 50, 50, 50, 50, 60, 60, 60)
ORIGINAL_MAZE_TOTAL_DOTS = 244  # 240 dots + 4 energizers; the maze this table was measured on

# --- Ghost house release (Dossier Ch. 2, "Home Sweet Home") ---------------------
# Personal dot-limit counters: only the single most-preferred ghost still
# waiting inside the house accrues a counter (preference order Hunt, then
# Wean, then Doherty); Gates (Blinky) is never subject to this at all and
# leaves immediately. Absolute counts out of ORIGINAL_MAZE_TOTAL_DOTS,
# scaled to our maze size (see levels.personal_dot_limit).
PERSONAL_DOT_LIMITS_BY_LEVEL = {
    1: {"hunt": 0, "wean": 30, "doherty": 60},
    2: {"hunt": 0, "wean": 0, "doherty": 50},
    "3+": {"hunt": 0, "wean": 0, "doherty": 0},
}

# Global dot counter, used instead of the personal counters after a life is
# lost. Also scaled to our maze size. Reaching the Doherty/Clyde threshold
# both releases him and deactivates the global counter (personal counters
# resume from then on).
GLOBAL_DOT_COUNTER_THRESHOLDS = {"hunt": 7, "wean": 17, "doherty": 32}

# Anti-starvation release timer: if Pac-Man goes this long without eating a
# dot, the most-preferred waiting ghost is released immediately regardless
# of any counter, and the timer resets.
GHOST_RELEASE_TIMEOUT_SECONDS_BY_BAND = {"1-4": 4.0, "5+": 3.0}

# How long a *revived* ghost (eaten, walked home, arrived at its in-house
# slot) bobs in the house before it is eligible for release again. The
# original ties this purely to the ambient release timer/counters, which
# are typically already satisfied by mid-level -- so a revived ghost can
# walk straight back out the door it just arrived through. We make the
# minimum dwell explicit and tunable here instead of leaving it implicit,
# so there is always a visible pause before a revived ghost rejoins the
# chase. This is a deliberate, documented departure from strict fidelity
# for legibility on a cabinet, not a transcription of the Dossier.
GHOST_REVIVE_DWELL_SECONDS = 3.0

# --- Scoring --------------------------------------------------------------------
PELLET_SCORE = 10
POWER_PELLET_SCORE = 50
GHOST_COMBO_SCORES = [200, 400, 800, 1600]  # 1st, 2nd, 3rd, 4th ghost in a chain
EXTRA_LIFE_THRESHOLD = 10_000
STARTING_LIVES = 3

# Fruit score by level (Dossier Table A.1); (max_level_inclusive, points),
# last entry (None) catches everything beyond.
FRUIT_SCORE_BREAKPOINTS = (
    (1, 100),
    (2, 300),
    (4, 500),
    (6, 700),
    (8, 1000),
    (10, 2000),
    (12, 3000),
    (None, 5000),
)
# Fruit spawns after this many dots eaten (out of ORIGINAL_MAZE_TOTAL_DOTS,
# scaled to our maze). On-screen duration is documented as "always between
# nine and ten seconds," deliberately variable rather than a fixed value.
FRUIT_PELLET_TRIGGERS_ORIGINAL = (70, 170)
FRUIT_LIFETIME_SECONDS_RANGE = (9.0, 10.0)

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
BUTTON_P1 = 5  # "go back one level" (main menu -> exit; anywhere else -> main menu), per the club's cross-game arcade contract
BUTTON_SELECT = 8
BUTTON_START = 9

CONFIRM_BUTTONS = (BUTTON_A, BUTTON_START)
# The single "go back one level" action is aliased across two buttons on
# the cabinet: P1 (5, the club's cross-game back/exit button) and B (0,
# the natural back partner to A/1 in this cabinet's layout). They are
# fully equivalent everywhere -- see input.wants_go_back() and
# Game.maybe_go_back().
EXIT_BUTTONS = (BUTTON_P1,)
BACK_BUTTONS = (BUTTON_B,)

JOYSTICK_AXIS_X = 0
JOYSTICK_AXIS_Y = 1
JOYSTICK_DEADZONE = 0.5

# The ArcadeLauncher's gallery selects a game with button 1 (A) or Enter,
# then tears down its own SDL and spawns us while that button may still be
# physically held. SDL surfaces the still-held button to us as soon as we
# initialize joysticks/keyboard, which an edge-triggered menu would read as
# a brand-new press and instantly confirm START GAME before the visitor
# ever sees the menu. Game.init_display() seeds pressed-state from the
# real hardware at startup (so a held button must be released once before
# it counts as fresh) -- this settle window is a belt-and-braces second
# layer that additionally ignores menu confirm/select for a brief moment
# after startup, in case anything slips past the seeding. It intentionally
# does NOT apply to the P1 exit contract, which must remain immediate.
INPUT_SETTLE_SECONDS = 0.3
