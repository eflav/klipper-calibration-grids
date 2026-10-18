# Klipper calibration grids

Two small Python scripts that write ready-to-print G-code calibration tests
for Klipper printers. No slicer involved: each script generates every move
directly, so one file tests a whole grid of settings in a single print.

Written for a Sovol SV07 (220 x 220 bed, 0.4 mm nozzle, PLA) running Klipper,
but every dimension, temperature and speed is a constant at the top of each
script.

| Script | What it tests | Output |
|---|---|---|
| `make_first_layer_grid.py` | Nozzle height (Z offset) across, first-layer flow down | `first_layer_grid.gcode` |
| `make_ironing_grid.py` | Ironing speed across, ironing flow down | `ironing_grid.gcode` |

The included `.gcode` files are the output of the scripts as committed, and the
`.png` files are top-down previews of the toolpaths.

## First layer grid

![first layer grid](first_layer_grid.png)

A grid of single-layer 18 mm squares. Each column is printed at a different
nozzle height relative to your current probe `z_offset` (labelled in 0.01 mm
units, so `+9` is 0.09 mm higher). Each row uses a different first-layer flow
percentage. Labels are printed on the bed next to the grid.

Pick the square that is smooth and matte, with the lines fused and no gaps or
ridges, and that lifts off as one sheet. Then:

- Flow row: set it as the slicer's first-layer flow (Cura: *Initial Layer Flow*).
- Z column: new `z_offset` = current `z_offset` **minus** the column value.
  A winning column of `-3` with a `z_offset` of 1.800 means 1.830.

If the winner sits on an edge of the grid, shift `Z_OFFSETS` or `FLOWS` in
that direction and run it again. If the same physical spot on the bed wins
regardless of its label, suspect the bed mesh or screw levelling in that
corner, not the setting. Mirroring the lists is a quick way to check.

## Ironing grid

![ironing grid](ironing_grid.png)

A grid of discs with identical bases, each ironed with its column's speed and
its row's flow at a fixed line spacing. Compare under a lamp at a low angle.
Visible lines between passes mean too little flow or too wide a spacing;
a raised rim or shiny bumps at the edge mean too much flow. Take the fastest
speed that still matches its slower neighbours.

Cura equivalents: *Ironing Flow*, *Ironing Speed*, *Ironing Line Spacing*.

## Running

```
python make_first_layer_grid.py
python make_ironing_grid.py
```

Python 3, standard library only. Each script writes its `.gcode` next to
itself. Upload the file through Mainsail or Fluidd and print it.

## Adapting to your printer

Both scripts start with:

```
M140 / M104 / M190 / M109   heat and wait
START_PRINT                 your Klipper start macro
...
END_PRINT                   your Klipper end macro
```

Change `START_PRINT` and `END_PRINT` to whatever your config uses, or replace
them with a plain `G28` and a park move. Also check:

- `GRID_X0`, `GRID_Y0`, `PITCH`: position and spacing on your bed.
- `LINE_W`: the first-layer grid uses 0.66 mm to match Cura's default 150%
  first-layer line width on a 0.4 mm nozzle.
- `TEMP_*`, `BED_TEMP`, `SPEED_*`: material and machine limits.
- `RESPOND` lines print the legend to the console; remove them if your
  config has no `[respond]` section.

The scripts use relative extrusion (`M83`) and absolute XY (`G90`).
