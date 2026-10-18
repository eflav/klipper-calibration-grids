"""
First layer calibration grid for Klipper (Sovol SV07, 0.4 mm nozzle, PLA).

Prints a grid of single-layer 18 mm squares. Columns vary the nozzle height
(Z offset relative to your current probe z_offset, in 0.01 mm units on the
labels). Rows vary first layer flow in percent. Labels are printed on the bed.

Each square is printed at Cura's first layer line width (0.66 mm, the SV07
definition's 150%), so the winning flow row goes straight into Cura's
"Initial Layer Flow" and the winning Z column is applied to the probe
z_offset in printer.cfg (see the notes printed when the script runs).

Edit Z_OFFSETS, FLOWS or any constant below, then run:
    python make_first_layer_grid.py
It writes first_layer_grid.gcode next to this script.
"""
import math
import os

# ---------------------------------------------------------------- settings
Z_OFFSETS = [0.09, 0.06, 0.03, 0.00, -0.03, -0.06, -0.09]   # mm, one per column; negative = nozzle closer to bed
FLOWS = [130, 120, 110, 100, 90, 80]                        # %, one per row, front to back

PATCH = 18.0           # square side, mm
PITCH = 22.0           # centre to centre
GRID_X0 = 48.0         # centre of the first column
GRID_Y0 = 42.0         # centre of the first row
LAYER_H = 0.2          # nominal first layer height
LINE_W = 0.66          # first layer line width (Cura: 0.44 x 150%)
WALLS = 1
FILAMENT_D = 1.75

TEMP_FIRST = 220
BED_TEMP = 60
SPEED_FIRST = 30       # mm/s, walls and fill
SPEED_TRAVEL = 120
ACCEL = 1000
RETRACT = 0.8
RETRACT_SPEED = 45
Z_HOP = 0.6
TEXT_H = 4.0
TEXT_W = 0.44          # labels use normal line width
TEXT_LAYERS = 2

# ---------------------------------------------------------------- stroke font (2 wide x 4 tall grid)
FONT = {
    "0": [[(0, 0), (2, 0), (2, 4), (0, 4), (0, 0)]],
    "1": [[(1, 0), (1, 4)]],
    "2": [[(0, 4), (2, 4), (2, 2), (0, 2), (0, 0), (2, 0)]],
    "3": [[(0, 4), (2, 4), (2, 0), (0, 0)], [(0, 2), (2, 2)]],
    "4": [[(0, 4), (0, 2), (2, 2)], [(2, 4), (2, 0)]],
    "5": [[(2, 4), (0, 4), (0, 2), (2, 2), (2, 0), (0, 0)]],
    "6": [[(2, 4), (0, 4), (0, 0), (2, 0), (2, 2), (0, 2)]],
    "7": [[(0, 4), (2, 4), (2, 0)]],
    "8": [[(0, 0), (2, 0), (2, 4), (0, 4), (0, 0)], [(0, 2), (2, 2)]],
    "9": [[(0, 0), (2, 0), (2, 4), (0, 4), (0, 2), (2, 2)]],
    "-": [[(0, 2), (2, 2)]],
    "+": [[(0, 2), (2, 2)], [(1, 1), (1, 3)]],
    "Z": [[(0, 4), (2, 4), (0, 0), (2, 0)]],
    "O": [[(0, 0), (2, 0), (2, 4), (0, 4), (0, 0)]],
    "F": [[(2, 4), (0, 4), (0, 0)], [(0, 2), (1.5, 2)]],
    "S": [[(2, 4), (0, 4), (0, 2), (2, 2), (2, 0), (0, 0)]],
    "E": [[(2, 4), (0, 4), (0, 0), (2, 0)], [(0, 2), (1.5, 2)]],
    "T": [[(0, 4), (2, 4)], [(1, 4), (1, 0)]],
    "L": [[(0, 4), (0, 0), (2, 0)]],
    "W": [[(0, 4), (0.5, 0), (1, 2), (1.5, 0), (2, 4)]],
    "M": [[(0, 0), (0, 4), (1, 2), (2, 4), (2, 0)]],
    "X": [[(0, 0), (2, 4)], [(0, 4), (2, 0)]],
    ".": [[(0.8, 0), (1.2, 0), (1.2, 0.5), (0.8, 0.5), (0.8, 0)]],
    " ": [],
}

