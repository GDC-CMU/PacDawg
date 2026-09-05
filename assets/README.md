# PacDawg art assets

All gameplay art is loaded from the PNG files in `assets/sprites/` through
the single loader in `pacdawg/assets.py`. Nothing else in the codebase
draws gameplay sprites procedurally, and nothing reads a sprite path
directly -- every file below is declared once in
`pacdawg.assets.SPRITE_SPECS` (name -> relative path -> nominal pixel
size).

**To replace any piece of art, overwrite the file at the same path with
the same name, keeping (roughly) the same aspect ratio. No code changes
are required.** Every sprite is loaded once at first use, cached, and
scaled to its nominal tile size, so files of a different resolution
still work (they're rescaled), but keeping them native-sized avoids any
blur from upscaling.

Everything currently committed in `assets/sprites/` is a **placeholder**,
generated deterministically by `tools/generate_placeholders.py`. Re-run
that script any time you want to reset the stock look (for example after
adding a new logical sprite name to `SPRITE_SPECS`):

```
python tools/generate_placeholders.py
```

Missing or unreadable files never crash the game -- a bright magenta
placeholder with a crossed-out look is substituted, and a single warning
is printed to stderr, so an in-progress art pass never blocks testing.

## Tile size

The maze is drawn at **20x20 pixels per tile** (`pacdawg/config.py`,
`TILE_SIZE`). Most sprites are nominally 20x20; a couple of HUD icons are
smaller. If you change `TILE_SIZE`, update the nominal sizes in
`SPRITE_SPECS` to match for the crispest result (or leave a mismatch --
it will simply be rescaled).

## Sprite reference

### Maze tiles (`assets/sprites/`)

| File | Size | Used for |
|---|---|---|
| `wall.png` | 20x20 | Every maze wall tile. Tiled edge-to-edge, so this should look reasonable when repeated. |
| `gate.png` | 20x20 | The ghost-house door (the tile Scotty can't pass but ghosts can). |
| `pellet.png` | 20x20 | A regular dot. Rendered centered on its tile, so plenty of transparent margin is expected. |
| `power_pellet.png` | 20x20 | A power pellet. Same centering as above. |

### Scotty -- the player character

Scotty is a small, shaggy Scottish Terrier: **CMU's mascot**, not a
yellow circle. He has two animation frames per facing direction (a
simple "legs/mouth" alternation used for the walk animation):

| Files | Size | Used for |
|---|---|---|
| `scotty_up_1.png`, `scotty_up_2.png` | 20x20 | Facing up |
| `scotty_down_1.png`, `scotty_down_2.png` | 20x20 | Facing down |
| `scotty_left_1.png`, `scotty_left_2.png` | 20x20 | Facing left |
| `scotty_right_1.png`, `scotty_right_2.png` | 20x20 | Facing right |
| `life_icon.png` | 16x16 | The small "lives remaining" icon in the HUD. Can be a simplified/cropped version of Scotty. |

### Ghosts -- four distinct personalities

Each of the four ghosts (see `pacdawg/ghosts.py` for what makes them
behave differently) has its own two-frame walk animation, plus shared
frightened/eaten states:

| Files | Size | Used for |
|---|---|---|
| `ghost_gates_1.png`, `ghost_gates_2.png` | 20x20 | **Gates** -- the direct chaser (red) |
| `ghost_hunt_1.png`, `ghost_hunt_2.png` | 20x20 | **Hunt** -- the ambusher (pink) |
| `ghost_wean_1.png`, `ghost_wean_2.png` | 20x20 | **Wean** -- the flanker (cyan) |
| `ghost_doherty_1.png`, `ghost_doherty_2.png` | 20x20 | **Doherty** -- the shy one (orange) |
| `ghost_frightened_1.png`, `ghost_frightened_2.png` | 20x20 | Any ghost, blue, right after a power pellet |
| `ghost_frightened_flash_1.png`, `ghost_frightened_flash_2.png` | 20x20 | Any ghost, flashing white/blue in the last couple of seconds before frightened mode ends |
| `eyes_up.png`, `eyes_down.png`, `eyes_left.png`, `eyes_right.png` | 20x20 | An eaten ghost's eyes, racing back to the ghost house |

The four ghost colors are deliberately distinct (red/pink/cyan/orange)
so they read clearly even before an artist touches them; keep them
visually distinguishable from each other and from Scotty when replacing.

### Fruit -- CMU/Skibo-themed bonus items

Bonus fruit cycles through eight items themed after the Skibo Cafe menu
rather than generic fruit, one per difficulty level (repeating after
level 8):

| File | Size | Flavor |
|---|---|---|
| `fruit_0.png` | 20x20 | Bagel |
| `fruit_1.png` | 20x20 | Coffee |
| `fruit_2.png` | 20x20 | Cookie |
| `fruit_3.png` | 20x20 | Milkshake |
| `fruit_4.png` | 20x20 | Pizza slice |
| `fruit_5.png` | 20x20 | Taco |
| `fruit_6.png` | 20x20 | Sushi |
| `fruit_7.png` | 20x20 | Boba tea |

## Adding a brand-new sprite

1. Add an entry to `SPRITE_SPECS` in `pacdawg/assets.py` (name, relative
   path, nominal size).
2. Add a matching generator function in `tools/generate_placeholders.py`
   so the placeholder set stays complete, then run the script.
3. Reference the new sprite by name from `pacdawg/render.py` with
   `assets.get("your_new_name")`.
