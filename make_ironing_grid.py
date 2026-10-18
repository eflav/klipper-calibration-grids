"""
Ironing calibration grid for Klipper (Sovol SV07, 0.4 mm nozzle, PLA).

Prints a 10 x 10 grid of 12 mm discs. Columns vary ironing SPEED, rows vary
ironing FLOW. Axis labels and numbers are printed on the bed next to the grid.
Every disc has the same base (2 walls + solid fill, 4 layers at 0.2 mm) and
is then ironed with its column's speed and its row's flow.

Edit SPEEDS, FLOWS or any constant below, then run:
    python make_ironing_grid.py
It writes ironing_grid.gcode next to this script.
"""
import math
import os

# ---------------------------------------------------------------- settings
SPEEDS = [15, 25, 35, 45]     # mm/s, one per column (left to right)
FLOWS = [4, 6, 8, 10, 12]        # %, one per row (front to back)
IRON_SPACING = 0.20                                     # mm, same for every disc
IRON_INSET = 0.5                                        # nozzle centre stays this far inside the edge
TEMP_IRON = 208

DISC_D = 20.0          # disc diameter
PITCH = 25.0           # centre to centre
GRID_X0 = 72.0         # centre of the first column
GRID_Y0 = 50.0         # centre of the first row
LAYERS = 3
LAYER_H = 0.2
LINE_W = 0.44
WALLS = 2
NOZZLE = 0.4
FILAMENT_D = 1.75

TEMP_FIRST = 220
TEMP_PRINT = 215
BED_TEMP = 60
SPEED_FIRST = 30
SPEED_WALL = 60
SPEED_FILL = 80
SPEED_TRAVEL = 150
ACCEL_PRINT = 5000
ACCEL_IRON = 1000
RETRACT = 0.8
RETRACT_SPEED = 45
Z_HOP = 0.4
TEXT_H = 5.0           # label height, mm
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
    "S": [[(2, 4), (0, 4), (0, 2), (2, 2), (2, 0), (0, 0)]],
    "P": [[(0, 0), (0, 4), (2, 4), (2, 2), (0, 2)]],
    "E": [[(2, 4), (0, 4), (0, 0), (2, 0)], [(0, 2), (1.5, 2)]],
    "D": [[(0, 0), (0, 4), (1.5, 4), (2, 3), (2, 1), (1.5, 0), (0, 0)]],
    "F": [[(2, 4), (0, 4), (0, 0)], [(0, 2), (1.5, 2)]],
    "L": [[(0, 4), (0, 0), (2, 0)]],
    "O": [[(0, 0), (2, 0), (2, 4), (0, 4), (0, 0)]],
    "W": [[(0, 4), (0.5, 0), (1, 2), (1.5, 0), (2, 4)]],
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
    set_z(z + Z_HOP)
    move(x, y)
    set_z(z)
    emit("G1 E%.3f F%d" % (RETRACT, RETRACT_SPEED * 60))


def circle_pts(cx, cy, r, n=48):
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n + 1)]


def ring(cx, cy, r, speed, flow, z, first_travel):
    pts = circle_pts(cx, cy, r)
    if first_travel:
        travel(pts[0][0], pts[0][1], z)
    else:
        extrude_to(pts[0][0], pts[0][1], speed, LINE_W, LAYER_H, flow)
    for p in pts[1:]:
        extrude_to(p[0], p[1], speed, LINE_W, LAYER_H, flow)


def chord_fill(cx, cy, r, along_x, spacing, speed, width, height, flow):
    """Back-and-forth lines clipped to a circle of radius r."""
    n = int(math.floor((2 * r) / spacing)) + 1
    start = -r + ((2 * r) - (n - 1) * spacing) / 2
    k = 0
    for i in range(n):
        off = start + i * spacing
        half = math.sqrt(max(r * r - off * off, 0.0))
        if half < 0.3:
            continue
        a, b = (-half, half) if k % 2 == 0 else (half, -half)
        k += 1
        if along_x:
            p0, p1 = (cx + a, cy + off), (cx + b, cy + off)
        else:
            p0, p1 = (cx + off, cy + a), (cx + off, cy + b)
        if k == 1:
            move(*p0, speed=SPEED_TRAVEL)
        else:
            extrude_to(p0[0], p0[1], speed, width, height, flow)
        extrude_to(p1[0], p1[1], speed, width, height, flow)


def text(s, x, y, z, h=TEXT_H, vertical=False, speed=SPEED_WALL, flow=1.0):
    """Single-stroke text. Origin is the bottom-left of the first character.
    vertical=True rotates 90 degrees anticlockwise, reading bottom to top."""
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
                extrude_to(p[0], p[1], speed, LINE_W, LAYER_H, flow)


# ---------------------------------------------------------------- geometry
R = DISC_D / 2
wall_r = [R - LINE_W / 2 - k * LINE_W for k in range(WALLS)]
fill_r = R - WALLS * LINE_W - LINE_W / 2
iron_r = R - IRON_INSET
cols = [GRID_X0 + i * PITCH for i in range(len(SPEEDS))]
rows = [GRID_Y0 + j * PITCH for j in range(len(FLOWS))]