# ---------------------------------------------------------------- helpers
FIL_AREA = math.pi * (FILAMENT_D / 2) ** 2
out = []
pos = {"x": 0.0, "y": 0.0, "z": 0.0}
time_s = 0.0


def emit(s):
    out.append(s)


def e_for(dist, width, height, flow=1.0):
    return dist * width * height * flow / FIL_AREA


def move(x, y, speed=SPEED_TRAVEL):
    global time_s
    d = math.hypot(x - pos["x"], y - pos["y"])
    if d < 1e-6:
        return
    time_s += d / speed
    emit("G0 X%.3f Y%.3f F%d" % (x, y, speed * 60))
    pos["x"], pos["y"] = x, y


def extrude_to(x, y, speed, width, height, flow=1.0):
    global time_s
    d = math.hypot(x - pos["x"], y - pos["y"])
    if d < 1e-6:
        return
    time_s += d / speed
    emit("G1 X%.3f Y%.3f E%.5f F%d" % (x, y, e_for(d, width, height, flow), speed * 60))
    pos["x"], pos["y"] = x, y


def set_z(z):
    if abs(z - pos["z"]) > 1e-6:
        emit("G1 Z%.3f F600" % z)
        pos["z"] = z


def travel(x, y, z):
    emit("G1 E-%.3f F%d" % (RETRACT, RETRACT_SPEED * 60))
    set_z(max(pos["z"], z) + Z_HOP)
    move(x, y)
    set_z(z)
    emit("G1 E%.3f F%d" % (RETRACT, RETRACT_SPEED * 60))


def square(cx, cy, half, z, width, flow, first_travel):
    pts = [(cx - half, cy - half), (cx + half, cy - half), (cx + half, cy + half), (cx - half, cy + half), (cx - half, cy - half)]
    if first_travel:
        travel(pts[0][0], pts[0][1], z)
    else:
        extrude_to(pts[0][0], pts[0][1], SPEED_FIRST, width, LAYER_H, flow)
    for p in pts[1:]:
        extrude_to(p[0], p[1], SPEED_FIRST, width, LAYER_H, flow)


def line_fill(cx, cy, half, spacing, width, flow):
    n = int(math.floor((2 * half) / spacing)) + 1
    start = -half + ((2 * half) - (n - 1) * spacing) / 2
    for i in range(n):
        off = start + i * spacing
        a, b = (-half, half) if i % 2 == 0 else (half, -half)
        p0, p1 = (cx + a, cy + off), (cx + b, cy + off)
        if i == 0:
            move(*p0, speed=SPEED_TRAVEL)
        else:
            extrude_to(p0[0], p0[1], SPEED_FIRST, width, LAYER_H, flow)
        extrude_to(p1[0], p1[1], SPEED_FIRST, width, LAYER_H, flow)


def text(s, x, y, z, h=TEXT_H, vertical=False, flow=1.1):
    sc = h / 4.0
    adv = 3.0 * sc
    for ci, ch in enumerate(s.upper()):
        for stroke in FONT.get(ch, []):
            pts = []
            for gx, gy in stroke:
                if vertical:
                    pts.append((x - gy * sc, y + ci * adv + gx * sc))
                else:
                    pts.append((x + ci * adv + gx * sc, y + gy * sc))
            travel(pts[0][0], pts[0][1], z)
            for p in pts[1:]:
                extrude_to(p[0], p[1], SPEED_FIRST, TEXT_W, LAYER_H, flow)


def text_width(s, h=TEXT_H):
    return (len(s) * 3.0 - 1.0) * h / 4.0


def zlabel(dz):
    v = int(round(dz * 100))
    return ("+%d" % v) if v > 0 else str(v)


