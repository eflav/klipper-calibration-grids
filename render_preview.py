"""Top-down PNG preview of a G-code file's extruding moves.

    python render_preview.py max_flow.gcode [more.gcode ...]

Writes <name>.png next to each file: 5 px per mm, 220 x 220 mm bed, Y up,
one pixel wide lines. Standard library only.
"""
import os
import struct
import sys
import zlib

SCALE = 5               # px per mm
BED = 220               # mm, square
INK = (192, 80, 16)
PAPER = (255, 255, 255)


def parse(path):
    """Yield (x0, y0, x1, y1) for every move that extrudes."""
    x = y = 0.0
    abs_xy = True
    for line in open(path):
        line = line.split(";")[0].strip()
        if not line:
            continue
        parts = line.split()
        cmd = parts[0]
        if cmd == "G90":
            abs_xy = True
        elif cmd == "G91":
            abs_xy = False
        elif cmd in ("G0", "G1"):
            nx, ny, e = x, y, 0.0
            for p in parts[1:]:
                if p[0] == "X":
                    nx = float(p[1:]) + (0 if abs_xy else x)
                elif p[0] == "Y":
                    ny = float(p[1:]) + (0 if abs_xy else y)
                elif p[0] == "E":
                    e = float(p[1:])
            if e > 0 and (nx != x or ny != y):
                yield x, y, nx, ny
            x, y = nx, ny


def draw(segments, size):
    px = bytearray(PAPER * size * size)

    def plot(ix, iy):
        if 0 <= ix < size and 0 <= iy < size:
            i = (iy * size + ix) * 3
            px[i:i + 3] = bytes(INK)

    for x0, y0, x1, y1 in segments:
        ax, ay = int(round(x0 * SCALE)), size - 1 - int(round(y0 * SCALE))
        bx, by = int(round(x1 * SCALE)), size - 1 - int(round(y1 * SCALE))
        n = max(abs(bx - ax), abs(by - ay), 1)
        for k in range(n + 1):
            plot(ax + (bx - ax) * k // n, ay + (by - ay) * k // n)
    return px


def write_png(path, px, size):
    raw = b"".join(b"\0" + bytes(px[y * size * 3:(y + 1) * size * 3]) for y in range(size))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(raw, 9)))
        f.write(chunk(b"IEND", b""))


if __name__ == "__main__":
    size = BED * SCALE
    for src in sys.argv[1:]:
        out = os.path.splitext(src)[0] + ".png"
        write_png(out, draw(parse(src), size), size)
        print("wrote", out)
