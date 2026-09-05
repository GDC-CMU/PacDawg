"""Tests for the documented Pac-Man Dossier speed/timing lookups.

These pin down the transcription from ``pacman-reference.md`` into
``config.py``/``levels.py``: base speed, per-level speed bands, the
scatter/chase timetable, frightened duration/flash counts (including the
documented non-monotonic jumps and the zero-duration levels), and the
maze-size scaling applied to every absolute dot count.
"""
from __future__ import annotations

import unittest

from pacdawg import config, levels


class BaseSpeedTests(unittest.TestCase):
    def test_base_speed_matches_the_documented_derivation(self):
        # 100% = 1.25 px/frame @ 60.606 Hz = 75.75757625 px/sec on 8px
        # tiles = 9.4697 tiles/sec (Dossier Table A.1 header).
        self.assertAlmostEqual(config.BASE_SPEED_TILES_PER_SEC, 9.46969703125, places=6)

    def test_level_1_pacman_is_80_percent(self):
        self.assertAlmostEqual(levels.pacman_normal_speed(1), config.BASE_SPEED_TILES_PER_SEC * 0.80)

    def test_level_5_pacman_is_full_speed(self):
        self.assertAlmostEqual(levels.pacman_normal_speed(5), config.BASE_SPEED_TILES_PER_SEC * 1.00)

    def test_level_21_pacman_drops_back_to_90_percent(self):
        self.assertAlmostEqual(levels.pacman_normal_speed(21), config.BASE_SPEED_TILES_PER_SEC * 0.90)

    def test_level_1_ghost_is_75_percent(self):
        self.assertAlmostEqual(levels.ghost_normal_speed(1), config.BASE_SPEED_TILES_PER_SEC * 0.75)

    def test_pacman_is_faster_than_ghosts_at_level_1(self):
        # The whole point of the cornering advantage: verify the raw
        # speeds themselves already favor the player at level 1.
        self.assertGreater(levels.pacman_normal_speed(1), levels.ghost_normal_speed(1))

    def test_elroy_2_is_the_only_speed_above_100_percent(self):
        self.assertAlmostEqual(levels.elroy2_speed(5), config.BASE_SPEED_TILES_PER_SEC * 1.05)
        self.assertGreater(levels.elroy2_speed(5), config.BASE_SPEED_TILES_PER_SEC)

    def test_frightened_pacman_is_faster_than_normal(self):
        self.assertGreater(levels.pacman_frightened_speed(1), levels.pacman_normal_speed(1))

    def test_tunnel_speed_is_slower_than_normal_ghost_speed(self):
        self.assertLess(levels.ghost_tunnel_speed(1), levels.ghost_normal_speed(1))


class DocumentedScatterChaseTimetableTests(unittest.TestCase):
    """Pins the literal Dossier table, independent of the arcade-fair
    opening override the game actually plays with (see
    ScatterChaseOpeningOverrideTests below)."""

    def test_level_1_matches_the_documented_absolute_timeline(self):
        table = levels.documented_scatter_chase_timetable_for_level(1)
        self.assertEqual(
            [d for _, d in table[:7]],
            [7.0, 20.0, 7.0, 20.0, 5.0, 20.0, 5.0],
        )
        self.assertEqual(table[0], ("scatter", 7.0))  # documented: opens in scatter
        self.assertEqual(table[7][0], "chase")
        self.assertGreater(table[7][1], 3600)  # effectively indefinite

    def test_levels_2_to_4_balloon_the_third_chase(self):
        table = levels.documented_scatter_chase_timetable_for_level(3)
        self.assertEqual(table[5], ("chase", 1033.0))
        self.assertAlmostEqual(table[6][1], 1.0 / 60.0)

    def test_level_5_plus_uses_1037_and_shorter_scatters(self):
        table = levels.documented_scatter_chase_timetable_for_level(10)
        self.assertEqual(table[0], ("scatter", 5.0))
        self.assertEqual(table[5], ("chase", 1037.0))

    def test_phases_alternate_scatter_and_chase(self):
        table = levels.documented_scatter_chase_timetable_for_level(1)
        for i, (phase, _) in enumerate(table):
            self.assertEqual(phase, "scatter" if i % 2 == 0 else "chase")


class ScatterChaseOpeningOverrideTests(unittest.TestCase):
    """The table the game actually plays with: a deliberate, documented
    deviation from the Dossier so ghosts engage from the start on a
    club-fair cabinet, instead of spending the first ~10s of a 30-60s
    session orbiting corners with no threat (see config.OPEN_IN_CHASE)."""

    def test_default_config_opens_in_chase(self):
        self.assertTrue(config.OPEN_IN_CHASE)
        self.assertLessEqual(config.OPENING_SCATTER_OVERRIDE_SECONDS, 0.0)

    def test_level_1_opens_directly_in_chase_not_scatter(self):
        table = levels.scatter_chase_timetable_for_level(1)
        self.assertEqual(table[0][0], "chase")
        self.assertEqual(table[0][1], 20.0)  # the documented table's *second* entry

    def test_later_phases_keep_their_documented_durations(self):
        documented = levels.documented_scatter_chase_timetable_for_level(1)
        overridden = levels.scatter_chase_timetable_for_level(1)
        # Everything after the removed opening scatter burst is untouched.
        self.assertEqual(overridden, documented[1:])

    def test_override_still_applies_across_bands(self):
        for level in (1, 3, 10):
            with self.subTest(level=level):
                table = levels.scatter_chase_timetable_for_level(level)
                self.assertEqual(table[0][0], "chase")

    def test_documented_table_is_unchanged_by_the_override(self):
        # The override must never mutate or replace the source-of-truth
        # documented table.
        before = levels.documented_scatter_chase_timetable_for_level(1)
        levels.scatter_chase_timetable_for_level(1)
        after = levels.documented_scatter_chase_timetable_for_level(1)
        self.assertEqual(before, after)
        self.assertEqual(after[0], ("scatter", 7.0))


