"""Tests for input intent resolution (joystick axes + keyboard)."""
from __future__ import annotations

import unittest

from pacdawg import config, input as input_mod
from pacdawg.entities import Direction
from pacdawg.input import RawInput


class AxisDirectionTests(unittest.TestCase):
    def test_below_deadzone_is_none(self):
        self.assertIsNone(input_mod.axis_direction(0.1, 0.1))

    def test_right_axis(self):
        self.assertEqual(input_mod.axis_direction(1.0, 0.0), Direction.RIGHT)

    def test_left_axis(self):
        self.assertEqual(input_mod.axis_direction(-1.0, 0.0), Direction.LEFT)

    def test_up_axis(self):
        self.assertEqual(input_mod.axis_direction(0.0, -1.0), Direction.UP)

    def test_down_axis(self):
        self.assertEqual(input_mod.axis_direction(0.0, 1.0), Direction.DOWN)

    def test_vertical_wins_on_tie(self):
        self.assertEqual(input_mod.axis_direction(1.0, 1.0), Direction.DOWN)

    def test_respects_custom_deadzone(self):
        self.assertIsNone(input_mod.axis_direction(0.3, 0.0, deadzone=0.5))
        self.assertEqual(input_mod.axis_direction(0.6, 0.0, deadzone=0.5), Direction.RIGHT)


class ResolveDirectionTests(unittest.TestCase):
    def test_either_connected_stick_can_steer(self):
        raw = RawInput(axes=((0.0, 0.0), (1.0, 0.0)))
        self.assertEqual(input_mod.resolve_direction(raw), Direction.RIGHT)

    def test_first_stick_wins_when_both_active(self):
        raw = RawInput(axes=((0.0, -1.0), (1.0, 0.0)))
        self.assertEqual(input_mod.resolve_direction(raw), Direction.UP)

    def test_falls_back_to_keyboard_when_no_stick_active(self):
        raw = RawInput(axes=((0.0, 0.0),), pressed_keys=frozenset({"a"}))
        self.assertEqual(input_mod.resolve_direction(raw), Direction.LEFT)

    def test_wasd_and_arrows_both_work(self):
        for key, expected in [
            ("w", Direction.UP),
            ("up", Direction.UP),
            ("s", Direction.DOWN),
            ("down", Direction.DOWN),
            ("a", Direction.LEFT),
            ("left", Direction.LEFT),
            ("d", Direction.RIGHT),
            ("right", Direction.RIGHT),
        ]:
            with self.subTest(key=key):
                raw = RawInput(pressed_keys=frozenset({key}))
                self.assertEqual(input_mod.resolve_direction(raw), expected)

    def test_no_input_returns_none(self):
        raw = RawInput()
        self.assertIsNone(input_mod.resolve_direction(raw))


class ConfirmExitTests(unittest.TestCase):
    def test_confirm_via_keyboard(self):
        for key in ("return", "space", "enter"):
            with self.subTest(key=key):
                self.assertTrue(input_mod.wants_confirm(RawInput(pressed_keys=frozenset({key}))))

    def test_confirm_via_arcade_buttons(self):
        self.assertFalse(input_mod.wants_confirm(RawInput(pressed_buttons=frozenset({config.BUTTON_A}))))
        self.assertTrue(input_mod.wants_confirm(RawInput(pressed_buttons=frozenset({config.BUTTON_START}))))

    def test_go_back_via_keyboard_or_arcade_buttons(self):
        # P1, Esc, Backspace, and button B are all equivalent aliases of
        # the single "go back one level" action.
        self.assertTrue(input_mod.wants_go_back(RawInput(pressed_keys=frozenset({"escape"}))))
        self.assertTrue(input_mod.wants_go_back(RawInput(pressed_keys=frozenset({"backspace"}))))
        self.assertTrue(input_mod.wants_go_back(RawInput(pressed_buttons=frozenset({config.BUTTON_P1}))))
        self.assertTrue(input_mod.wants_go_back(RawInput(pressed_buttons=frozenset({config.BUTTON_B}))))

    def test_no_false_positive_go_back(self):
        raw = RawInput(pressed_keys=frozenset({"a"}), pressed_buttons=frozenset({config.BUTTON_A}))
        self.assertFalse(input_mod.wants_go_back(raw))


if __name__ == "__main__":
    unittest.main()
