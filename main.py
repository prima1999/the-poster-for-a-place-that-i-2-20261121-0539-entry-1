#!/usr/bin/env python3
"""Thalorne - a travel poster for a place that isn't there.

Pure-stdlib procedural poster: a lantern-lit cliffside harbour town
beneath a huge low moon, its tall lantern tower the one landmark
above warm windows and boats on a moonlit sea. Writes a 1024x1024
PNG to /output/entry.png (or $MAKEFUN_OUTPUT_DIR/entry.png).
No network, no external files, deterministic output - repeated
runs are byte-identical.
"""

import math
import os
import struct
import zlib
from binascii import crc32

W = 1024
H = 1024
HORIZON = 580
MOON_X = 700
MOON_Y = 330
MOON_R = 108

INK = (252, 240, 216)
SHADOW = (24, 18, 44)
GOLD = (255, 198, 112)
EMBER = (255, 150, 60)
MOONLIGHT = (255, 232, 178)


def lerp(a, b, t):
    t = clamp(t, 0.0, 1.0)
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


class Canvas:
    def __init__(self):
        self.px = bytearray(W * H * 3)

    def row_fill(self, y, x0, x1, color):
        x0 = clamp(x0, 0, W)
        x1 = clamp(x1, 0, W)
        if x1 <= x0 or y < 0 or y >= H:
            return
        base = (y * W + x0) * 3
        n = x1 - x0
        self.px[base:base + n * 3] = bytes(color) * n

    def rect(self, x, y, w, h, color):
        for yy in range(y, y + h):
            self.row_fill(yy, x, x + w, color)

    def blend_span(self, y, x0, x1, color, alpha):
        x0 = clamp(x0, 0, W)
        x1 = clamp(x1, 0, W)
        if x1 <= x0 or y < 0 or y >= H:
            return
        px = self.px
        r, g, b = color
        for x in range(x0, x1):
            i = (y * W + x) * 3
            px[i] = int(px[i] + (r - px[i]) * alpha)
            px[i + 1] = int(px[i + 1] + (g - px[i + 1]) * alpha)
            px[i + 2] = int(px[i + 2] + (b - px[i + 2]) * alpha)

    def disc(self, cx, cy, r, color, alpha=1.0):
        for yy in range(cy - r, cy + r + 1):
            dy = yy - cy
            half = int(math.sqrt(max(0, r * r - dy * dy)))
            if alpha >= 1.0:
                self.row_fill(yy, cx - half, cx + half + 1, color)
            else:
                self.blend_span(yy, cx - half, cx + half + 1, color, alpha)

    def glow(self, cx, cy, r, color, steps=4):
        for k in range(steps, 0, -1):
            self.disc(cx, cy, int(r * (1.0 + 0.35 * k)), color, 0.05)

    def blend_row(self, y, color, alpha):
        px = self.px
        r, g, b = color
        for x in range(W):
            i = (y * W + x) * 3
            px[i] = int(px[i] + (r - px[i]) * alpha)
            px[i + 1] = int(px[i + 1] + (g - px[i + 1]) * alpha)
            px[i + 2] = int(px[i + 2] + (b - px[i + 2]) * alpha)


FONT = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11100", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11100", "10000", "10000", "10000"),
    "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01110"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("01110", "00100", "00100", "00100", "00100", "00100", "01110"),
    "J": ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "11011", "10001"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
    ".": ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    "!": ("00100", "00100", "00100", "00100", "00100", "00000", "00100"),
    "-": ("00000", "00000", "00000", "01110", "00000", "00000", "00000"),
}


def text_width(text, scale):
    pitch = 6 * scale
    return len(text) * pitch - scale


def draw_text(cv, text, x, y, scale, color, shadow=None):
    if shadow is not None:
        draw_text(cv, text, x + scale, y + scale, scale, shadow)
    cx = x
    for ch in text:
        glyph = FONT.get(ch, FONT[" "])
        for row in range(7):
            bits = glyph[row]
            for col in range(5):
                if bits[col] == "1":
                    cv.rect(cx + col * scale, y + row * scale, scale, scale, color)
        cx += 6 * scale