class FrightenedTableTests(unittest.TestCase):
    def test_level_1_is_six_seconds_five_flashes(self):
        self.assertEqual(levels.frightened_seconds_for_level(1), 6.0)
        self.assertEqual(levels.frightened_flashes_for_level(1), 5)

    def test_non_monotonic_jumps_at_6_10_and_14(self):
        # Levels 5 -> 6, 9 -> 10, and 13 -> 14 all jump *up*, not down --
        # confirmed by two independent clones, not a transcription slip.
        self.assertEqual(levels.frightened_seconds_for_level(5), 2.0)
        self.assertEqual(levels.frightened_seconds_for_level(6), 5.0)
        self.assertEqual(levels.frightened_seconds_for_level(9), 1.0)
        self.assertEqual(levels.frightened_seconds_for_level(10), 5.0)
        self.assertEqual(levels.frightened_seconds_for_level(13), 1.0)
        self.assertEqual(levels.frightened_seconds_for_level(14), 3.0)

    def test_levels_17_19_20_and_beyond_have_zero_frightened_time(self):
        for level in (17, 19, 20, 25):
            with self.subTest(level=level):
                self.assertEqual(levels.frightened_seconds_for_level(level), 0.0)
                self.assertEqual(levels.frightened_flashes_for_level(level), 0)

    def test_level_18_is_not_zero_despite_neighbors_being_zero(self):
        self.assertEqual(levels.frightened_seconds_for_level(18), 1.0)
        self.assertEqual(levels.frightened_flashes_for_level(18), 3)


class DotScalingTests(unittest.TestCase):
    """Every absolute dot count in the Dossier is measured against the
    original 244-dot maze; ours has a different pellet count, so these
    must scale proportionally rather than being copied raw."""

    def test_elroy_thresholds_scale_with_maze_size(self):
        stage1_small, stage2_small = levels.elroy_thresholds_for_level(1, 244)
        self.assertEqual((stage1_small, stage2_small), (20, 10))  # unscaled = documented exactly

        stage1_big, stage2_big = levels.elroy_thresholds_for_level(1, 488)  # double-size maze
        self.assertEqual((stage1_big, stage2_big), (40, 20))

    def test_personal_dot_limit_scales_and_zero_stays_zero(self):
        self.assertEqual(levels.personal_dot_limit(1, "hunt", 488), 0)
        self.assertEqual(levels.personal_dot_limit(1, "wean", 488), 60)  # 30 * (488/244)
        self.assertEqual(levels.personal_dot_limit(1, "doherty", 488), 120)  # 60 * 2

    def test_personal_dot_limit_is_zero_from_level_3_onward(self):
        for name in ("hunt", "wean", "doherty"):
            self.assertEqual(levels.personal_dot_limit(3, name, 488), 0)
            self.assertEqual(levels.personal_dot_limit(10, name, 488), 0)

    def test_global_dot_counter_thresholds_scale(self):
        self.assertEqual(levels.global_dot_counter_threshold("hunt", 488), 14)  # 7 * 2
        self.assertEqual(levels.global_dot_counter_threshold("wean", 488), 34)  # 17 * 2
        self.assertEqual(levels.global_dot_counter_threshold("doherty", 488), 64)  # 32 * 2

    def test_fruit_triggers_scale(self):
        first, second = levels.fruit_pellet_triggers(488)
        self.assertEqual((first, second), (140, 340))  # 70*2, 170*2


class GhostReleaseTimeoutTests(unittest.TestCase):
    def test_four_seconds_for_levels_1_to_4(self):
        for level in (1, 2, 3, 4):
            self.assertEqual(levels.ghost_release_timeout_seconds(level), 4.0)

    def test_three_seconds_from_level_5(self):
        for level in (5, 6, 50):
            self.assertEqual(levels.ghost_release_timeout_seconds(level), 3.0)


class FruitScoreTests(unittest.TestCase):
    def test_documented_breakpoints(self):
        expected = {
            1: 100,
            2: 300,
            3: 500,
            4: 500,
            5: 700,
            6: 700,
            7: 1000,
            8: 1000,
            9: 2000,
            10: 2000,
            11: 3000,
            12: 3000,
            13: 5000,
            20: 5000,
        }
        for level, points in expected.items():
            with self.subTest(level=level):
                self.assertEqual(levels.fruit_score_for_level(level), points)


if __name__ == "__main__":
    unittest.main()
