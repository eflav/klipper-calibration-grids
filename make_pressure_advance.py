"""
Pressure advance pattern test for Klipper (Sovol SV07, 0.4 mm nozzle, PLA).

One chevron (two 25 mm legs meeting at a 90 degree corner) per pressure
advance value, stacked up the bed with its PA value printed beside it.
Each leg starts slow, accelerates to the fast speed into the corner, and slows
again at the end. The speed changes are where pressure advance shows:

  PA too low  : blob at the corner, thin line just after the slow-to-fast change
  PA too high : gap or very thin corner, bulge where the line slows down
  PA right    : even line width end to end, crisp corner

Lines are printed LAYERS tall (default 4) so they stand up and are easy to see.
Pick the lowest value whose corner is crisp with no blob. Put it in printer.cfg:
    [extruder]
    pressure_advance: <value>

Edit PA_VALUES or any constant below, then run:
    python make_pressure_advance.py
It writes pressure_advance.gcode next to this script.
"""
import math
import os

# ---------------------------------------------------------------- settings
PA_VALUES = [round(i * 0.005, 3) for i in range(21)]   # 0.000 .. 0.100 in 0.005 steps
SMOOTH_TIME = 0.040           # pressure_advance_smooth_time during the test
CONFIG_PA = 0.01              # restored at the end (your printer.cfg value)
CONFIG_SMOOTH = 0.060         # restored at the end (your printer.cfg value)

SPEED_SLOW = 20               # mm/s, lead-in and lead-out segments
SPEED_FAST = 120              # mm/s, the body of each leg and the corner
SLOW_LEN = 8.0                # mm of slow line at the start and end of each chevron
LEG = 25.0                    # leg length, mm
ACCEL = 5000                  # matches the LR4 profiles
PITCH = 6.0                   # vertical spacing between chevrons

CORNER_X = 125.0              # x of every corner
GRID_Y0 = 30.0                # y of the first chevron's leg ends (lowest point)
LAYERS = 4
LAYER_H = 0.2
LINE_W = 0.44
FILAMENT_D = 1.75

TEMP_FIRST = 220
TEMP_PRINT = 215
BED_TEMP = 60
SPEED_TRAVEL = 150
SPEED_FIRST_FACTOR = 1.0      # first layer runs at full test speed on purpose (needs a good Z offset)
RETRACT = 0.8
RETRACT_SPEED = 45
Z_HOP = 0.4
TEXT_H = 4.0
TEXT_LAYERS = 2

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
    ".": [[(0.8, 0), (1.2, 0), (1.2, 0.5), (0.8, 0.5), (0.8, 0)]],
    "P": [[(0, 0), (0, 4), (2, 4), (2, 2), (0, 2)]],
    "A": [[(0, 0), (0, 3), (1, 4), (2, 3), (2, 0)], [(0, 2), (2, 2)]],
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


def extrude_to(x, y, speed, width=LINE_W, height=LAYER_H, flow=1.0):
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


def text(s, x, y, z, h=TEXT_H, flow=1.0):
    sc = h / 4.0
    adv = 3.0 * sc
    for ci, ch in enumerate(s.upper()):
        for stroke in FONT.get(ch, []):
            pts = [(x + ci * adv + gx * sc, y + gy * sc) for gx, gy in stroke]
            travel(pts[0][0], pts[0][1], z)
            for p in pts[1:]:
                extrude_to(p[0], p[1], SPEED_SLOW * 2)


def text_width(s, h=TEXT_H):
    return (len(s) * 3.0 - 1.0) * h / 4.0


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def chevron(y_base, z):
    """Two legs at 45 degrees meeting at (CORNER_X, y_base + LEG/sqrt2)."""
    k = LEG / math.sqrt(2)
    corner = (CORNER_X, y_base + k)
    start = (CORNER_X - k, y_base)
    end = (CORNER_X + k, y_base)
    t_slow = SLOW_LEN / LEG
    travel(start[0], start[1], z)
    p = lerp(start, corner, t_slow)
    extrude_to(p[0], p[1], SPEED_SLOW)             # lead-in, slow
    extrude_to(corner[0], corner[1], SPEED_FAST)   # fast into the corner
    p = lerp(corner, end, 1 - t_slow)
    extrude_to(p[0], p[1], SPEED_FAST)             # fast out of the corner
    extrude_to(end[0], end[1], SPEED_SLOW)         # lead-out, slow


# ---------------------------------------------------------------- gcode
emit("; Pressure advance pattern test, generated by make_pressure_advance.py")
emit("; chevrons bottom to top, PA values: %s" % PA_VALUES)
emit("; slow %d mm/s for %.0f mm, fast %d mm/s, accel %d, smooth_time %.3f" % (SPEED_SLOW, SLOW_LEN, SPEED_FAST, ACCEL, SMOOTH_TIME))
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
emit('RESPOND TYPE=echo MSG="PA test: %d chevrons, %.3f to %.3f, labels beside each"' % (len(PA_VALUES), PA_VALUES[0], PA_VALUES[-1]))

k = LEG / math.sqrt(2)
bases = [GRID_Y0 + i * PITCH for i in range(len(PA_VALUES))]
label_x = CORNER_X - k - 4 - text_width("0.000")

for layer in range(LAYERS):
    z = LAYER_H * (layer + 1)
    emit("; layer %d z=%.2f" % (layer + 1, z))
    if layer == 1:
        emit("M106 S255")
        emit("M104 S%d" % TEMP_PRINT)
    if layer < TEXT_LAYERS:
        emit("SET_PRESSURE_ADVANCE ADVANCE=%.3f SMOOTH_TIME=%.3f" % (CONFIG_PA, SMOOTH_TIME))
        emit("; labels")
        text("PA", label_x, bases[-1] + PITCH + 4, z)
        for i, pa in enumerate(PA_VALUES):
            text("%.3f" % pa, label_x, bases[i] - TEXT_H / 2 + 1, z)
    for i, pa in enumerate(PA_VALUES):
        emit("; chevron %d: PA %.3f" % (i + 1, pa))
        emit("SET_PRESSURE_ADVANCE ADVANCE=%.3f SMOOTH_TIME=%.3f" % (pa, SMOOTH_TIME))
        chevron(bases[i], z)

emit("SET_PRESSURE_ADVANCE ADVANCE=%.3f SMOOTH_TIME=%.3f" % (CONFIG_PA, CONFIG_SMOOTH))
emit("G1 E-%.3f F%d" % (RETRACT, RETRACT_SPEED * 60))
emit("END_PRINT")

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pressure_advance.gcode")
with open(path, "w") as f:
    f.write("\n".join(out) + "\n")
print("wrote", path, "(%d lines, about %d min of motion)" % (len(out), time_s / 60))
