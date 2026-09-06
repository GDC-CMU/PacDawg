#!/usr/bin/env python
"""Generate the ArcadeLauncher's attract-mode preview animation from the
real game.

The launcher's own gallery attract mode plays a short looping animation
inside each game's card. It cannot run another process's game loop to
produce that (separate processes; the launcher owns SDL), so each game
ships a small pre-rendered loop instead -- see the cross-repo contract
this must match, ``preview-contract.md``.

This script drives PacDawg's actual attract-mode demo (the same one
shown in-game after 15 seconds idle -- see ``pacdawg.game.Game._enter_demo``)
headlessly, captures a handful of frames through the real render path
(``pacdawg.render.draw_frame``), downsamples them to card size, and
writes them plus ``manifest.json`` to ``assets/preview/``.

Deterministic by construction, so running this twice leaves ``git
status`` clean:

* The demo's RNG is seeded with a fixed constant (SEED below).
* Every simulated frame advances by the same fixed ``DT``, never real
  elapsed wall-clock time.
* The game's own ``gameplay_time`` sprite clock advances by that same
  fixed ``DT`` through ``Game.update()``, never wall time. It is also
  the clock frozen by the in-game pause menu.
* The high score shown in the captured HUD is pinned to a fixed
  constant (PINNED_HIGH_SCORE below) rather than left to read the real,
  persisted ``highscore.json``. ``Game()`` loads that file at
  construction time, and it is genuinely mutable shared state -- any
  other game session (a real play session, a test run, this very tool
  run previously) can commit a new high score to it between two
  invocations of this generator, which would otherwise change a
  handful of pixels in the rendered "HIGH ######" text and break
  byte-for-byte reproducibility for a reason that has nothing to do
  with the demo itself. This was the actual, confirmed source of the
  non-determinism this tool originally shipped with.
"""
from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pacdawg import config, render  # noqa: E402
from pacdawg.game import Game, GameState  # noqa: E402
from pacdawg.input import RawInput  # noqa: E402

# --- Tunables ---------------------------------------------------------------
# A build-time tool, not a runtime setting -- deliberately kept here
# rather than in pacdawg/config.py.
SEED = 20260115  # fixed: pins every rng.uniform()/rng-driven choice the demo makes
# Fixed, arbitrary stand-in for whatever the real persisted high score
# happens to be right now -- see the module docstring for why reading
# the real highscore.json here would break determinism.
PINNED_HIGH_SCORE = 12000
# Chosen by sampling the demo over two minutes and picking a stretch
# where multiple ghosts are simultaneously within a handful of tiles of
# Scotty while hunting (CHASE) -- reads as an active, multi-ghost chase
# rather than empty corridor. All four ghosts have long since left the
# house by here.
WARMUP_SECONDS = 49.0
FPS = 8
# Unique captured frames. The manifest plays these forward then
# backward (see _ping_pong_sequence()) rather than looping straight
# back to frame 0 -- the demo is continuously moving, so a straight
# loop would jump-cut back to an earlier position every cycle. A
# forward-then-reverse "boomerang" sequence is seamless by
# construction: every step, including the wrap, is an adjacent pair
# from the same real, continuous capture.
FRAME_COUNT = 9  # 1.125s of unique motion; the boomerang below doubles it to ~2s
SIM_HZ = 60  # the real game's simulation rate; DT below matches it exactly
DT = 1.0 / SIM_HZ
FRAME_PERIOD_SECONDS = 1.0 / FPS
OUT_WIDTH, OUT_HEIGHT = 200, 150
OUT_DIR = REPO_ROOT / "assets" / "preview"


def _ping_pong_sequence(names: list) -> list:
    """Forward then reverse, excluding the two endpoints from the
    reverse leg so they aren't held for a doubled frame: [0, 1, ..., N,
    N-1, ..., 1] then wraps back to 0. Every adjacent pair in this
    sequence -- including the wrap from the last entry back to the
    first -- is a real, adjacent pair from the original continuous
    capture, so the loop has no jump-cut anywhere."""
    if len(names) < 2:
        return list(names)
    return list(names) + list(reversed(names[1:-1]))


def _render_clean_frame(screen, game: Game) -> None:
    """Render one frame via the real render path, but as if it were
    ordinary gameplay: no DEMO tag, no PACDAWG title overlay. Those are
    useful in-game (they tell a visitor this isn't a stuck real game)
    but would be redundant clutter inside a launcher card that already
    names the game and only ever shows the play area."""
    real_state = game.state
    game.state = GameState.PLAYING
    try:
        render.draw_frame(screen, game)
    finally:
        game.state = real_state


def main() -> int:
    pygame.init()
    screen = pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))

    game = Game(rng=random.Random(SEED))
    # Pin the high score before entering the demo -- see the module
    # docstring for why reading the real persisted value here would
    # break determinism. _enter_demo() seeds the demo's disposable
    # ScoreBoard from whatever game.score.high_score currently is, so
    # setting it here (before the swap) is enough to make the captured
    # HUD's "HIGH ######" text fully independent of highscore.json.
    game.score.high_score = PINNED_HIGH_SCORE
    game._enter_demo()
    idle = RawInput()

    warmup_ticks = int(round(WARMUP_SECONDS * SIM_HZ))
    for _ in range(warmup_ticks):
        game.update(DT, idle)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Remove any stale frames from a previous run with a different
    # FRAME_COUNT, so the directory never accumulates orphans.
    for existing in OUT_DIR.glob("frame_*.png"):
        existing.unlink()

    frame_names = []
    elapsed_since_capture = 0.0
    while len(frame_names) < FRAME_COUNT:
        game.update(DT, idle)
        elapsed_since_capture += DT
        # Sample at 60Hz but capture on average every FRAME_PERIOD_SECONDS
        # of *simulated* time (7.5 ticks at 60Hz/8fps) -- not a rounded
        # integer tick stride, which would drift the loop's real-time
        # pace away from what FPS in the manifest claims.
        if elapsed_since_capture >= FRAME_PERIOD_SECONDS - 1e-9:
            elapsed_since_capture -= FRAME_PERIOD_SECONDS
            _render_clean_frame(screen, game)
            small = pygame.transform.scale(screen, (OUT_WIDTH, OUT_HEIGHT))
            name = f"frame_{len(frame_names):03d}.png"
            pygame.image.save(small, str(OUT_DIR / name))
            frame_names.append(name)

    manifest_frames = _ping_pong_sequence(frame_names)
    manifest = {"version": 1, "fps": FPS, "frames": manifest_frames}
    manifest_path = OUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(
        f"wrote {len(frame_names)} unique frames ({OUT_WIDTH}x{OUT_HEIGHT} @ {FPS}fps), "
        f"{len(manifest_frames)}-entry ping-pong sequence, to {OUT_DIR}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
