"""Scoring, lives, extra-life awards, and high-score persistence.

Pure logic, no pygame. High scores are written to a small JSON file next
to the repository (resolved via ``config.HIGHSCORE_PATH``, which is
anchored to this file's location, never the current working directory).
Any failure to read or write is caught and logged to stderr once; the
game must stay playable even on a read-only filesystem.
"""
from __future__ import annotations

import json
import sys

from . import config


def load_high_score() -> int:
    path = config.HIGHSCORE_PATH
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return 0
    except OSError as exc:
        print(f"pacdawg: could not read high score file ({exc}); starting at 0", file=sys.stderr)
        return 0
    try:
        data = json.loads(raw)
        return max(0, int(data.get("high_score", 0)))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"pacdawg: high score file is corrupt ({exc}); starting at 0", file=sys.stderr)
        return 0


def save_high_score(value: int) -> None:
    try:
        config.HIGHSCORE_PATH.write_text(
            json.dumps({"high_score": int(value)}), encoding="utf-8"
        )
    except OSError as exc:
        print(
            f"pacdawg: could not save high score ({exc}); continuing without persistence",
            file=sys.stderr,
        )


class ScoreBoard:
    """Tracks score, lives, level, and the ghost-eating combo chain."""

    def __init__(self, high_score: int = None):
        self.score = 0
        self.lives = config.STARTING_LIVES
        self.level = 1
        self.high_score = load_high_score() if high_score is None else high_score
        self.ghost_chain = 0
        self._extra_life_awarded = False

    def add_pellet(self) -> None:
        self.score += config.PELLET_SCORE
        self._check_extra_life()

    def add_power_pellet(self) -> None:
        self.score += config.POWER_PELLET_SCORE
        self.ghost_chain = 0
        self._check_extra_life()

    def add_ghost_eaten(self) -> int:
        """Award escalating combo points; returns points just scored."""
        index = min(self.ghost_chain, len(config.GHOST_COMBO_SCORES) - 1)
        points = config.GHOST_COMBO_SCORES[index]
        self.score += points
        self.ghost_chain += 1
        self._check_extra_life()
        return points

    def add_fruit(self, points: int) -> None:
        self.score += points
        self._check_extra_life()

    def reset_combo(self) -> None:
        self.ghost_chain = 0

    def _check_extra_life(self) -> None:
        if not self._extra_life_awarded and self.score >= config.EXTRA_LIFE_THRESHOLD:
            self.lives += 1
            self._extra_life_awarded = True

    def lose_life(self) -> bool:
        """Returns True if a life remains, False if it's game over."""
        self.lives -= 1
        self.ghost_chain = 0
        return self.lives > 0

    def advance_level(self) -> None:
        self.level += 1

    def commit_high_score(self) -> None:
        if self.score > self.high_score:
            self.high_score = self.score
            save_high_score(self.high_score)