# ---------------------------------------------------------------- geometry
half = PATCH / 2
wall_half = half - LINE_W / 2
fill_half = half - WALLS * LINE_W - LINE_W / 2
cols = [GRID_X0 + i * PITCH for i in range(len(Z_OFFSETS))]
rows = [GRID_Y0 + j * PITCH for j in range(len(FLOWS))]

# ---------------------------------------------------------------- gcode
emit("; First layer calibration grid, generated by make_first_layer_grid.py")
emit("; columns = Z offset mm: %s" % Z_OFFSETS)
emit("; rows (front to back) = first layer flow %%: %s" % FLOWS)
emit("; layer %.2f mm, line width %.2f mm, %d mm/s, %d C nozzle, %d C bed" % (LAYER_H, LINE_W, SPEED_FIRST, TEMP_FIRST, BED_TEMP))
emit(";FLAVOR:Marlin")
emit("M140 S%d" % BED_TEMP)
emit("M104 S%d" % TEMP_FIRST)
emit("M190 S%d" % BED_TEMP)
emit("M109 S%d" % TEMP_FIRST)
emit("START_PRINT")
emit("M83")
emit("G90")
emit("M106 S0")
emit("M204 S%d" % ACCEL)
emit('RESPOND TYPE=echo MSG="First layer grid: columns Z offset %s"' % " ".join(zlabel(d) for d in Z_OFFSETS))
emit('RESPOND TYPE=echo MSG="First layer grid: rows flow %s"' % " ".join(str(f) for f in FLOWS))

# labels at nominal height, two layers so they survive a slightly high nozzle
for layer in range(TEXT_LAYERS):
    z = LAYER_H * (layer + 1)
    emit("; labels layer %d" % (layer + 1))
    for i, dz in enumerate(Z_OFFSETS):
        lab = zlabel(dz)
        text(lab, cols[i] - text_width(lab) / 2, GRID_Y0 - half - 3 - TEXT_H, z)
    lab = "Z OFFSET X 0.01MM"
    text(lab, cols[len(cols) // 2] - text_width(lab) / 2, GRID_Y0 - half - 6 - 2 * TEXT_H, z)
    for j, fl in enumerate(FLOWS):
        lab = str(fl)
        text(lab, GRID_X0 - half - 3 - text_width(lab), rows[j] - TEXT_H / 2, z)
    lab = "FLOW"
    text(lab, GRID_X0 - half - 6 - TEXT_H - 1, rows[len(rows) // 2] - text_width(lab) / 2, z, vertical=True)

# patches: one layer each, at its own Z and flow
emit("; ---- patches ----")
for j, cy in enumerate(rows):
    order = range(len(cols)) if j % 2 == 0 else range(len(cols) - 1, -1, -1)
    for i in order:
        cx = cols[i]
        z = LAYER_H + Z_OFFSETS[i]
        fl = FLOWS[j] / 100.0
        emit("; patch col %d row %d: z %+.2f flow %d%%" % (i + 1, j + 1, Z_OFFSETS[i], FLOWS[j]))
        square(cx, cy, wall_half, z, LINE_W, fl, first_travel=True)
        line_fill(cx, cy, fill_half, LINE_W, LINE_W, fl)

emit("G1 E-%.3f F%d" % (RETRACT, RETRACT_SPEED * 60))
emit("END_PRINT")

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "first_layer_grid.gcode")
with open(path, "w") as f:
    f.write("\n".join(out) + "\n")
print("wrote", path, "(%d lines, about %d min of motion)" % (len(out), time_s / 60))
print()
print("After printing, pick the best patch. Then:")
print("  Flow row  -> Cura: Initial Layer Flow = that row's percent")
print("  Z column  -> printer.cfg [probe] z_offset = current z_offset MINUS the column value")
print("     e.g. best column -3 (= -0.03 mm) with z_offset 1.800 -> set z_offset: 1.830")
print("     then SAVE_CONFIG or RESTART")