def sky(cv):
    top = (12, 16, 50)
    mid = (64, 56, 116)
    low = (226, 138, 78)
    for y in range(HORIZON):
        if y < 300:
            c = lerp(top, mid, y / 300.0)
        else:
            c = lerp(mid, low, (y - 300) / 280.0)
        cv.row_fill(y, 0, W, c)


def stars(cv):
    for k in range(280):
        x = (k * 389 + 97) % W
        y = (k * 271 + 53) % 260
        s = 1 if k % 7 else 2
        b = 200 if k % 3 else 255
        if (x - MOON_X) ** 2 + (y - MOON_Y) ** 2 < (MOON_R + 30) ** 2:
            continue
        cv.rect(x, y, s, s, (b, b, 230))


def moon(cv):
    cv.glow(MOON_X, MOON_Y, MOON_R, (255, 214, 140), steps=4)
    cv.disc(MOON_X, MOON_Y, MOON_R, MOONLIGHT, 1.0)
    cv.disc(672, 306, 16, (238, 208, 150), 1.0)
    cv.disc(724, 356, 11, (238, 208, 150), 1.0)
    cv.disc(700, 372, 7, (238, 208, 150), 1.0)
    cv.disc(736, 300, 5, (238, 208, 150), 1.0)


def mountains(cv):
    ridge = (52, 44, 92)
    for x in range(340, W):
        t = x / float(W)
        peak = 470 + int(48 * math.sin(t * 9.0) + 26 * math.sin(t * 23.0 + 1.7))
        cv.rect(x, peak, 1, HORIZON - peak, ridge)


def sea(cv):
    top = (44, 84, 110)
    deep = (10, 26, 52)
    for y in range(HORIZON, H):
        c = lerp(top, deep, (y - HORIZON) / float(H - HORIZON))
        cv.row_fill(y, 0, W, c)
    for k in range(46):
        y = HORIZON + 14 + k * 9
        w = 56 + (k % 5) * 20
        x0 = MOON_X - w // 2 + ((k * 37) % 41) - 20
        cv.blend_span(y, x0, x0 + w, GOLD, 0.38)
    for k in range(30):
        y = HORIZON + 40 + k * 13
        x0 = (k * 173 + 61) % 900
        cv.blend_span(y, x0, x0 + 60 + (k % 3) * 30, (120, 170, 200), 0.12)


def cliff_and_town(cv):
    rock = (30, 26, 58)
    rock_hi = (44, 36, 76)
    for y in range(430, HORIZON + 40):
        span = int(340 - (y - 430) * 0.62)
        cv.row_fill(y, 0, max(0, span), rock)
        cv.row_fill(y, 0, max(0, int(span * 0.55)), rock_hi)
    for y in range(470, 560):
        cv.row_fill(y, 250, 340, (38, 32, 70))
    houses = [(40, 500, 64, 46), (120, 486, 58, 60), (196, 496, 62, 50)]
    for hx, hy, hw, hh in houses:
        cv.rect(hx, hy, hw, hh, (44, 34, 74))
        cv.rect(hx + 4, hy - 8, hw - 8, 8, (58, 40, 84))
        cv.rect(hx + hw - 16, hy - 18, 8, 10, (44, 34, 74))
        for wy in range(2):
            for wx in range(3):
                wx0 = hx + 10 + wx * 18
                wy0 = hy + 10 + wy * 20
                cv.rect(wx0, wy0, 8, 10, GOLD if (wx + wy) % 2 else EMBER)
    tower_x = 288
    cv.rect(tower_x, 330, 34, 220, (52, 40, 88))
    cv.rect(tower_x - 6, 322, 46, 10, (70, 52, 104))
    cv.rect(tower_x + 6, 296, 22, 26, (30, 24, 56))
    cv.disc(tower_x + 17, 309, 30, GOLD, 0.22)
    cv.rect(tower_x + 8, 300, 18, 18, (255, 226, 150))
    cv.rect(tower_x + 12, 288, 10, 8, (255, 226, 150))
    cv.rect(tower_x - 4, 344, 8, 12, GOLD)
    cv.rect(tower_x + 22, 380, 8, 12, GOLD)
    cv.rect(tower_x - 4, 430, 8, 12, EMBER)
    cv.rect(tower_x + 22, 470, 8, 12, GOLD)
    cv.rect(tower_x - 8, 540, 50, 6, (70, 52, 104))


