"""Original CMU-themed maze layouts and per-level tuning.

Layouts are authored as literal text grids so they are easy to read and
hand-edit; see :mod:`pacdawg.maze` for the character legend. These are
wholly original layouts named after campus landmarks -- none of them
reproduce the layout of any existing maze-chase game.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from . import config
from .maze import Maze

# "The Cut" -- the grassy walkway that splits campus in two.
THE_CUT: List[str] = [
    "#################################",
    "#o.............................o#",
    "#.#####..###...###...###..#####.#",
    "#.#####..###...###...###..#####.#",
    "#........###.........###........#",
    "#.#####..###.........###..#####.#",
    "#.#####..###..##.##..###..#####.#",
    "#.............##.##.............#",
    "#.##.###.###..##.##..###.###.##.#",
    "#.##.###.###..##.##..###.###.##.#",
    "#...............................#",
    "#....###.....###=###.....###....#",
    "#.##.###.###.#  3  #.###.###.##.#",
    "T.##.....###.#1   2#.###.....##.T",
    "#.##.###.###.#  4  #.###.###.##.#",
    "#.##.###.###.#######.###.###.##.#",
    "#...............................#",
    "#.##.###.###.........###.###.##.#",
    "#.##.###.###.........###.###.##.#",
    "#...............................#",
    "#.#####..###... P ...###..#####.#",
    "#.#####..###.........###..#####.#",
    "#........###.........###........#",
    "#.#####..###...###...###..#####.#",
    "#.#####..###...###...###..#####.#",
    "#o.............................o#",
    "#################################",
]

# "The Fence" -- the painted CMU tradition wall.
THE_FENCE: List[str] = [
    "#################################",
    "#o.............................o#",
    "#.###.######...###...######.###.#",
    "#.....######.........######.....#",
    "#.###.........##.##.........###.#",
    "#.###.##.###..##.##..###.##.###.#",
    "#.###.##.###.........###.##.###.#",
    "#.....##.................##.....#",
    "#.###.##.###.........###.##.###.#",
    "#.###.##.###.........###.##.###.#",
    "#...............................#",
    "#.#####.####.###=###.####.#####.#",
    "#.#####......#  3  #......#####.#",
    "T............#1   2#............T",
    "#.##.###.###.#  4  #.###.###.##.#",
    "#.##.###.###.#######.###.###.##.#",
    "#.##.###.###.........###.###.##.#",
    "#..............###..............#",
    "#.#####.####...###...####.#####.#",
    "#.#####...................#####.#",
    "#.....##....... P .......##.....#",
    "#.###.##.###.........###.##.###.#",
    "#.###.##.###.........###.##.###.#",
    "#.###.##.................##.###.#",
    "#.###.##.###.........###.##.###.#",
    "#o.............................o#",
    "#################################",
]

# "Skibo" -- the campus cafe everyone routes through.
SKIBO: List[str] = [
    "#################################",
    "#o.............................o#",
    "#.##.#######.........#######.##.#",
    "#.##.........................##.#",
    "#.##.##.####.........####.##.##.#",
    "#.##.##.####...###...####.##.##.#",
    "#..............###..............#",
    "#.#####.####.........####.#####.#",
    "#.......####.........####.......#",
    "#.##.........................##.#",
    "#........###.........###........#",
    "#.######.....###=###.....######.#",
    "#.######.....#  3  #.....######.#",
    "T............#1   2#............T",
    "#.###.##.###.#  4  #.###.##.###.#",
    "#.###.##.###.#######.###.##.###.#",
    "#.....##.................##.....#",
    "#.###.##.###.........###.##.###.#",
    "#.###.##.###.........###.##.###.#",
    "#.###....###.........###....###.#",
    "#.............##P##.............#",
    "#.#####.####..##.##..####.#####.#",
    "#.#####...................#####.#",
    "#........###.........###........#",
    "#.##.....###.........###.....##.#",
    "#o.............................o#",
    "#################################",
]

LEVEL_LAYOUTS = [
    ("The Cut", THE_CUT),
    ("The Fence", THE_FENCE),
    ("Skibo", SKIBO),
]


def layout_index_for_level(level: int) -> int:
    """Levels cycle through the authored layouts forever."""
    return (max(level, 1) - 1) % len(LEVEL_LAYOUTS)


def name_for_level(level: int) -> str:
    return LEVEL_LAYOUTS[layout_index_for_level(level)][0]


def build_maze(level: int) -> Maze:
    """Construct a fresh :class:`Maze` (full pellets) for a level number."""
    name, layout = LEVEL_LAYOUTS[layout_index_for_level(level)]
    return Maze(layout, name=name)


def _clamped_index(length: int, level: int) -> int:
    return min(max(level, 1) - 1, length - 1)


# --- Speed lookups (Dossier Table A.1 percentages of BASE_SPEED_TILES_PER_SEC) --
def _level_band_index(level: int) -> int:
    """0 = level 1, 1 = levels 2-4, 2 = levels 5-20, 3 = levels 21+."""
    level = max(level, 1)
    if level == 1:
        return 0
    if level <= 4:
        return 1
    if level <= 20:
        return 2
    return 3


def _pct_to_speed(pct: float) -> float:
    return config.BASE_SPEED_TILES_PER_SEC * pct / 100.0


def pacman_normal_speed(level: int) -> float:
    return _pct_to_speed(config.PACMAN_NORMAL_PCT_BY_BAND[_level_band_index(level)])


def pacman_frightened_speed(level: int) -> float:
    return _pct_to_speed(config.PACMAN_FRIGHTENED_PCT_BY_BAND[_level_band_index(level)])


def ghost_normal_speed(level: int) -> float:
    return _pct_to_speed(config.GHOST_NORMAL_PCT_BY_BAND[_level_band_index(level)])


def ghost_frightened_speed(level: int) -> float:
    return _pct_to_speed(config.GHOST_FRIGHTENED_PCT_BY_BAND[_level_band_index(level)])


def ghost_tunnel_speed(level: int) -> float:
    return _pct_to_speed(config.GHOST_TUNNEL_PCT_BY_BAND[_level_band_index(level)])


def elroy1_speed(level: int) -> float:
    return _pct_to_speed(config.ELROY_1_PCT_BY_BAND[_level_band_index(level)])


def elroy2_speed(level: int) -> float:
    return _pct_to_speed(config.ELROY_2_PCT_BY_BAND[_level_band_index(level)])


def eyes_speed(level: int) -> float:
    """Undocumented by the Dossier; both reference clones estimate ~1.5x."""
    return ghost_normal_speed(level) * config.EYES_SPEED_MULTIPLIER


def house_pace_speed(level: int) -> float:
    """Undocumented by the Dossier; both reference clones estimate ~0.5x."""
    return ghost_normal_speed(level) * config.HOUSE_PACE_SPEED_MULTIPLIER


# --- Scatter / chase timetable ---------------------------------------------------
def scatter_chase_timetable_for_level(level: int) -> List[Tuple[str, float]]:
    """The (phase, seconds) timetable for a level (Dossier Ch. 2), ending
    in an effectively endless final chase."""
    level = max(level, 1)
    if level == 1:
        durations = config.SCATTER_CHASE_SECONDS_BY_BAND[1]
    elif level <= 4:
        durations = config.SCATTER_CHASE_SECONDS_BY_BAND["2-4"]
    else:
        durations = config.SCATTER_CHASE_SECONDS_BY_BAND["5+"]
    phases = ("scatter", "chase", "scatter", "chase", "scatter", "chase", "scatter")
    timetable = list(zip(phases, durations))
    timetable.append(("chase", 1_000_000.0))  # indefinite final chase
    return timetable


# --- Frightened duration / flashing ------------------------------------------------
def frightened_seconds_for_level(level: int) -> float:
    table = config.FRIGHTENED_SECONDS_BY_LEVEL
    return float(table[_clamped_index(len(table), level)])


def frightened_flashes_for_level(level: int) -> int:
    table = config.FRIGHTENED_FLASHES_BY_LEVEL
    return int(table[_clamped_index(len(table), level)])


# --- Dot-count scaling (our maze isn't the original's 244-dot 28x36 grid) ---------
def _dot_scale(total_pellets: int) -> float:
    """Every documented absolute dot count (Elroy thresholds, ghost-house
    release counters) is scaled proportionally to our maze's actual pellet
    total rather than copied raw, since our mazes are not 244 dots."""
    return total_pellets / config.ORIGINAL_MAZE_TOTAL_DOTS


def elroy_thresholds_for_level(level: int, total_pellets: int) -> Tuple[int, int]:
    """(stage-1, stage-2) dots-*remaining* thresholds, scaled to our maze."""
    idx = _clamped_index(len(config.ELROY_1_DOTS_LEFT_BY_LEVEL), level)
    scale = _dot_scale(total_pellets)
    stage1 = max(1, round(config.ELROY_1_DOTS_LEFT_BY_LEVEL[idx] * scale))
    stage2 = max(1, round(config.ELROY_2_DOTS_LEFT_BY_LEVEL[idx] * scale))
    return stage1, stage2


def personal_dot_limit(level: int, ghost_name: str, total_pellets: int) -> int:
    """Scaled ghost-house personal dot limit for one ghost at one level."""
    if level == 1:
        table = config.PERSONAL_DOT_LIMITS_BY_LEVEL[1]
    elif level == 2:
        table = config.PERSONAL_DOT_LIMITS_BY_LEVEL[2]
    else:
        table = config.PERSONAL_DOT_LIMITS_BY_LEVEL["3+"]
    raw = table.get(ghost_name, 0)
    if raw == 0:
        return 0
    return max(1, round(raw * _dot_scale(total_pellets)))


def global_dot_counter_threshold(ghost_name: str, total_pellets: int) -> int:
    """Scaled global ghost-house dot-counter threshold (used after a life
    is lost, in place of the personal counters)."""
    raw = config.GLOBAL_DOT_COUNTER_THRESHOLDS[ghost_name]
    return max(1, round(raw * _dot_scale(total_pellets)))


def ghost_release_timeout_seconds(level: int) -> float:
    """Anti-starvation timer: the most-preferred waiting ghost is released
    if this many seconds pass without Scotty eating a dot."""
    band = "1-4" if level <= 4 else "5+"
    return config.GHOST_RELEASE_TIMEOUT_SECONDS_BY_BAND[band]


# --- Fruit -------------------------------------------------------------------------
def fruit_score_for_level(level: int) -> int:
    for max_level, points in config.FRUIT_SCORE_BREAKPOINTS:
        if max_level is None or level <= max_level:
            return points
    return config.FRUIT_SCORE_BREAKPOINTS[-1][1]


def fruit_pellet_triggers(total_pellets: int) -> Tuple[int, int]:
    """Scaled (first, second) pellets-eaten counts that spawn bonus fruit."""
    scale = _dot_scale(total_pellets)
    first, second = config.FRUIT_PELLET_TRIGGERS_ORIGINAL
    return max(1, round(first * scale)), max(1, round(second * scale))
