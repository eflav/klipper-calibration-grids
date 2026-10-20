"""
Maximum volumetric flow test for Klipper (Sovol SV07, 0.4 mm nozzle, PLA).

Prints one band per volumetric rate, front to back, each labelled in mm3/s.
A band is PASSES adjacent lines BAND_LEN long, printed as one continuous
serpentine so the hotend has to sustain that rate for several seconds, then
a second layer on top. Every band uses the same line width and height; only
the speed changes, so the amount of plastic the hotend must melt per second
steps up band by band.

Reading it:
  good band      : even width end to end, both layers solid, matte surface
  past the limit : band goes thin, rough, or gappy part way along, the second
                   layer shows holes, or the extruder clicks/grinds
The highest rate whose band is still good is your hotend's limit F.
Use 0.9 x F as the working ceiling and set slicer speeds from it:
  speed (mm/s) = 0.9 F / (layer height x line width)

Edit RATES, TEMP or any constant below, then run:
    python make_max_flow.py
It writes max_flow.gcode next to this script. To test a different range
without editing, pass the rates and an output name:
    python make_max_flow.py 28 30 32 34 36 38 40 42 44 46 -o max_flow_v3.gcode
"""
import math
import os

# ---------------------------------------------------------------- settings
RATES = [8, 10, 12, 14, 16, 18, 20, 22, 24, 26]   # mm3/s, one band each, front to back
# Override from the command line: python make_max_flow.py 28 30 32 34 36 38 40 42 44 46 -o max_flow_v3.gcode
OUT = "max_flow.gcode"
import sys
_args = sys.argv[1:]
if "-o" in _args:
    OUT = _args[_args.index("-o") + 1]; del _args[_args.index("-o"):_args.index("-o") + 2]
if _args:
    RATES = [int(a) for a in _args]
TEMP = 225                    # nozzle, the temperature you will print parts at
BED_TEMP = 60
LAYER_H = 0.28
LINE_W = 0.60
PASSES = 4                    # lines per band (band is PASSES x LINE_W wide)
BAND_LEN = 150.0              # mm, length of each line
LAYERS = 2
PITCH = 8.0                   # band to band spacing in Y
BAND_X0 = 40.0                # left end of every band
GRID_Y0 = 60.0                # y of the first band's first line
ACCEL = 5000
FILAMENT_D = 1.75

SPEED_TRAVEL = 150
RETRACT = 0.8
RETRACT_SPEED = 45
Z_HOP = 0.4
TEXT_H = 4.0
TEXT_W = 0.44
TEXT_SPEED = 30

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
    "/": [[(0, 0), (2, 4)]],
    "M": [[(0, 0), (0, 4), (1, 2), (2, 4), (2, 0)]],
    "S": [[(2, 4), (0, 4), (0, 2), (2, 2), (2, 0), (0, 0)]],
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


def e_for(dist, width, height):
    return dist * width * height / FIL_AREA


def move(x, y, speed=SPEED_TRAVEL):
    global time_s
    d = math.hypot(x - pos["x"], y - pos["y"])
    if d < 1e-6:
        return
    time_s += d / speed
    emit("G0 X%.3f Y%.3f F%d" % (x, y, speed * 60))
    pos["x"], pos["y"] = x, y


def extrude_to(x, y, speed, width=LINE_W, height=LAYER_H):
    global time_s
    d = math.hypot(x - pos["x"], y - pos["y"])
    if d < 1e-6:
        return
    time_s += d / speed
    emit("G1 X%.3f Y%.3f E%.5f F%d" % (x, y, e_for(d, width, height), speed * 60))
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


def text(s, x, y, z, h=TEXT_H):
    sc = h / 4.0
    adv = 3.0 * sc
    for ci, ch in enumerate(s.upper()):
        for stroke in FONT.get(ch, []):
            pts = [(x + ci * adv + gx * sc, y + gy * sc) for gx, gy in stroke]
            travel(pts[0][0], pts[0][1], z)
            for p in pts[1:]:
                extrude_to(p[0], p[1], TEXT_SPEED, TEXT_W, LAYER_H)


def text_width(s, h=TEXT_H):
    return (len(s) * 3.0 - 1.0) * h / 4.0


def speed_for(rate):
    return rate / (LINE_W * LAYER_H)


def band(y0, z, rate):
    """PASSES serpentine lines starting at (BAND_X0, y0), going +Y by LINE_W per pass."""
    sp = speed_for(rate)
    travel(BAND_X0, y0, z)
    for p in range(PASSES):
        y = y0 + p * LINE_W
        if p > 0:
            extrude_to(pos["x"], y, sp)
        x_end = BAND_X0 + BAND_LEN if p % 2 == 0 else BAND_X0
        extrude_to(x_end, y, sp)


# ---------------------------------------------------------------- gcode
emit("; Max volumetric flow test, generated by make_max_flow.py")
emit("; bands front to back, mm3/s: %s" % RATES)
emit("; line %.2f x %.2f mm, %d passes x %.0f mm per band, %d layers, %d C" % (LINE_W, LAYER_H, PASSES, BAND_LEN, LAYERS, TEMP))
emit("; speeds mm/s: %s" % [round(speed_for(r)) for r in RATES])
emit(";FLAVOR:Marlin")
emit("M140 S%d" % BED_TEMP)
emit("M104 S%d" % TEMP)
emit("M190 S%d" % BED_TEMP)
emit("M109 S%d" % TEMP)
emit("START_PRINT")
emit("M83")
emit("G90")
emit("M106 S0")
emit("M204 S%d" % ACCEL)
emit('RESPOND TYPE=echo MSG="Flow test: bands front to back %s mm3/s at %d C"' % (" ".join(str(r) for r in RATES), TEMP))
emit('RESPOND TYPE=echo MSG="Flow test: limit F = highest band that is still even and solid. Slicer ceiling is 0.9 F"')

ys = [GRID_Y0 + i * PITCH for i in range(len(RATES))]
label_x = BAND_X0 - 4 - text_width("26")
band_w = PASSES * LINE_W

for layer in range(LAYERS):
    z = LAYER_H * (layer + 1)
    emit("; layer %d z=%.2f" % (layer + 1, z))
    if layer == 1:
        emit("M106 S255")
    if layer == 0:
        emit("; labels")
        for i, r in enumerate(RATES):
            lab = str(r)
            text(lab, label_x + text_width("26") - text_width(lab), ys[i] + band_w / 2 - TEXT_H / 2, z)
        lab = "FLOW MM3/S"
        text(lab, BAND_X0, ys[-1] + PITCH + 2, z)
    for i, r in enumerate(RATES):
        emit("; band %d: %.1f mm3/s = %.0f mm/s" % (i + 1, r, speed_for(r)))
        band(ys[i], z, r)

emit("G1 E-%.3f F%d" % (RETRACT, RETRACT_SPEED * 60))
emit("END_PRINT")

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), OUT)
with open(path, "w") as f:
    f.write("\n".join(out) + "\n")
print("wrote", path, "(%d lines, about %d min of motion)" % (len(out), time_s / 60))
print()
print("Band speeds (mm/s):", ", ".join("%d->%d" % (r, speed_for(r)) for r in RATES))
print("After printing: F = highest good band. Working ceiling 0.9F. Then")
print("  speed = 0.9F / (layer_height x 0.44)   e.g. F=18, 0.28 layer -> 131 mm/s")
