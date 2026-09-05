# PacDawg

An original, CMU-themed maze-chase arcade game starring **Scotty**, the
CMU mascot, versus four ghosts with genuinely different chase
personalities. Built for the CMU-Q arcade cabinet and its
[ArcadeLauncher](https://github.com/GDC-CMU/ArcadeLauncher).

This is not a Pac-Man clone with the serial numbers filed off: the
mazes, art direction, character, and ghost AI are all original, authored
for this project (see [Design notes](#design-notes) below). Maze-chase
as a genre is fair game; Bandai Namco's specific maze layout, sprites,
and name are not, and this project doesn't reproduce them.

![Title screen with the ghost cast roster and high score](docs/screenshots/title_screen.png)

## What it is

- A proper title/attract screen naming the real arcade buttons and
  showing the ghost cast, shown on launch and again after every game
  over -- see [Controls](#controls).
- Four campus-themed mazes-worth of original layouts (**The Cut**, **The
  Fence**, **Skibo**), cycling forever and speeding up as you go.
- Four ghosts with genuinely different targeting algorithms (not one
  rule recolored four times) -- see [Design notes](#design-notes).
- Movement speeds, per-level timing, scatter/chase/frightened durations,
  Cruise Elroy, and ghost-house release logic are transcribed from
  documented Pac-Man (1980) ROM-derived data, scaled to our maze size --
  see [Difficulty is documented, not invented](#difficulty-is-documented-not-invented).
- A proper scatter/chase/frightened state machine, power pellets, combo
  scoring for eating multiple ghosts in one frightened window, bonus
  fruit themed after the Skibo Cafe menu, lives, an extra life at
  10,000 points, and a persisted high score.
- **All gameplay art is swappable PNGs** -- see [Swapping in real
  art](#swapping-in-real-art).

![Ready screen with all four ghosts in the house](docs/screenshots/gameplay_03_ready.png)

![Mid-level gameplay with the four ghosts spread across the maze](docs/screenshots/gameplay_01.png)

![Frightened and eaten ghosts, plus a Skibo-themed bonus fruit](docs/screenshots/gameplay_02.png)

![Game over screen returning to the title, not quitting](docs/screenshots/game_over_screen.png)

## Controls

### Arcade cabinet

| Input | Action |
|---|---|
| Joystick (either connected stick), axis 0/1 | Steer Scotty |
| Button 1 (A) or Button 9 (Start) | Confirm / start |
| **Button 5 (P1)** | **Exit immediately**, from any screen, back to the launcher |

The cabinet has two identical joystick devices; either one can steer.
Hot-plugging (disconnecting/reconnecting a stick mid-game) is handled
without crashing.

The title screen (shown on launch and again after every game over) is
the one place that tells a visitor how to start and that P1 exits back
to the launcher's gallery, since the gallery itself doesn't say so.

### Keyboard (development)

| Input | Action |
|---|---|
| Arrow keys or WASD | Steer Scotty |
| Enter / Space | Confirm / start |
| Esc | Exit immediately |

## Running locally

Requires Python 3.10+ and `pygame-ce`.

```
pip install -r requirements.txt
python main.py
```

To run headlessly (no display, e.g. in CI or over SSH):

```
# Windows PowerShell
$env:SDL_VIDEODRIVER = "dummy"; python main.py

# bash
SDL_VIDEODRIVER=dummy python main.py
```

## Running the tests

The whole game is unit-tested headlessly, with no real display or
hardware required:

```
python -m unittest discover -s tests -v
```

Coverage includes maze parsing and validation (including malformed
layouts being rejected loudly), each ghost personality picking a
different target from identical game state, the scatter/chase/frightened
state machine, scoring and the ghost-eating combo, pellet accounting and
level completion, asset fallback behavior, working-directory
independence, and the arcade exit contract (800x600 display, P1 exits
via `sys.exit(0)` from any state).

## How it's deployed

The [ArcadeLauncher](https://github.com/GDC-CMU/ArcadeLauncher) spawns
each game as `[sys.executable, "main.py"]` with `cwd` set to this
checkout, in its own virtualenv built from `requirements.txt`. That's why
`main.py` lives at the repo root with no arguments, and why every asset
and maze path is resolved from `__file__` rather than the current
working directory -- the game has to work no matter where the launcher
runs it from.

Button 5 (P1) exits via `sys.exit(0)` immediately, from any state, which
is the documented contract the launcher relies on to return the visitor
to its gallery.

## Swapping in real art

The client's brief was explicit: gameplay art must come from PNG files,
not code, so it's trivial to hand real assets to an artist later. See
[`assets/README.md`](assets/README.md) for the full sprite reference --
every expected file, its nominal size, and what it's used for. The short
version: **overwrite a file in `assets/sprites/` with the same name and
you're done, no code changes required.** Everything currently there is a
deterministically-generated placeholder (`tools/generate_placeholders.py`),
not final art.

## Tuning difficulty

Every tunable knob -- speeds, scatter/chase timing, frightened duration,
ghost house release timing, scoring, the extra-life threshold, fruit
thresholds -- lives in one place: [`pacdawg/config.py`](pacdawg/config.py).
Nothing else in the codebase hard-codes a difficulty number.

## Difficulty is documented, not invented

Every speed, timing, and threshold in `config.py` is transcribed from
Jamey Pittman's *The Pac-Man Dossier* (a ROM-disassembly-derived
reference), cross-checked against Don Hodges' Z80 analysis and two
high-fidelity open-source clones -- not estimated. The base speed
(9.4697 tiles/sec at 100%), per-level speed bands, scatter/chase
timetable (including the ~17-minute third chase and the pause while any
ghost is frightened), frightened duration/flash counts (including the
documented non-monotonic jumps at levels 6, 10, and 14), Cruise Elroy,
and the ghost-house release counters all carry a comment citing the
source. Every documented value that's expressed as an absolute dot count
(Elroy thresholds, ghost-house release counters, fruit triggers) is
scaled proportionally to our maze's actual pellet count, since our mazes
aren't the original's 244-dot 28x36 grid. A handful of values the Dossier
itself flags as undocumented (eaten-ghost "eyes" speed, in-house pacing
speed) follow the same estimates the reference clones use, noted in
`config.py` as such.

Scotty's controls follow the documented cornering/pre-turn model rather
than a timed input buffer: a held direction is re-evaluated every frame
against Scotty's current tile and takes effect immediately, wherever
inside the tile he is, and he drifts diagonally toward a new lane's
centerline while cornering. Ghosts do not get this treatment -- they may
only change direction on an exact tile center -- which is the documented
mechanical basis of the player's speed advantage over them.

## Architecture

Pure game logic is kept separate from rendering so it's fully testable
without a display:

```
main.py                  entrypoint (the launcher invokes this exact path)
pacdawg/
  config.py              every tunable in one place
  maze.py                tile grid, text-layout parsing, pellet accounting
  levels.py              the original CMU-themed layouts + per-level tuning
  entities.py            Scotty + tile-aligned movement, tunnels
  ghosts.py              four personalities + scatter/chase/frightened machine
  game.py                state machine: attract -> ready -> play -> death -> ...
  score.py               scoring, lives, extra life, high-score persistence
  input.py               joystick + keyboard intent resolution
  assets.py              the single point of PNG access (see assets/README.md)
  render.py              draws only from assets.py surfaces, plus HUD text
tools/generate_placeholders.py
tests/
docs/screenshots/
```

Only `game.py`, `render.py`, and `assets.py` import `pygame`; every other
module is plain Python so it can be driven and asserted against directly
in tests.

## Design notes

### The four ghosts

Named after CMU campus landmarks, each with a genuinely different
targeting algorithm (see `pacdawg/ghosts.py`):

- **Gates** -- a direct chaser. Always targets Scotty's exact tile.
- **Hunt** -- an ambusher. Targets four tiles *ahead* of wherever Scotty
  is facing, trying to cut him off before he arrives -- including the
  documented "facing up" quirk (see below).
- **Wean** -- a flanker. Its target is Gates' position reflected through
  a point ahead of Scotty, so it swings in from an angle that depends on
  where Gates currently is.
- **Doherty** -- shy. Chases aggressively from eight tiles or more away,
  but flees back toward its home corner once it gets closer, so it never
  quite commits to the kill alone. Once low on remaining pellets, Gates
  enters "Cruise Elroy" mode: it speeds up in two stages and starts
  targeting Scotty directly even during scatter.

Hunt and Wean deliberately reproduce a documented original-game ROM bug:
targeting "N tiles in the direction Scotty is facing" overflows when
facing up, becoming "N tiles up **and** N tiles left" instead of just up.
This is a genuine artifact of how the original computed the offset (Don
Hodges' Z80 analysis), not an oversight here -- it's part of what makes
those two personalities beatable by facing up near them.

All four alternate between scatter (heading for a home corner) and chase
phases on a per-level timetable that pauses while any ghost is
frightened, turn frightened (and eventually flash a warning) after a
power pellet, and become eyes-only when eaten, racing back to the ghost
house before rejoining the chase.

### Mazes

Three original layouts -- **The Cut**, **The Fence**, **Skibo** -- named
after CMU landmarks, authored as plain text grids in `pacdawg/levels.py`
and validated at load time (every pellet must be reachable, exactly one
player start, a well-formed tunnel, etc.). Levels cycle through them
forever, getting faster each time.
