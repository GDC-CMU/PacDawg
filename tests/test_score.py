"""Tests for scoring, combos, extra lives, and high-score persistence."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from pacdawg import config, score as score_mod
from pacdawg.score import ScoreBoard


class ScoreBoardTests(unittest.TestCase):
    def setUp(self):
        # Avoid touching the real high-score file during scoring tests.
        patcher = mock.patch.object(score_mod, "load_high_score", return_value=0)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_pellet_awards_points(self):
        board = ScoreBoard()
        board.add_pellet()
        self.assertEqual(board.score, config.PELLET_SCORE)

    def test_power_pellet_awards_points_and_resets_combo(self):
        board = ScoreBoard()
        board.add_ghost_eaten()
        board.add_power_pellet()
        self.assertEqual(board.ghost_chain, 0)

    def test_ghost_combo_escalates_then_holds(self):
        board = ScoreBoard()
        points = [board.add_ghost_eaten() for _ in range(6)]
        expected = config.GHOST_COMBO_SCORES + [config.GHOST_COMBO_SCORES[-1]] * 2
        self.assertEqual(points, expected)

    def test_extra_life_awarded_once_at_threshold(self):
        board = ScoreBoard()
        starting_lives = board.lives
        pellets_needed = -(-config.EXTRA_LIFE_THRESHOLD // config.PELLET_SCORE)
        for _ in range(pellets_needed):
            board.add_pellet()
        self.assertEqual(board.lives, starting_lives + 1)
        # Keep scoring past the threshold; must not award a second life.
        for _ in range(50):
            board.add_pellet()
        self.assertEqual(board.lives, starting_lives + 1)

    def test_lose_life_reports_game_over_at_zero(self):
        board = ScoreBoard()
        board.lives = 1
        alive = board.lose_life()
        self.assertFalse(alive)
        self.assertEqual(board.lives, 0)

    def test_lose_life_resets_combo(self):
        board = ScoreBoard()
        board.add_ghost_eaten()
        board.lose_life()
        self.assertEqual(board.ghost_chain, 0)

    def test_advance_level_increments(self):
        board = ScoreBoard()
        board.advance_level()
        board.advance_level()
        self.assertEqual(board.level, 3)


class HighScorePersistenceTests(unittest.TestCase):
    def setUp(self):
        self._original_path = config.HIGHSCORE_PATH

    def tearDown(self):
        config.HIGHSCORE_PATH = self._original_path
        score_mod.config.HIGHSCORE_PATH = self._original_path

    def test_missing_file_reads_as_zero(self, tmp_name="pacdawg_test_missing.json"):
        path = Path(__file__).resolve().parent / tmp_name
        if path.exists():
            path.unlink()
        score_mod.config.HIGHSCORE_PATH = path
        self.assertEqual(score_mod.load_high_score(), 0)

    def test_save_then_load_roundtrips(self):
        path = Path(__file__).resolve().parent / "pacdawg_test_roundtrip.json"
        score_mod.config.HIGHSCORE_PATH = path
        try:
            score_mod.save_high_score(4242)
            self.assertEqual(score_mod.load_high_score(), 4242)
        finally:
            if path.exists():
                path.unlink()

    def test_corrupt_file_reads_as_zero_and_does_not_raise(self):
        path = Path(__file__).resolve().parent / "pacdawg_test_corrupt.json"
        path.write_text("not valid json{{{", encoding="utf-8")
        score_mod.config.HIGHSCORE_PATH = path
        try:
            self.assertEqual(score_mod.load_high_score(), 0)
        finally:
            path.unlink()

    def test_unwritable_directory_does_not_raise(self):
        # A path inside a nonexistent directory can never be written --
        # this simulates a read-only filesystem without needing OS-level
        # permission tricks that behave inconsistently across platforms.
        path = Path(__file__).resolve().parent / "no_such_dir" / "highscore.json"
        score_mod.config.HIGHSCORE_PATH = path
        try:
            score_mod.save_high_score(999)  # must not raise
        except OSError:
            self.fail("save_high_score raised OSError instead of handling it")


if __name__ == "__main__":
    unittest.main()
