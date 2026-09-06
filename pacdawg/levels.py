"""Original CMU-themed maze layouts and per-level tuning.

Layouts are authored as literal text grids so they are easy to read and
hand-edit; see :mod:`pacdawg.maze` for the character legend. These are
wholly original layouts named after campus landmarks -- none of them
reproduce the layout of any existing maze-chase game.
"""
from __future__ import annotations

from typing import Dict, List, NamedTuple, Tuple

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


class Difficulty(NamedTuple):
    player_pct: int
    ghost_pct: int
    frightened_seconds: float
    release_timeout: float
    house_dot_limits: Tuple[int, int, int]


def difficulty_for_level(level: int) -> Difficulty:
    """A gentler first maze, increasing once per clear and capped at the last tier."""
    table = config.DIFFICULTY_BY_LEVEL
    return Difficulty(*table[_clamped_index(len(table), level)])


# --- Speed lookups: live difficulty curve; reference bands retained for eyes/house --
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
    return _pct_to_speed(difficulty_for_level(level).player_pct)


def pacman_frightened_speed(level: int) -> float:
    return _pct_to_speed(min(100, difficulty_for_level(level).player_pct + config.POWER_PLAYER_BONUS_PCT))


def ghost_normal_speed(level: int) -> float:
    return _pct_to_speed(difficulty_for_level(level).ghost_pct)


def ghost_frightened_speed(level: int) -> float:
    return ghost_normal_speed(level) * config.FRIGHTENED_SPEED_FRACTION


def ghost_tunnel_speed(level: int) -> float:
    return ghost_normal_speed(level) * config.TUNNEL_SPEED_FRACTION


def elroy1_speed(level: int) -> float:
    return _pct_to_speed(difficulty_for_level(level).ghost_pct + config.ELROY_BONUS_PCT[0])


def elroy2_speed(level: int) -> float:
    return _pct_to_speed(difficulty_for_level(level).ghost_pct + config.ELROY_BONUS_PCT[1])


def eyes_speed(level: int) -> float:
    """Returning eyes stay brisk even when chasing ghosts are beginner-slow."""
    reference = _pct_to_speed(config.GHOST_NORMAL_PCT_BY_BAND[_level_band_index(level)])
    return reference * config.EYES_SPEED_MULTIPLIER


def house_pace_speed(level: int) -> float:
    """Keep the non-threatening house animation independent of chase difficulty."""
    reference = _pct_to_speed(config.GHOST_NORMAL_PCT_BY_BAND[_level_band_index(level)])
    return reference * config.HOUSE_PACE_SPEED_MULTIPLIER


# --- Scatter / chase timetable ---------------------------------------------------
def documented_scatter_chase_timetable_for_level(level: int) -> List[Tuple[str, float]]:
    """The literal Dossier-documented (phase, seconds) timetable for a
    level (Ch. 2), always opening in scatter, ending in an effectively
    endless final chase.

    Most callers want :func:`scatter_chase_timetable_for_level` instead,
    which applies the arcade-fair opening override (config.OPEN_IN_CHASE)
    on top of this. This function exists so the documented table itself
    stays directly available and pinned by its own tests, even though the
    game does not use it unmodified by default.
    """
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


def scatter_chase_timetable_for_level(level: int) -> List[Tuple[str, float]]:
    """The (phase, seconds) timetable actually used by the game: the
    documented table with the arcade-fair opening override applied (see
    config.OPEN_IN_CHASE) -- every phase *after* the opening burst keeps
    its documented duration."""
    timetable = documented_scatter_chase_timetable_for_level(level)
    if config.OPEN_IN_CHASE:
        timetable = _apply_opening_chase_override(timetable)
    return timetable


def _apply_opening_chase_override(
    timetable: List[Tuple[str, float]]
) -> List[Tuple[str, float]]:
    override = config.OPENING_SCATTER_OVERRIDE_SECONDS
    if override <= 0.0:
        # Skip the opening scatter burst entirely: ghosts leave the house
        # straight into the timetable's first chase burst.
        return timetable[1:]
    return [("scatter", override)] + timetable[1:]


# --- Frightened duration / flashing ------------------------------------------------
def frightened_seconds_for_level(level: int) -> float:
    return difficulty_for_level(level).frightened_seconds


def frightened_flashes_for_level(level: int) -> int:
    duration = frightened_seconds_for_level(level)
    return min(config.POWER_WARNING_FLASHES, int(duration / (2 * config.FRIGHTENED_FLASH_TOGGLE_SECONDS)))


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


def _house_dot_limits(level: int) -> Dict[str, int]:
    return dict(zip(("hunt", "wean", "doherty"), difficulty_for_level(level).house_dot_limits))


def personal_dot_limit(level: int, ghost_name: str, total_pellets: int) -> int:
    """Scaled ghost-house personal dot limit for one ghost at one level."""
    raw = _house_dot_limits(level).get(ghost_name, 0)
    if raw == 0:
        return 0
    return max(1, round(raw * _dot_scale(total_pellets)))


def global_dot_counter_threshold(ghost_name: str, total_pellets: int, level: int = 1) -> int:
    """Scaled global ghost-house dot-counter threshold (used after a life
    is lost, in place of the personal counters)."""
    raw = max(config.GLOBAL_DOT_COUNTER_THRESHOLDS[ghost_name], _house_dot_limits(level)[ghost_name])
    return max(1, round(raw * _dot_scale(total_pellets)))


def ghost_release_timeout_seconds(level: int) -> float:
    """Anti-starvation timer: the most-preferred waiting ghost is released
    if this many seconds pass without Scotty eating a dot."""
    return difficulty_for_level(level).release_timeout


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
