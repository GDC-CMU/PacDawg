#!/usr/bin/env python
"""Regenerate the committed placeholder sprite PNGs deterministically.

Every shape here is drawn with fixed coordinates (no randomness), so
running this script twice in a row leaves ``git status`` clean. Run it
whenever a new logical sprite is added to
``pacdawg.assets.SPRITE_SPECS``, or any time you want to reset
``assets/sprites/`` back to the stock placeholder look.

These placeholders are deliberately more than flat rectangles -- a
recognisable shaggy terrier silhouette for Scotty, four distinct ghost
colors, and themed CMU/Skibo snack icons for fruit -- so the repo looks
intentional from the first clone. Real art can replace any file here
with zero code changes; see ``assets/README.md``.
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pacdawg.assets import ASSETS_ROOT, SPRITE_SPECS  # noqa: E402

pygame.init()

TRANSPARENT = (0, 0, 0, 0)

GATES_COLOR = (214, 40, 40)     # Gates: red, direct chaser
HUNT_COLOR = (255, 128, 200)    # Hunt: pink, ambusher
WEAN_COLOR = (64, 200, 220)     # Wean: cyan, flanker
DOHERTY_COLOR = (240, 150, 60)  # Doherty: orange, shy

DIRECTION_ANGLES = {"right": 0, "up": -90, "left": 180, "down": 90}
DIRECTION_VECTORS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


def _surface(size):
    surf = pygame.Surface(size, pygame.SRCALPHA)
    surf.fill(TRANSPARENT)
    return surf


# --- Scotty --------------------------------------------------------------------
def make_scotty(size, direction, frame):
    w, h = size
    surf = _surface(size)
    cx, cy = w / 2.0, h / 2.0
    radius = min(w, h) / 2.0 - 1.5

    body = (35, 33, 31)
    ear_shade = (58, 54, 50)
    belly = (120, 112, 104)
    outline = (150, 140, 130)
    collar = (196, 40, 60)

    pygame.draw.circle(surf, body, (round(cx), round(cy)), round(radius))

    belly_w, belly_h = radius * 0.75, radius * 0.55
    pygame.draw.ellipse(
        surf,
        belly,
        pygame.Rect(
            round(cx - belly_w / 2), round(cy + radius * 0.2), round(belly_w), round(belly_h)
        ),
    )

    ear_dx, ear_dy = radius * 0.55, radius * 0.55
    left_ear = [
        (cx - ear_dx, cy - ear_dy),
        (cx - radius * 0.12, cy - radius * 1.05),
        (cx - radius * 0.02, cy - radius * 0.3),
    ]
    right_ear = [
        (cx + ear_dx, cy - ear_dy),
        (cx + radius * 0.12, cy - radius * 1.05),
        (cx + radius * 0.02, cy - radius * 0.3),
    ]
    pygame.draw.polygon(surf, ear_shade, left_ear)
    pygame.draw.polygon(surf, ear_shade, right_ear)
    pygame.draw.polygon(surf, outline, left_ear, 1)
    pygame.draw.polygon(surf, outline, right_ear, 1)

    # a little collar, always at the "back of the neck" opposite the mouth
    collar_angle = math.radians(DIRECTION_ANGLES[direction] + 180)
    collar_x = cx + math.cos(collar_angle) * radius * 0.55
    collar_y = cy + math.sin(collar_angle) * radius * 0.55
    pygame.draw.circle(surf, collar, (round(collar_x), round(collar_y)), max(1, round(radius * 0.14)))

    # chomping mouth wedge, cut fully transparent, aimed at the facing direction
    angle_center = DIRECTION_ANGLES[direction]
    half_angle = 16 if frame == 1 else 42
    a1 = math.radians(angle_center - half_angle)
    a2 = math.radians(angle_center + half_angle)
    reach = radius * 1.3
    p1 = (cx + math.cos(a1) * reach, cy + math.sin(a1) * reach)
    p2 = (cx + math.cos(a2) * reach, cy + math.sin(a2) * reach)
    pygame.draw.polygon(surf, TRANSPARENT, [(cx, cy), p1, p2])

    eye_angle = math.radians(angle_center - 100)
    eye_x = cx + math.cos(eye_angle) * radius * 0.45
    eye_y = cy + math.sin(eye_angle) * radius * 0.45
    pygame.draw.circle(surf, (230, 220, 210), (round(eye_x), round(eye_y)), max(2, round(radius * 0.18)))
    pygame.draw.circle(surf, (12, 12, 12), (round(eye_x), round(eye_y)), max(1, round(radius * 0.09)))

    pygame.draw.circle(surf, outline, (round(cx), round(cy)), round(radius), 1)
    return surf


# --- Ghosts ----------------------------------------------------------------------
def _ghost_shape(size, color, frame, face="normal"):
    w, h = size
    surf = _surface(size)
    cx = w / 2.0
    radius = (w - 2) / 2.0
    top_cy = h * 0.42

    pygame.draw.circle(surf, color, (round(cx), round(top_cy)), round(radius))
    body_rect = pygame.Rect(1, round(top_cy), w - 2, round(h - top_cy - h * 0.18))
    pygame.draw.rect(surf, color, body_rect)

    bumps = 4
    bump_w = (w - 2) / bumps
    base_y = h - h * 0.18
    phase = 0 if frame == 1 else 1
    points = [(1.0, base_y)]
    for i in range(bumps):
        x0 = 1 + i * bump_w
        xm = x0 + bump_w / 2
        x1 = x0 + bump_w
        peak_y = base_y + (h * 0.16 if (i + phase) % 2 == 0 else h * 0.04)
        points.append((xm, peak_y))
        points.append((x1, base_y))
    points.append((float(w - 1), base_y))
    points.append((float(w - 1), float(h - 2)))
    points.append((1.0, float(h - 2)))
    pygame.draw.polygon(surf, color, points)

    if face == "normal":
        eye_y = top_cy - radius * 0.05
        for dx in (-radius * 0.38, radius * 0.38):
            ex = cx + dx
            pygame.draw.ellipse(
                surf,
                (245, 245, 255),
                (round(ex - radius * 0.24), round(eye_y - radius * 0.30), round(radius * 0.48), round(radius * 0.58)),
            )
            pygame.draw.ellipse(
                surf,
                (25, 25, 130),
                (round(ex - radius * 0.09), round(eye_y - radius * 0.08), round(radius * 0.22), round(radius * 0.3)),
            )
    else:  # frightened / spooked face
        brow_y = top_cy - radius * 0.15
        for dx, tilt in ((-radius * 0.35, -1), (radius * 0.35, 1)):
            ex = cx + dx
            pygame.draw.line(
                surf,
                (235, 235, 245),
                (ex - radius * 0.18, brow_y + tilt * radius * 0.05),
                (ex + radius * 0.18, brow_y - tilt * radius * 0.05),
                2,
            )
        mouth_y = top_cy + radius * 0.35
        seg = radius * 0.16
        wiggle_points = []
        for i in range(5):
            x = cx - radius * 0.32 + i * seg
            y = mouth_y + (radius * 0.1 if i % 2 == 0 else -radius * 0.02)
            wiggle_points.append((x, y))
        pygame.draw.lines(surf, (235, 235, 245), False, wiggle_points, 2)

    return surf


def make_ghost(size, color, frame):
    return _ghost_shape(size, color, frame, face="normal")


def make_frightened(size, frame, flashing=False):
    color = (255, 255, 255) if (flashing and frame == 1) else (36, 64, 224)
    return _ghost_shape(size, color, frame, face="scared")


def make_eyes(size, direction):
    w, h = size
    surf = _surface(size)
    cx, cy = w / 2.0, h / 2.0
    r = min(w, h) * 0.22
    dxn, dyn = DIRECTION_VECTORS[direction]
    for dx in (-w * 0.19, w * 0.19):
        ex, ey = cx + dx, cy
        pygame.draw.ellipse(
            surf, (255, 255, 255), (round(ex - r), round(ey - r * 1.25), round(r * 2), round(r * 2.5))
        )
        pupil_x = ex + dxn * r * 0.55
        pupil_y = ey + dyn * r * 0.55
        pygame.draw.circle(surf, (30, 30, 130), (round(pupil_x), round(pupil_y)), max(1, round(r * 0.55)))
    return surf


# --- Maze tiles ---------------------------------------------------------------------
def make_wall(size):
    w, h = size
    surf = _surface(size)
    base = (24, 54, 116)     # CMU-ish blue
    highlight = (66, 110, 190)
    pygame.draw.rect(surf, base, (0, 0, w, h))
    pygame.draw.rect(surf, highlight, (1, 1, w - 2, h - 2), 1)
    pygame.draw.line(surf, highlight, (0, h // 2), (w, h // 2), 1)
    pygame.draw.line(surf, highlight, (w // 2, 0), (w // 2, h // 2), 1)
    pygame.draw.line(surf, highlight, (w // 4, h // 2), (w // 4, h), 1)
    pygame.draw.line(surf, highlight, (3 * w // 4, h // 2), (3 * w // 4, h), 1)
    return surf


def make_pellet(size):
    w, h = size
    surf = _surface(size)
    r = max(2, min(w, h) // 8)
    pygame.draw.circle(surf, (255, 222, 140), (w // 2, h // 2), r)
    return surf


def make_power_pellet(size):
    w, h = size
    surf = _surface(size)
    r = max(4, min(w, h) // 3)
    pygame.draw.circle(surf, (255, 222, 140), (w // 2, h // 2), r)
    pygame.draw.circle(surf, (255, 255, 255), (w // 2, h // 2), r, 1)
    return surf


def make_gate(size):
    w, h = size
    surf = _surface(size)
    pygame.draw.rect(surf, (255, 140, 190), (0, round(h * 0.42), w, round(h * 0.16)))
    return surf


def make_life_icon(size):
    return make_scotty(size, "right", 1)


# --- Fruit (Skibo Cafe menu, CMU-themed) ----------------------------------------------
def fruit_bagel(size):
    w, h = size
    surf = _surface(size)
    cx, cy, r = w / 2, h / 2, min(w, h) / 2 - 2
    pygame.draw.circle(surf, (196, 148, 88), (round(cx), round(cy)), round(r))
    pygame.draw.circle(surf, TRANSPARENT, (round(cx), round(cy)), round(r * 0.4))
    pygame.draw.circle(surf, (150, 108, 58), (round(cx), round(cy)), round(r), 1)
    return surf


def fruit_coffee(size):
    w, h = size
    surf = _surface(size)
    cup = pygame.Rect(round(w * 0.26), round(h * 0.32), round(w * 0.5), round(h * 0.52))
    pygame.draw.rect(surf, (250, 250, 250), cup, border_radius=2)
    pygame.draw.rect(
        surf, (92, 58, 24), (cup.x + 2, cup.y + 2, cup.width - 4, round(cup.height * 0.35))
    )
    pygame.draw.arc(
        surf, (250, 250, 250), (cup.right - 4, cup.y + round(cup.height * 0.15), 8, round(cup.height * 0.6)),
        -1.6, 1.6, 2,
    )
    return surf


def fruit_cookie(size):
    w, h = size
    surf = _surface(size)
    cx, cy, r = w / 2, h / 2, min(w, h) / 2 - 2
    pygame.draw.circle(surf, (185, 134, 82), (round(cx), round(cy)), round(r))
    for dx, dy in [(-0.3, -0.2), (0.2, -0.3), (0.0, 0.1), (0.3, 0.25), (-0.25, 0.3)]:
        pygame.draw.circle(surf, (92, 56, 26), (round(cx + dx * r), round(cy + dy * r)), max(1, round(r * 0.16)))
    return surf


def fruit_milkshake(size):
    w, h = size
    surf = _surface(size)
    pygame.draw.polygon(
        surf,
        (255, 182, 213),
        [
            (w * 0.3, h * 0.32),
            (w * 0.7, h * 0.32),
            (w * 0.64, h * 0.86),
            (w * 0.36, h * 0.86),
        ],
    )
    pygame.draw.rect(surf, (255, 255, 255), (round(w * 0.46), round(h * 0.06), round(w * 0.08), round(h * 0.32)))
    return surf


def fruit_pizza(size):
    w, h = size
    surf = _surface(size)
    pygame.draw.polygon(surf, (232, 192, 122), [(w * 0.5, h * 0.1), (w * 0.86, h * 0.86), (w * 0.14, h * 0.86)])
    pygame.draw.polygon(surf, (204, 62, 52), [(w * 0.5, h * 0.28), (w * 0.7, h * 0.76), (w * 0.3, h * 0.76)])
    for dx, dy in [(-0.08, 0.05), (0.1, 0.15), (-0.02, 0.24)]:
        pygame.draw.circle(surf, (150, 32, 32), (round(w * 0.5 + dx * w), round(h * 0.5 + dy * h)), max(1, round(w * 0.05)))
    return surf


def fruit_taco(size):
    w, h = size
    surf = _surface(size)
    pygame.draw.polygon(
        surf, (232, 190, 92), [(w * 0.1, h * 0.55), (w * 0.5, h * 0.16), (w * 0.9, h * 0.55), (w * 0.5, h * 0.72)]
    )
    pygame.draw.polygon(
        surf, (122, 172, 82), [(w * 0.22, h * 0.5), (w * 0.5, h * 0.32), (w * 0.78, h * 0.5), (w * 0.5, h * 0.62)]
    )
    return surf


def fruit_sushi(size):
    w, h = size
    surf = _surface(size)
    cx, cy, r = w / 2, h / 2, min(w, h) / 2 - 2
    pygame.draw.circle(surf, (250, 250, 250), (round(cx), round(cy)), round(r))
    pygame.draw.rect(surf, (32, 30, 28), (round(w * 0.15), round(h * 0.38), round(w * 0.7), round(h * 0.24)))
    pygame.draw.circle(surf, (232, 104, 124), (round(cx), round(cy)), round(r * 0.32))
    return surf


def fruit_boba(size):
    w, h = size
    surf = _surface(size)
    pygame.draw.polygon(
        surf,
        (214, 178, 132),
        [(w * 0.28, h * 0.24), (w * 0.72, h * 0.24), (w * 0.66, h * 0.86), (w * 0.34, h * 0.86)],
    )
    for dx, dy in [(-0.08, 0.62), (0.05, 0.68), (-0.02, 0.74), (0.1, 0.7)]:
        pygame.draw.circle(surf, (44, 28, 18), (round(w * 0.5 + dx * w), round(h * dy)), max(1, round(w * 0.05)))
    return surf


FRUIT_GENERATORS = [
    fruit_bagel,
    fruit_coffee,
    fruit_cookie,
    fruit_milkshake,
    fruit_pizza,
    fruit_taco,
    fruit_sushi,
    fruit_boba,
]


def _build_generators():
    generators = {
        "wall": make_wall,
        "pellet": make_pellet,
        "power_pellet": make_power_pellet,
        "gate": make_gate,
        "life_icon": make_life_icon,
        "ghost_frightened_1": lambda size: make_frightened(size, 1),
        "ghost_frightened_2": lambda size: make_frightened(size, 2),
        "ghost_frightened_flash_1": lambda size: make_frightened(size, 1, flashing=True),
        "ghost_frightened_flash_2": lambda size: make_frightened(size, 2, flashing=True),
    }
    for direction in ("up", "down", "left", "right"):
        for frame in (1, 2):
            key = f"scotty_{direction}_{frame}"
            generators[key] = (lambda size, d=direction, f=frame: make_scotty(size, d, f))
        generators[f"eyes_{direction}"] = (lambda size, d=direction: make_eyes(size, d))

    ghost_colors = {
        "gates": GATES_COLOR,
        "hunt": HUNT_COLOR,
        "wean": WEAN_COLOR,
        "doherty": DOHERTY_COLOR,
    }
    for name, color in ghost_colors.items():
        for frame in (1, 2):
            key = f"ghost_{name}_{frame}"
            generators[key] = (lambda size, c=color, f=frame: make_ghost(size, c, f))

    for index in range(8):
        key = f"fruit_{index}"
        generators[key] = (lambda size, i=index: FRUIT_GENERATORS[i](size))

    return generators


GENERATORS = _build_generators()


def main() -> int:
    sprites_dir = ASSETS_ROOT / "sprites"
    sprites_dir.mkdir(parents=True, exist_ok=True)

    missing = sorted(set(SPRITE_SPECS) - set(GENERATORS))
    if missing:
        raise SystemExit(f"no placeholder generator registered for: {missing}")

    for name, (rel_path, size) in sorted(SPRITE_SPECS.items()):
        surface = GENERATORS[name](size)
        out_path = REPO_ROOT / "assets" / rel_path
        pygame.image.save(surface, str(out_path))
        print(f"wrote {out_path.relative_to(REPO_ROOT)}")

    print(f"generated {len(SPRITE_SPECS)} placeholder sprites")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
