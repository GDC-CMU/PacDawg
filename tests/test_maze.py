"""Tests for maze layout parsing, validation, and pellet accounting."""
from __future__ import annotations

import unittest

from pacdawg.maze import Maze, MazeError
from pacdawg import levels


def _minimal_layout():
    return [
        "#######",
        "#.....#",
        "#.###.#",
        "#.....#",
        "#.###.#",
        "#..P..#",
        "#######",
    ]


class MazeParsingTests(unittest.TestCase):
    def test_rejects_ragged_rows(self):
        layout = _minimal_layout()
        layout[2] = "#.###"  # too short
        with self.assertRaises(MazeError):
            Maze(layout, name="ragged")

    def test_rejects_unknown_character(self):
        layout = _minimal_layout()
        layout[3] = "#..Z.#"
        with self.assertRaises(MazeError):
            Maze(layout, name="bad-char")

    def test_rejects_missing_player_start(self):
        layout = [row.replace("P", ".") for row in _minimal_layout()]
        with self.assertRaises(MazeError):
            Maze(layout, name="no-player")

    def test_rejects_duplicate_player_start(self):
        layout = _minimal_layout()
        layout[1] = "#P....#"
        with self.assertRaises(MazeError):
            Maze(layout, name="two-players")

    def test_rejects_no_pellets(self):
        layout = [row.replace(".", " ") for row in _minimal_layout()]
        with self.assertRaises(MazeError):
            Maze(layout, name="no-pellets")

    def test_rejects_unreachable_pellet(self):
        layout = [
            "#######",
            "#P....#",
            "#.###.#",
            "#.#.#.#",
            "#.###.#",
            "#.....#",
            "#######",
        ]
        # the pellet at (3, 3) is walled in on all four sides
        with self.assertRaises(MazeError):
            Maze(layout, name="sealed-pellet")

    def test_valid_minimal_layout_parses(self):
        maze = Maze(_minimal_layout(), name="minimal")
        self.assertEqual(maze.player_start, (3, 5))
        self.assertGreater(maze.pellets_remaining, 0)
        self.assertFalse(maze.is_complete)

    def test_eating_all_pellets_completes_maze(self):
        maze = Maze(_minimal_layout(), name="minimal")
        total = maze.total_pellets
        eaten = 0
        for row in range(maze.rows):
            for col in range(maze.cols):
                if maze.eat_at(col, row) is not None:
                    eaten += 1
        self.assertEqual(eaten, total)
        self.assertTrue(maze.is_complete)
        self.assertEqual(maze.pellets_remaining, 0)

    def test_reset_pellets_restores_original_counts(self):
        maze = Maze(_minimal_layout(), name="minimal")
        total = maze.total_pellets
        for row in range(maze.rows):
            for col in range(maze.cols):
                maze.eat_at(col, row)
        self.assertTrue(maze.is_complete)
        maze.reset_pellets()
        self.assertEqual(maze.pellets_remaining, total)

    def test_tunnel_requires_both_ends_open(self):
        layout = _minimal_layout()
        layout[3] = "T....#"  # only the left end is a tunnel opening
        with self.assertRaises(MazeError):
            Maze(layout, name="one-sided-tunnel")

    def test_gate_blocks_player_but_not_ghost(self):
        layout = [
            "#######",
            "#.....#",
            "#.###.#",
            "#.#1#.#",
            "#.#2#.#",
            "#.#3#.#",
            "#.=4=.#",
            "#..P..#",
            "#######",
        ]
        maze = Maze(layout, name="gated")
        gate_coords = list(maze.gates)
        self.assertTrue(len(gate_coords) >= 1)
        col, row = gate_coords[0]
        self.assertTrue(maze.can_ghost_enter(col, row))
        self.assertFalse(maze.can_player_enter(col, row))

    def test_wrap_col(self):
        maze = Maze(_minimal_layout(), name="minimal")
        self.assertEqual(maze.wrap_col(-1), maze.cols - 1)
        self.assertEqual(maze.wrap_col(maze.cols), 0)
        self.assertEqual(maze.wrap_col(3), 3)


class AuthoredLevelTests(unittest.TestCase):
    """The real, shipped CMU-themed layouts must all be valid and distinct."""

    def test_all_authored_layouts_are_valid(self):
        for name, layout in levels.LEVEL_LAYOUTS:
            maze = Maze(layout, name=name)
            self.assertGreater(maze.total_pellets, 0)
            self.assertEqual(len(maze.ghost_starts), 4)

    def test_layouts_cycle_across_levels(self):
        count = len(levels.LEVEL_LAYOUTS)
        first_name = levels.name_for_level(1)
        cycled_name = levels.name_for_level(1 + count)
        self.assertEqual(first_name, cycled_name)

    def test_build_maze_returns_fresh_pellets(self):
        maze1 = levels.build_maze(1)
        maze1.eat_at(*maze1.player_start)
        maze2 = levels.build_maze(1)
        self.assertEqual(maze2.pellets_eaten, 0)

    def test_speed_multiplier_clamps_beyond_table(self):
        far_level = 999
        table = levels.config.LEVEL_SPEED_MULTIPLIERS
        self.assertEqual(levels.speed_multiplier_for_level(far_level), table[-1])


if __name__ == "__main__":
    unittest.main()