def boats(cv):
    for bx, by, s in [(520, 700, 1.0), (830, 830, 1.3)]:
        w = int(120 * s)
        h = int(26 * s)
        for yy in range(by, by + h):
            frac = (yy - by) / float(h)
            half = int(w * (0.52 - frac * 0.34))
            cv.row_fill(yy, bx - half, bx + half, (26, 22, 50))
        mast = int(64 * s)
        cv.rect(bx - 2, by - mast, 4, mast, (40, 32, 66))
        cv.disc(bx, by - mast - 6, int(14 * s), GOLD, 0.30)
        cv.rect(bx - 5, by - mast - 12, 10, 12, (255, 226, 150))
        for dx in (-46, 46):
            cv.rect(bx + int(dx * s) - 3, by - 8, 6, 8, EMBER)
        cv.rect(bx + 4, by - mast + 6, int(34 * s), int(26 * s), (214, 178, 140))


def mist(cv):
    for y in range(552, 610):
        a = 0.24 * (1.0 - abs(y - 581) / 29.0)
        cv.blend_row(y, (236, 204, 172), max(0.0, a))


def foreground(cv):
    rock = (16, 14, 34)
    ledge = (22, 18, 42)
    for y in range(940, H):
        left = int(220 - (y - 940) * 1.4)
        right = int(260 - (y - 940) * 1.6)
        cv.row_fill(y, 0, left, rock)
        cv.row_fill(y, W - right, W, rock)
    cv.rect(0, 940, 150, 14, ledge)
    cv.rect(60, 954, 120, 14, ledge)
    cv.rect(W - 180, 940, 180, 14, ledge)
    cv.rect(W - 120, 954, 120, 14, ledge)
    cv.rect(42, 928, 6, 8, GOLD)
    cv.rect(150, 942, 6, 8, EMBER)
    cv.rect(W - 48, 928, 6, 8, GOLD)


def frame(cv):
    cv.rect(0, 0, W, 10, INK)
    cv.rect(0, H - 10, W, 10, INK)
    cv.rect(0, 0, 10, H, INK)
    cv.rect(W - 10, 0, 10, H, INK)
    cv.rect(18, 18, W - 36, 3, (250, 238, 214))
    cv.rect(18, H - 21, W - 36, 3, (250, 238, 214))
    cv.rect(26, 26, W - 52, 2, GOLD)
    cv.rect(26, H - 28, W - 52, 2, GOLD)


def title(cv):
    name = "THALORNE"
    scale = 13
    x = (W - text_width(name, scale)) // 2
    draw_text(cv, name, x + 3, 58, scale, SHADOW, shadow=None)
    draw_text(cv, name, x, 54, scale, INK, shadow=None)
    tag = "WHERE THE TIDE KEEPS THE LIGHT"
    ts = 4
    tx = (W - text_width(tag, ts)) // 2
    draw_text(cv, tag, tx + 2, 174, ts, SHADOW, shadow=None)
    draw_text(cv, tag, tx, 170, ts, (255, 214, 150), shadow=None)


def png_bytes(cv):
    raw = bytearray()
    for y in range(H):
        raw.append(0)
        base = y * W * 3
        raw += cv.px[base:base + W * 3]
    comp = zlib.compress(bytes(raw), 9)

    def chunk(tag, data):
        out = struct.pack(">I", len(data)) + tag + data
        return out + struct.pack(">I", crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", comp) + chunk(b"IEND", b"")


def main():
    cv = Canvas()
    sky(cv)
    stars(cv)
    moon(cv)
    mountains(cv)
    sea(cv)
    cliff_and_town(cv)
    boats(cv)
    mist(cv)
    foreground(cv)
    title(cv)
    frame(cv)
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "entry.png")
    data = png_bytes(cv)
    with open(path, "wb") as f:
        f.write(data)
    print("wrote", path, len(data), "bytes")


if __name__ == "__main__":
    main()
