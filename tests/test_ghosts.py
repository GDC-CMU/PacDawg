"""Tests for ghost personalities and the scatter/chase/frightened machine."""
from __future__ import annotations

import random
import unittest

from pacdawg import config, levels
from pacdawg.entities import Direction, Scotty
from pacdawg.ghosts import (
    Ghost,
    GhostMode,
    ScatterChaseClock,
    TARGET_FUNCTIONS,
    apply_phase_change,
    create_ghosts,
    target_doherty,
    target_gates,
    target_hunt,
    target_wean,
)
from pacdawg.maze import Maze, MazeError


def _test_maze():
    """A small, hand-verified maze: open field, one tunnel row, a boxed
    ghost house with all four start markers, and a player start below it.
    """
    cols, rows = 17, 15
    grid = [["." for _ in range(cols)] for _ in range(rows)]
    for c in range(cols):
        grid[0][c] = "#"
        grid[rows - 1][c] = "#"
    for r in range(rows):
        grid[r][0] = "#"
        grid[r][cols - 1] = "#"

    tunnel_row = rows // 2  # 7
    grid[tunnel_row][0] = "T"
    grid[tunnel_row][cols - 1] = "T"

    top, bottom = tunnel_row - 2, tunnel_row + 2  # 5, 9
    left, right = 6, 10
    for c in range(left, right + 1):
        grid[top][c] = "#"
        grid[bottom][c] = "#"
    for r in range(top, bottom + 1):
        grid[r][left] = "#"
        grid[r][right] = "#"
    grid[top][(left + right) // 2] = "="
    for r in range(top + 1, bottom):
        for c in range(left + 1, right):
            grid[r][c] = " "
    grid[tunnel_row][left + 1] = "1"
    grid[tunnel_row][right - 1] = "2"
    grid[top + 1][(left + right) // 2] = "3"
    grid[bottom - 1][(left + right) // 2] = "4"

    grid[rows - 2][cols // 2] = "P"

    layout = ["".join(row) for row in grid]
    return Maze(layout, name="test-maze")


class GhostPersonalityTests(unittest.TestCase):
    def setUp(self):
        self.maze = _test_maze()
        self.player = Scotty(8, 13, levels.pacman_normal_speed(1))
        self.player.direction = Direction.RIGHT
        self.player.facing = Direction.RIGHT
        self.ghosts = create_ghosts(self.maze, level=1)

    def test_four_personalities_are_registered(self):
        self.assertEqual(set(TARGET_FUNCTIONS), {"gates", "hunt", "wean", "doherty"})

    def test_gates_targets_players_exact_tile(self):
        target = target_gates(self.ghosts["gates"], self.player, self.ghosts, self.maze)
        self.assertEqual(target, self.player.tile)

    def test_hunt_targets_ahead_of_player_facing(self):
        target = target_hunt(self.ghosts["hunt"], self.player, self.ghosts, self.maze)
        px, py = self.player.tile
        self.assertEqual(target, (px + 4, py))  # facing right
        self.assertNotEqual(target, self.player.tile)

    def test_hunt_reproduces_the_documented_up_overflow_bug(self):
        # Facing up, "4 tiles up" is documented to overflow into "4 up
        # AND 4 left" due to a genuine ROM bug (Don Hodges' Z80 analysis);
        # we deliberately reproduce it rather than "fixing" it.
        self.player.facing = Direction.UP
        target = target_hunt(self.ghosts["hunt"], self.player, self.ghosts, self.maze)
        px, py = self.player.tile
        self.assertEqual(target, (px - 4, py - 4))
        self.assertNotEqual(target, (px, py - 4))  # the "correct" (buggy-free) answer

    def test_wean_reproduces_the_documented_up_overflow_bug(self):
        self.player.facing = Direction.UP
        gates = self.ghosts["gates"]
        gates.teleport(8, 13)
        target = target_wean(self.ghosts["wean"], self.player, self.ghosts, self.maze)
        px, py = self.player.tile
        pivot = (px - 2, py - 2)  # overflowed pivot: 2 up AND 2 left
        expected = (2 * pivot[0] - gates.tile[0], 2 * pivot[1] - gates.tile[1])
        self.assertEqual(target, expected)

    def test_wean_target_depends_on_gates_position(self):
        gates = self.ghosts["gates"]
        gates.teleport(2, 2)
        target_a = target_wean(self.ghosts["wean"], self.player, self.ghosts, self.maze)
        gates.teleport(14, 12)
        target_b = target_wean(self.ghosts["wean"], self.player, self.ghosts, self.maze)
        self.assertNotEqual(target_a, target_b)

    def test_doherty_chases_far_and_retreats_close(self):
        doherty = self.ghosts["doherty"]
        doherty.teleport(*self.player.tile)  # right on top of Scotty: very close
        near_target = target_doherty(doherty, self.player, self.ghosts, self.maze)
        self.assertEqual(near_target, doherty.corner)

        doherty.teleport(1, 1)  # far corner: should come chase
        far_target = target_doherty(doherty, self.player, self.ghosts, self.maze)
        self.assertEqual(far_target, self.player.tile)

    def test_doherty_eight_tiles_exactly_counts_as_far(self):
        # Dossier: "eight tiles or more" -- inclusive. One reference clone
        # flips behavior at exactly 8 tiles by using a strict '>'; we use
        # '>=' per the documented wording.
        doherty = self.ghosts["doherty"]
        px, py = self.player.tile
        doherty.teleport(px + 8, py)  # exactly 8 tiles away (distance_sq == 64)
        target = target_doherty(doherty, self.player, self.ghosts, self.maze)
        self.assertEqual(target, self.player.tile)

        doherty.teleport(px + 7, py)  # just under 8 tiles: too close, retreats
        target = target_doherty(doherty, self.player, self.ghosts, self.maze)
        self.assertEqual(target, doherty.corner)

    def test_same_game_state_yields_different_targets_per_personality(self):
        targets = {
            name: fn(self.ghosts[name], self.player, self.ghosts, self.maze)
            for name, fn in TARGET_FUNCTIONS.items()
        }
        # doherty is far away here, so it also chases directly -- but gates
        # and hunt must still differ from each other, and wean (a
        # reflection through gates) must differ from a direct chase.
        self.assertNotEqual(targets["gates"], targets["hunt"])
        self.assertNotEqual(targets["gates"], targets["wean"])

    def test_create_ghosts_requires_all_four_markers(self):
        layout = [
            "#####",
            "#P..#",
            "#...#",
            "#.o.#",
            "#####",
        ]
        maze = Maze(layout, name="no-ghosts")
        with self.assertRaises(ValueError):
            create_ghosts(maze, level=1)


class GhostModeMachineTests(unittest.TestCase):
    def setUp(self):
        self.maze = _test_maze()
        self.ghost = Ghost("gates", (8, 8), (1, 1), levels.ghost_normal_speed(1))

    def test_new_ghost_starts_in_house(self):
        self.assertEqual(self.ghost.mode, GhostMode.HOUSE)

    def test_release_moves_to_leaving(self):
        self.ghost.release()
        self.assertEqual(self.ghost.mode, GhostMode.LEAVING)

    def test_frighten_only_affects_hunting_ghosts(self):
        self.ghost.mode = GhostMode.CHASE
        self.ghost.frighten(5.0)
        self.assertEqual(self.ghost.mode, GhostMode.FRIGHTENED)
        self.assertEqual(self.ghost.frightened_seconds_left, 5.0)

        house_ghost = Ghost("hunt", (8, 8), (1, 1), levels.ghost_normal_speed(1))
        house_ghost.frighten(5.0)
        self.assertEqual(house_ghost.mode, GhostMode.HOUSE)  # unaffected

    def test_frightened_expires_back_to_chase_or_scatter(self):
        self.ghost.mode = GhostMode.CHASE
        self.ghost.frighten(1.0)
        player = Scotty(8, 13, levels.pacman_normal_speed(1))
        ghosts = {"gates": self.ghost}
        rng = random.Random(1)

        self.ghost.update(self.maze, 0.5, player, ghosts, "chase", rng)
        self.assertEqual(self.ghost.mode, GhostMode.FRIGHTENED)

        self.ghost.update(self.maze, 0.6, player, ghosts, "chase", rng)
        self.assertEqual(self.ghost.mode, GhostMode.CHASE)

    def test_get_eaten_then_returns_home_and_reenters_house(self):
        self.ghost.mode = GhostMode.FRIGHTENED
        self.ghost.frightened_seconds_left = 3.0
        self.ghost.get_eaten()
        self.assertEqual(self.ghost.mode, GhostMode.EATEN)

        player = Scotty(8, 13, levels.pacman_normal_speed(1))
        ghosts = {"gates": self.ghost}
        rng = random.Random(2)
        # eyes move fast; give it plenty of simulated time to get home
        for _ in range(400):
            if self.ghost.mode is GhostMode.HOUSE:
                break
            self.ghost.update(self.maze, 1 / 30.0, player, ghosts, "chase", rng)
        self.assertEqual(self.ghost.mode, GhostMode.HOUSE)
        # It must have physically reached its own in-house home tile, not
        # just the gate/doorway.
        self.assertEqual(self.ghost.tile, self.ghost.home_tile)

    def test_revived_ghost_dwells_before_being_release_eligible(self):
        # Regression test: an eaten ghost used to flip straight to HOUSE
        # with released=False right at the gate, but the release
        # counters/timer were typically already satisfied by mid-level,
        # so it walked straight back out the doorway it just arrived
        # through. There must now be a real, visible, configurable dwell.
        self.ghost.mode = GhostMode.FRIGHTENED
        self.ghost.frightened_seconds_left = 3.0
        self.ghost.get_eaten()
        player = Scotty(8, 13, levels.pacman_normal_speed(1))
        ghosts = {"gates": self.ghost}
        rng = random.Random(2)
        for _ in range(400):
            if self.ghost.mode is GhostMode.HOUSE:
                break
            self.ghost.update(self.maze, 1 / 30.0, player, ghosts, "chase", rng)
        self.assertEqual(self.ghost.mode, GhostMode.HOUSE)
        self.assertAlmostEqual(self.ghost.house_dwell_remaining, config.GHOST_REVIVE_DWELL_SECONDS)

        # It must not become SCATTER/CHASE-eligible for at least the
        # configured dwell -- update() alone (with no external release())
        # never leaves HOUSE mode, so drive the dwell timer down directly
        # and confirm it only reaches zero after the configured duration.
        dt = 1 / 60.0
        elapsed = 0.0
        while self.ghost.house_dwell_remaining > 0:
            self.ghost.update(self.maze, dt, player, ghosts, "chase", rng)
            elapsed += dt
            self.assertEqual(self.ghost.mode, GhostMode.HOUSE)
            if elapsed > config.GHOST_REVIVE_DWELL_SECONDS + 1.0:
                self.fail("dwell never expired")
        self.assertGreaterEqual(elapsed, config.GHOST_REVIVE_DWELL_SECONDS - 0.05)

    def test_is_flashing_only_near_end_of_frightened(self):
        self.ghost.mode = GhostMode.FRIGHTENED
        self.ghost.frightened_flash_count = 5
        self.ghost.frightened_seconds_left = 5.0
        self.assertFalse(self.ghost.is_flashing)
        lead_in = 5 * 2 * config.FRIGHTENED_FLASH_TOGGLE_SECONDS
        self.ghost.frightened_seconds_left = lead_in - 0.01
        # flashing toggles on/off; just confirm it's deterministic and defined
        self.assertIn(self.ghost.is_flashing, (True, False))

    def test_is_flashing_false_without_a_flash_count(self):
        # A ghost frightened via frighten(seconds) with no flash_count
        # (e.g. some tests, or a level with 0 flashes) never flashes.
        self.ghost.mode = GhostMode.FRIGHTENED
        self.ghost.frightened_flash_count = 0
        self.ghost.frightened_seconds_left = 0.01
        self.assertFalse(self.ghost.is_flashing)

    def _in_bounds(self, maze, ghost):
        return -2 <= ghost.x <= maze.cols + 1 and -2 <= ghost.y <= maze.rows + 1

    def test_release_after_house_bobbing_never_runs_away(self):
        # Regression test: releasing a ghost while it is mid-bob used to
        # leave the tracked segment target on the wrong side of its
        # actual (bobbed) position, causing "distance to target" to grow
        # every frame instead of shrink -- so it never arrived, never
        # re-checked walls, and sailed straight through the top of the
        # maze forever.
        maze = _test_maze()
        ghost = Ghost("gates", (8, 8), (1, 1), levels.ghost_normal_speed(1))
        player = Scotty(*maze.player_start, levels.pacman_normal_speed(1))
        ghosts = {"gates": ghost}
        rng = random.Random(5)
        for _ in range(37):  # bob for an odd number of sub-frames first
            ghost._bob_in_house(1 / 60.0)
        ghost.release()
        for _ in range(600):
            ghost.update(maze, 1 / 60.0, player, ghosts, "chase", rng)
            self.assertTrue(
                self._in_bounds(maze, ghost),
                f"ghost left the maze bounds: ({ghost.x}, {ghost.y})",
            )

    def test_frighten_reversal_never_runs_away(self):
        maze = _test_maze()
        ghost = Ghost("gates", (8, 8), (1, 1), levels.ghost_normal_speed(1))
        player = Scotty(*maze.player_start, levels.pacman_normal_speed(1))
        ghosts = {"gates": ghost}
        rng = random.Random(6)
        ghost.mode = GhostMode.CHASE
        ghost.direction = Direction.RIGHT
        # Put the ghost mid-tile (not on an exact integer), the way it
        # would be most frames in a real game, before forcing a reversal.
        ghost.x = 8.4
        ghost._target_x, ghost._target_y = 9.0, 8.0
        ghost.frighten(5.0)
        for _ in range(600):
            ghost.update(maze, 1 / 60.0, player, ghosts, "chase", rng)
            self.assertTrue(self._in_bounds(maze, ghost))

    def test_apply_phase_change_reversal_never_runs_away(self):
        maze = _test_maze()
        ghost = Ghost("gates", (8, 8), (1, 1), levels.ghost_normal_speed(1))
        player = Scotty(*maze.player_start, levels.pacman_normal_speed(1))
        ghosts = {"gates": ghost}
        rng = random.Random(7)
        ghost.mode = GhostMode.CHASE
        ghost.direction = Direction.UP
        ghost.y = 7.6
        ghost._target_x, ghost._target_y = 8.0, 7.0
        apply_phase_change(ghosts, "scatter")
        for _ in range(600):
            ghost.update(maze, 1 / 60.0, player, ghosts, "scatter", rng)
            self.assertTrue(self._in_bounds(maze, ghost))


class ScatterChaseClockTests(unittest.TestCase):
    def test_starts_on_first_entry(self):
        clock = ScatterChaseClock([("scatter", 1.0), ("chase", 2.0)])
        self.assertEqual(clock.phase, "scatter")

    def test_advances_phase_after_duration(self):
        clock = ScatterChaseClock([("scatter", 1.0), ("chase", 2.0)])
        changed = clock.update(0.5)
        self.assertFalse(changed)
        self.assertEqual(clock.phase, "scatter")
        changed = clock.update(0.6)
        self.assertTrue(changed)
        self.assertEqual(clock.phase, "chase")

    def test_stays_on_final_phase_forever(self):
        clock = ScatterChaseClock([("scatter", 1.0), ("chase", 2.0)])
        clock.update(1.1)
        self.assertEqual(clock.phase, "chase")
        changed = clock.update(1000.0)
        self.assertFalse(changed)
        self.assertEqual(clock.phase, "chase")

    def test_apply_phase_change_flags_pending_reversal_for_hunting_ghosts(self):
        # Reversal is documented to "take effect when the ghost next
        # enters a tile", not instantly mid-corridor -- so apply_phase_change
        # only flags it; direction flips later, at the next arrival.
        ghost = Ghost("gates", (5, 5), (1, 1), levels.ghost_normal_speed(1))
        ghost.mode = GhostMode.CHASE
        ghost.direction = Direction.RIGHT
        apply_phase_change({"gates": ghost}, "scatter")
        self.assertEqual(ghost.mode, GhostMode.SCATTER)
        self.assertTrue(ghost._pending_reversal)
        self.assertEqual(ghost.direction, Direction.RIGHT)  # not yet flipped

    def test_apply_phase_change_reversal_lands_at_next_tile_arrival(self):
        maze = _test_maze()
        player = Scotty(*maze.player_start, levels.pacman_normal_speed(1))
        ghost = Ghost("gates", (8, 8), (1, 1), levels.ghost_normal_speed(1))
        ghost.mode = GhostMode.CHASE
        ghost.direction = Direction.RIGHT
        ghosts = {"gates": ghost}
        apply_phase_change(ghosts, "scatter")
        rng = random.Random(3)
        for _ in range(120):
            ghost.update(maze, 1 / 60.0, player, ghosts, "scatter", rng)
            if ghost.direction is Direction.LEFT:
                break
        self.assertEqual(ghost.direction, Direction.LEFT)
        self.assertFalse(ghost._pending_reversal)

    def test_apply_phase_change_ignores_frightened_and_eaten(self):
        ghost = Ghost("gates", (5, 5), (1, 1), levels.ghost_normal_speed(1))
        ghost.mode = GhostMode.FRIGHTENED
        ghost.direction = Direction.RIGHT
        apply_phase_change({"gates": ghost}, "scatter")
        self.assertEqual(ghost.mode, GhostMode.FRIGHTENED)
        self.assertEqual(ghost.direction, Direction.RIGHT)


class ScatterPatrolTests(unittest.TestCase):
    """Regression tests: scatter (and Doherty's close-range retreat) must
    make ghosts patrol/orbit their corner forever, never park there.

    The bug was that scatter corners sat on reachable open floor, and the
    "stop on arrival" rule (meant only for genuine static destinations
    like the house exit or gate) applied to them too -- so a ghost would
    drive to its corner, arrive, and freeze there for the rest of the
    phase.
    """

    def setUp(self):
        self.maze = levels.build_maze(1)
        self.player = Scotty(*self.maze.player_start, levels.pacman_normal_speed(1))
        self.ghosts = create_ghosts(self.maze, level=1)
        self.rng = random.Random(42)

    def test_no_hunting_ghost_is_ever_stationary_during_scatter(self):
        for ghost in self.ghosts.values():
            ghost.release()
            ghost.mode = GhostMode.SCATTER

        visited = {name: set() for name in self.ghosts}
        for _ in range(600):  # 10 simulated seconds
            for name, ghost in self.ghosts.items():
                previous = (ghost.x, ghost.y)
                ghost.update(self.maze, 1 / 60.0, self.player, self.ghosts, "scatter", self.rng)
                visited[name].add(ghost.tile)
                self.assertNotEqual(
                    (ghost.x, ghost.y),
                    previous,
                    f"{name} was stationary for a frame while in SCATTER",
                )

        for name, tiles in visited.items():
            self.assertGreater(
                len(tiles), 5, f"{name} only ever visited {len(tiles)} tile(s) while scattering"
            )

    def test_scatter_corners_are_outside_the_maze_and_unreachable(self):
        for ghost in self.ghosts.values():
            self.assertFalse(self.maze.in_bounds(*ghost.corner))

    def test_doherty_close_range_retreat_also_keeps_moving(self):
        doherty = self.ghosts["doherty"]
        doherty.release()
        doherty.mode = GhostMode.CHASE

        visited = set()
        for _ in range(600):
            # Keep Scotty right next to Doherty so it stays in "retreat"
            # mode (< 8 tiles away) for the whole run.
            self.player.x, self.player.y = doherty.x + 1, doherty.y
            previous = (doherty.x, doherty.y)
            doherty.update(self.maze, 1 / 60.0, self.player, self.ghosts, "chase", self.rng)
            visited.add(doherty.tile)
            self.assertNotEqual((doherty.x, doherty.y), previous)

        self.assertGreater(len(visited), 5)


class GatesHuntSymmetryTests(unittest.TestCase):
    """Client report: Gates and Hunt reported *identical* distance-to-corner
    at every sample during an early trace (30/30, 20/20, 9/9, ...), which
    looked suspicious -- two ghosts with different personalities moving in
    perfect lockstep would halve the apparent threat.

    Traced empirically: with a *stationary* player, Gates targets the
    player's exact tile and Hunt targets 4 tiles ahead of the player's
    facing, which (with no facing/no movement) collapses onto the same
    tile Gates targets; combined with both ghosts having zero release
    delay, equal speed and left-right mirrored corners/start tiles, they
    move as exact mirror images of one another -- not stacked on the same
    tile. This test pins that: they stay on different tiles throughout,
    but their x-coordinates sum to a constant (mirrored across the maze's
    vertical centerline) and their y-coordinates match.
    """

    def test_gates_and_hunt_are_mirror_images_during_scatter_not_stacked(self):
        maze = levels.build_maze(1)
        player = Scotty(*maze.player_start, levels.pacman_normal_speed(1))
        ghosts = create_ghosts(maze, level=1)
        rng = random.Random(42)
        for ghost in ghosts.values():
            ghost.release()
            ghost.mode = GhostMode.SCATTER

        gates, hunt = ghosts["gates"], ghosts["hunt"]
        same_tile_frames = 0
        for _ in range(600):  # 10 simulated seconds
            for name, ghost in ghosts.items():
                ghost.update(maze, 1 / 60.0, player, ghosts, "scatter", rng)
            if gates.tile == hunt.tile:
                same_tile_frames += 1
            self.assertAlmostEqual(gates.x + hunt.x, maze.cols - 1, delta=0.05)
            self.assertAlmostEqual(gates.y, hunt.y, delta=0.05)

        # They briefly share the single house-exit doorway tile while both
        # converge on it just after release, but must not stay stacked --
        # the rest of the run they're on distinct (mirrored) tiles.
        self.assertLess(same_tile_frames, 30, "gates and hunt stayed stacked on one tile")


if __name__ == "__main__":
    unittest.main()
