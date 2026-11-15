#!/usr/bin/env python3
"""v011 'urban' sign atlas (procedural drawings, no third-party sign artwork; Liberation Sans, SIL OFL, rasterised only).

Simplified approximations of the Austrian signs visible in the user's reference screenshots of the Neuwaldegg
roundabout (data/raw/Marswiese_start.png, data/raw/Marswiese_start_1st_exit.png; Street View = reference only):
pedestrian crossing, bicycle crossing (blue squares), end of short-term parking zone (+ text plate), yield,
keep-right (diagonal arrow, light blue) and pass-right (horizontal arrow, roundabout island), deer-crossing warning
+ supplementary plate, 'Tulln ->' direction board (white, blue frame). Not certified sign artwork.
Output: data/processed/textures_v011/v011_urban.dds (1024x1024, 8x8 cells of 128 px, alpha-tested) + previews/urban.png
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import v004_textures as T4

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/processed/textures_v011'
C, N, SS = 128, 8, 4
FONT = '/usr/share/fonts/liberation-sans-fonts/LiberationSans-Regular.ttf'
FONT_B = '/usr/share/fonts/liberation-sans-fonts/LiberationSans-Bold.ttf'
BLUE = (22, 86, 190, 255); LBLUE = (70, 150, 220, 255); WHITE = (240, 240, 236, 255); BLACK = (25, 25, 28, 255)
RED = (205, 35, 35, 255); GREY = (125, 128, 128, 255); LGREY = (222, 224, 222, 255); CLEAR = (0, 0, 0, 0)
CELLS2 = {  # name -> (col, row, wcells, hcells)
    'ped_crossing': (0, 0, 1, 1), 'bike_crossing': (1, 0, 1, 1), 'kurzpark_end': (2, 0, 1, 1), 'yield': (3, 0, 1, 1),
    'keep_right_diag': (4, 0, 1, 1), 'pass_right': (5, 0, 1, 1), 'deer': (6, 0, 1, 1), 'plate_text': (7, 0, 1, 1),
    'tulln': (0, 1, 2, 1), 'kurzpark_text': (2, 1, 1, 1),
}


def uv2(name, inset=1.0):
    c, r, w, h = CELLS2[name]
    W = N * C
    x0, y0, x1, y1 = c * C + inset, r * C + inset, (c + w) * C - inset, (r + h) * C - inset
    return x0 / W, 1 - y1 / W, x1 / W, 1 - y0 / W


def font(px, bold=False):
    return ImageFont.truetype(FONT_B if bold else FONT, int(px))


def canvas(w=1, h=1, bg=CLEAR):
    im = Image.new('RGBA', (w * C * SS, h * C * SS), bg)
    return im, ImageDraw.Draw(im), C * SS


def done(im, w=1, h=1):
    return np.asarray(im.resize((w * C, h * C), Image.LANCZOS))


def pedestrian(g, cx, cy, s, col=BLACK):
    """Walking figure, size s (height), centred at (cx, cy)."""
    lw = max(2, int(s * 0.09))
    g.ellipse([cx - s * .07, cy - s * .5, cx + s * .07, cy - s * .36], fill=col)
    g.line([cx, cy - s * .34, cx - s * .03, cy + s * .05], fill=col, width=lw)  # torso
    g.line([cx - s * .03, cy + s * .05, cx - s * .2, cy + s * .45], fill=col, width=lw)
    g.line([cx - s * .03, cy + s * .05, cx + s * .18, cy + s * .45], fill=col, width=lw)
    g.line([cx - s * .01, cy - s * .25, cx - s * .2, cy - s * .02], fill=col, width=lw)
    g.line([cx - s * .01, cy - s * .25, cx + s * .2, cy - s * .08], fill=col, width=lw)


def triangle_square(kind):
    im, g, S = canvas(bg=BLUE)
    m = S * .08
    g.rectangle([m * .3, m * .3, S - m * .3, S - m * .3], outline=WHITE, width=int(S * .02))
    g.polygon([(S / 2, m * 1.4), (S - m * 1.3, S - m * 1.3), (m * 1.3, S - m * 1.3)], fill=WHITE)
    base = S - m * 2.0
    if kind == 'ped':
        pedestrian(g, S / 2, S * .6, S * .42)
        for i in range(7):
            x = S * .3 + i * S * .06
            g.rectangle([x, base, x + S * .035, base + S * .02], fill=BLACK)
    else:
        lw = int(S * .025)
        for cx in (S * .36, S * .64):
            g.ellipse([cx - S * .1, S * .62, cx + S * .1, S * .82], outline=BLACK, width=lw)
        g.line([S * .36, S * .72, S * .48, S * .58, S * .64, S * .72], fill=BLACK, width=lw)
        g.line([S * .48, S * .58, S * .56, S * .45], fill=BLACK, width=lw)
        g.ellipse([S * .53, S * .33, S * .6, S * .4], fill=BLACK)
        g.line([S * .56, S * .45, S * .64, S * .55], fill=BLACK, width=lw)
        for y in (S * .56, base):
            for i in range(6):
                x = S * .3 + i * S * .07
                g.rectangle([x, y, x + S * .04, y + S * .018], fill=BLACK)
    return done(im)


def kurzpark_end():
    im, g, S = canvas(bg=WHITE)
    g.rectangle([0, 0, S - 1, S - 1], outline=GREY, width=int(S * .02))
    r = S * .36
    c = (S / 2, S / 2)
    g.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill=GREY)
    g.ellipse([c[0] - r * .7, c[1] - r * .7, c[0] + r * .7, c[1] + r * .7], fill=(160, 162, 162, 255))
    g.line([c[0] - r * .5, c[1] - r * .5, c[0] + r * .5, c[1] + r * .5], fill=GREY, width=int(S * .06))
    g.line([c[0] - r * .5, c[1] + r * .5, c[0] + r * .5, c[1] - r * .5], fill=GREY, width=int(S * .06))
    g.line([S * .1, S * .9, S * .9, S * .1], fill=BLACK, width=int(S * .1))
    return done(im)


def kurzpark_text():
    im, g, S = canvas(bg=WHITE)
    g.rectangle([0, 0, S - 1, S - 1], outline=GREY, width=int(S * .02))
    f = font(S * .15, True)
    for i, t in enumerate(('gebühren-', 'pflichtig', 'Parkdauer', '2 Std.', 'Mo-Fr 9-22')):
        g.text((S / 2, S * (.13 + i * .185)), t, font=f, fill=BLACK, anchor='mm')
    return done(im)


def yield_sign():
    im, g, S = canvas()
    g.polygon([(S * .02, S * .08), (S * .98, S * .08), (S / 2, S * .95)], fill=RED)
    g.polygon([(S * .2, S * .19), (S * .8, S * .19), (S / 2, S * .71)], fill=WHITE)
    return done(im)


def round_arrow(diag, light):
    im, g, S = canvas()
    g.ellipse([S * .02, S * .02, S * .98, S * .98], fill=LBLUE if light else BLUE)
    g.ellipse([S * .06, S * .06, S * .94, S * .94], outline=WHITE, width=int(S * .015))
    a = np.array([[-.3, -.07], [.08, -.07], [.08, -.2], [.32, 0], [.08, .2], [.08, .07], [-.3, .07]])
    if diag:
        th = np.radians(-45)  # pointing down-right (image y down)
        a = a @ np.array([[np.cos(th), np.sin(th)], [-np.sin(th), np.cos(th)]])
        a[:, 1] *= -1
    g.polygon([(S / 2 + x * S, S / 2 + y * S) for x, y in a], fill=WHITE)
    return done(im)


def deer():
    im, g, S = canvas()
    g.polygon([(S / 2, S * .05), (S * .98, S * .92), (S * .02, S * .92)], fill=RED)
    g.polygon([(S / 2, S * .24), (S * .83, S * .83), (S * .17, S * .83)], fill=WHITE)
    lw = int(S * .03)
    g.polygon([(S * .33, S * .62), (S * .55, S * .55), (S * .62, S * .6), (S * .4, S * .68)], fill=BLACK)  # body (leaping)
    g.line([S * .55, S * .56, S * .63, S * .45], fill=BLACK, width=lw)  # neck
    g.polygon([(S * .61, S * .43), (S * .69, S * .44), (S * .63, S * .48)], fill=BLACK)  # head
    g.line([S * .63, S * .43, S * .6, S * .36], fill=BLACK, width=int(lw * .7))
    g.line([S * .65, S * .43, S * .67, S * .36], fill=BLACK, width=int(lw * .7))
    for x0, y0, x1, y1 in ((.36, .65, .26, .74), (.4, .67, .33, .78), (.58, .6, .68, .69), (.55, .62, .62, .74)):
        g.line([S * x0, S * y0, S * x1, S * y1], fill=BLACK, width=int(lw * .8))
    return done(im)


def plate_text():
    im, g, S = canvas()
    g.rectangle([0, S * .25, S - 1, S * .75], fill=WHITE, outline=BLACK, width=int(S * .02))
    f = font(S * .12, True)
    g.text((S / 2, S * .4), 'Gefährliche', font=f, fill=BLACK, anchor='mm')
    g.text((S / 2, S * .6), 'Fahrbahnstelle', font=f, fill=BLACK, anchor='mm')
    return done(im)


def tulln():
    im, g, S = canvas(2, 1, LGREY)
    W, H = 2 * S, S
    g.rectangle([S * .03, H * .06, W - S * .03, H * .94], outline=BLUE, width=int(S * .07))
    g.text((S * .2, H / 2), 'Tulln', font=font(H * .5), fill=BLACK, anchor='lm')
    y = H / 2
    g.line([W * .74, y, W * .9, y], fill=BLACK, width=int(H * .08))
    g.polygon([(W * .93, y), (W * .86, y - H * .14), (W * .86, y + H * .14)], fill=BLACK)
    return done(im, 2, 1)


def put(atlas, name, cell):
    c, r, w, h = CELLS2[name]
    atlas[r * C:(r + h) * C, c * C:(c + w) * C] = cell


def main():
    (OUT / 'previews').mkdir(parents=True, exist_ok=True)
    atlas = np.zeros((N * C, N * C, 4), np.uint8)
    for name, im in (('ped_crossing', triangle_square('ped')), ('bike_crossing', triangle_square('bike')),
                     ('kurzpark_end', kurzpark_end()), ('kurzpark_text', kurzpark_text()), ('yield', yield_sign()),
                     ('keep_right_diag', round_arrow(True, True)), ('pass_right', round_arrow(False, False)),
                     ('deer', deer()), ('plate_text', plate_text()), ('tulln', tulln())):
        put(atlas, name, im)
    Image.fromarray(atlas).save(OUT / 'previews/urban.png')
    rec = T4.write_dds(OUT / 'v011_urban.dds', atlas, alpha_test=True)
    (OUT / 'manifest.json').write_text(json.dumps(dict(cells=CELLS2, cell_px=C, files=dict(urban=rec), note=__doc__), indent=2) + '\n')
    print(rec)


if __name__ == '__main__':
    main()