# ---------------------------------------------------------------- gcode
emit("; Ironing calibration grid, generated by make_ironing_grid.py")
emit("; columns = ironing speed mm/s: %s" % SPEEDS)
emit("; rows (front to back) = ironing flow %%: %s" % FLOWS)
emit("; spacing %.2f mm, inset %.1f mm, iron temp %d" % (IRON_SPACING, IRON_INSET, TEMP_IRON))
emit(";FLAVOR:Marlin")
emit("M140 S%d" % BED_TEMP)
emit("M104 S%d" % TEMP_FIRST)
emit("M190 S%d" % BED_TEMP)
emit("M109 S%d" % TEMP_FIRST)
emit("START_PRINT")
emit("M83")
emit("G90")
emit("M204 S%d" % ACCEL_PRINT)
emit('RESPOND TYPE=echo MSG="Ironing grid: columns speed %s"' % " ".join(str(s) for s in SPEEDS))
emit('RESPOND TYPE=echo MSG="Ironing grid: rows flow %s"' % " ".join(str(f) for f in FLOWS))

for layer in range(LAYERS):
    z = LAYER_H * (layer + 1)
    first = layer == 0
    sp_w = SPEED_FIRST if first else SPEED_WALL
    sp_f = SPEED_FIRST if first else SPEED_FILL
    flow = 1.1 if first else 1.0
    emit("; layer %d z=%.2f" % (layer + 1, z))
    emit("M106 S0" if first else "M106 S255")
    if layer == 1:
        emit("M104 S%d" % TEMP_PRINT)
    if layer < TEXT_LAYERS:
        emit("; labels")
        # column numbers under the grid, centred on each column
        for i, s in enumerate(SPEEDS):
            label = str(s)
            w = (len(label) * 3.0 - 1.0) * TEXT_H / 4.0
            text(label, cols[i] - w / 2, GRID_Y0 - R - 3 - TEXT_H, z, speed=sp_w, flow=flow)
        text("SPEED", (cols[0] + cols[-1]) / 2 - 6, GRID_Y0 - R - 6 - 2 * TEXT_H, z, speed=sp_w, flow=flow)
        # row numbers left of the grid, right-aligned
        for j, fl in enumerate(FLOWS):
            label = str(fl)
            w = (len(label) * 3.0 - 1.0) * TEXT_H / 4.0
            text(label, GRID_X0 - R - 3 - w, rows[j] - TEXT_H / 2, z, speed=sp_w, flow=flow)
        text("FLOW", GRID_X0 - R - 6 - TEXT_H - 1, (rows[0] + rows[-1]) / 2 - 6, z, vertical=True, speed=sp_w, flow=flow)
    # discs, serpentine order to shorten travel
    for j, cy in enumerate(rows):
        order = range(len(cols)) if j % 2 == 0 else range(len(cols) - 1, -1, -1)
        for i in order:
            cx = cols[i]
            emit("; disc col %d row %d" % (i + 1, j + 1))
            ring(cx, cy, wall_r[0], sp_w, flow, z, first_travel=True)
            for r in wall_r[1:]:
                ring(cx, cy, r, sp_w, flow, z, first_travel=False)
            chord_fill(cx, cy, fill_r, along_x=(layer % 2 == LAYERS % 2), spacing=LINE_W,
                       speed=sp_f, width=LINE_W, height=LAYER_H, flow=flow)

# ironing
z_top = LAYER_H * LAYERS
emit("; ---- ironing ----")
emit("G1 E-%.3f F%d" % (RETRACT, RETRACT_SPEED * 60))
set_z(z_top + 5)
move(cols[0] - 25, rows[0] - 25)
emit("M104 S%d" % TEMP_IRON)
emit("M109 S%d" % TEMP_IRON)
emit("G1 E%.3f F%d" % (RETRACT, RETRACT_SPEED * 60))
emit("M204 S%d" % ACCEL_IRON)
for j, cy in enumerate(rows):
    order = range(len(cols)) if j % 2 == 0 else range(len(cols) - 1, -1, -1)
    for i in order:
        cx = cols[i]
        sp, fl = SPEEDS[i], FLOWS[j]
        emit("; iron col %d row %d: speed %d flow %d%%" % (i + 1, j + 1, sp, fl))
        travel(cx - iron_r, cy, z_top)
        chord_fill(cx, cy, iron_r, along_x=False, spacing=IRON_SPACING, speed=sp,
                   width=IRON_SPACING, height=LAYER_H, flow=fl / 100.0)

emit("M204 S%d" % ACCEL_PRINT)
emit("G1 E-%.3f F%d" % (RETRACT, RETRACT_SPEED * 60))
emit("END_PRINT")

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ironing_grid.gcode")
with open(path, "w") as f:
    f.write("\n".join(out) + "\n")
print("wrote", path, "(%d lines, about %d min of motion)" % (len(out), time_s / 60))
