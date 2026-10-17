# Melodarium - make_icons.py (logo and icon files)
# Copyright (C) 2026 Joshua Nichols
# https://github.com/joshdnichols/Melodarium
#
# This program is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later version.
# This program is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.
"""Builds the Melodarium logo and icon files: melodarium-light.svg / -dark.svg (the full
logo), mark-light.svg / mark-dark.svg (no wordmark), icon.png (1024), icon.ico (Windows,
16-256) and icon.icns (Mac). The icon is the mark without the wordmark, white on a
near-black rounded square; small sizes get heavier lines so they stay clear.
The strands are spaced twice as far apart as in the first artwork (option C), so they
stay separate at small sizes; the dots sit at the same places along their strands."""
import asyncio, io, os, re
from PIL import Image
from playwright.async_api import async_playwright

OUT = os.path.dirname(os.path.abspath(__file__))
INK, PAPER, TILE = "#111111", "#FFFFFF", "#111111"
WAVES = ["M 42 115 C 110 131.75 134 11 203 29 S 297 139.5 363 89 S 450 17 520 65",
         "M 42 115 C 110 141.75 134 43 203 61 S 297 169.5 363 121 S 450 49 520 65",
         "M 42 115 C 110 153.75 134 75 203 93 S 297 199.5 363 153 S 450 81 520 65",
         "M 42 115 C 110 165.75 134 107 203 125 S 297 229.5 363 185 S 450 113 520 65"]
DOTS = [(154.82, 39.6), (297.34, 94.44), (520, 65)]
MARK_BOX = (40.65, 25.81, 529.35, 198.93)      # the mark's ink, in the artwork's units
# the MELODARIUM wordmark (Noto Sans Light, letter-spaced), outlined, from the artwork
WORDMARK = ("m 157.89603,250 -9.984,-25.467 h -0.117 q 0.039,1.092 0.078,2.496 0.078,1.365 0.078,2.886 V 250 h -2.145 v -27.846 h 3.432 l 9.594,24.375 h 0.117 l 9.711,-24.375 h 3.354 V 250 h -2.262 v -20.319 q 0,-1.287 0.039,-2.613 0.078,-1.365 0.117,-2.496 h -0.117 L 159.72903,250 Z m 44.20598,0 h -15.288 v -27.846 h 15.288 v 2.028 h -13.026 v 10.179 h 12.285 v 2.028 h -12.285 v 11.583 h 13.026 z m 13.27898,0 v -27.846 h 2.262 v 25.779 h 13.065 V 250 Z m 49.89996,-13.962 q 0,4.251 -1.404,7.488 -1.404,3.237 -4.212,5.07 -2.769,1.794 -6.903,1.794 -4.212,0 -7.02,-1.794 -2.769,-1.833 -4.173,-5.07 -1.365,-3.276 -1.365,-7.527 0,-4.251 1.404,-7.449 1.443,-3.198 4.251,-4.992 2.847,-1.833 7.02,-1.833 4.017,0 6.786,1.755 2.769,1.716 4.173,4.914 1.443,3.198 1.443,7.644 z m -22.698,-0.039 q 0,3.705 1.092,6.513 1.092,2.769 3.354,4.329 2.262,1.521 5.733,1.521 3.51,0 5.733,-1.521 2.262,-1.521 3.315,-4.29 1.092,-2.808 1.092,-6.513 0,-5.811 -2.535,-9.048 -2.496,-3.237 -7.488,-3.237 -3.471,0 -5.772,1.56 -2.301,1.521 -3.432,4.29 -1.092,2.73 -1.092,6.396 z m 57.46599,-0.195 q 0,7.02 -3.744,10.608 -3.705,3.588 -10.764,3.588 h -6.903 v -27.846 h 7.761 q 6.591,0 10.101,3.51 3.549,3.471 3.549,10.14 z m -2.379,0.078 q 0,-11.739 -11.739,-11.739 h -5.031 v 23.868 h 4.446 q 12.324,0 12.324,-12.129 z m 32.35,14.118 -3.705,-9.594 h -11.544 l -3.744,9.594 h -2.34 l 10.959,-27.963 h 2.067 l 10.686,27.963 z m -8.112,-21.684 q -0.234,-0.546 -0.624,-1.716 -0.39,-1.17 -0.663,-2.067 -0.312,1.053 -0.663,2.067 -0.351,1.014 -0.585,1.755 l -3.861,9.984 h 10.101 z m 28.33299,-6.162 q 4.992,0 7.488,1.755 2.535,1.716 2.535,5.889 0,3.198 -1.716,5.031 -1.677,1.794 -4.212,2.535 l 7.644,12.636 h -2.691 l -7.098,-12.012 h -6.63 V 250 h -2.262 v -27.846 z m -0.195,1.989 h -4.485 v 11.895 h 5.265 q 3.393,0 5.226,-1.56 1.872,-1.599 1.872,-4.602 0,-3.198 -1.95,-4.446 -1.95,-1.287 -5.928,-1.287 z M 379.97794,250 h -8.19 v -1.404 l 2.964,-0.429 v -24.141 l -2.964,-0.468 v -1.404 h 8.19 v 1.404 l -2.964,0.468 v 24.141 l 2.964,0.429 z m 33.48104,-9.828 q 0,4.758 -2.769,7.488 -2.73,2.73 -7.761,2.73 -5.031,0 -7.722,-2.73 -2.652,-2.73 -2.652,-7.566 v -17.94 h 2.262 v 17.94 q 0,4.056 2.106,6.162 2.106,2.106 6.123,2.106 3.939,0 6.045,-2.106 2.145,-2.145 2.145,-5.928 v -18.174 h 2.223 z m 26.61701,9.828 -9.984,-25.467 h -0.117 q 0.039,1.092 0.078,2.496 0.078,1.365 0.078,2.886 V 250 h -2.145 v -27.846 h 3.432 l 9.594,24.375 h 0.117 l 9.711,-24.375 h 3.354 V 250 h -2.262 v -20.319 q 0,-1.287 0.039,-2.613 0.078,-1.365 0.117,-2.496 h -0.117 L 441.90899,250 Z")
MARK_SHIFT, WORD_SHIFT, LOGO_H = 23.7, 47.13, 327.13   # full logo layout: same margins as the artwork


def mark(color, stroke=2.7, r=8):
    paths = "".join(f'<path d="{d}"/>' for d in WAVES)
    dots = "".join(f'<circle cx="{x}" cy="{y}" r="{r}"/>' for x, y in DOTS)
    return (f'<g fill="none" stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" '
            f'stroke-linejoin="round">{paths}</g><g fill="{color}">{dots}</g>')


def logo_svg(color):   # the full logo: mark above the wordmark
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{2 * LOGO_H:.0f}" viewBox="0 0 600 {LOGO_H}">'
            f'<title>Melodarium</title><g transform="translate(0 {MARK_SHIFT})">' + mark(color) + "</g>"
            f'<path transform="translate(0 {WORD_SHIFT})" fill="{color}" aria-label="MELODARIUM" d="{WORDMARK}"/></svg>')


def mark_svg(color):   # the mark alone, cropped to it
    x0, y0, x1, y1 = MARK_BOX
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0-6} {y0-6} {x1-x0+12} {y1-y0+12}">'
            + mark(color) + "</svg>")


def icon_svg(variant):
    """1024 x 1024 app icon. variant: large (128 px up), medium (48-64), small (16-32)."""
    stroke, r, cover, inset, radius = {"large": (9.5, 15, 0.84, 64, 200),
                                       "medium": (13, 19, 0.86, 32, 190),
                                       "small": (19, 25, 0.90, 0, 180)}[variant]
    x0, y0, x1, y1 = MARK_BOX
    side = 1024 - 2 * inset
    s = cover * side / (x1 - x0)
    tx, ty = 512 - s * (x0 + x1) / 2, 512 - s * (y0 + y1) / 2
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">'
            f'<rect x="{inset}" y="{inset}" width="{side}" height="{side}" rx="{radius}" fill="{TILE}"/>'
            # a faint edge so the dark tile still shows on a dark desktop or Dock
            f'<rect x="{inset + 6}" y="{inset + 6}" width="{side - 12}" height="{side - 12}" rx="{radius - 6}" '
            'fill="none" stroke="#ffffff" stroke-opacity="0.16" stroke-width="12"/>'
            f'<g transform="translate({tx:.2f} {ty:.2f}) scale({s:.4f})">' + mark(PAPER, stroke, r) + "</g></svg>")


async def render(page, svg, w, h=None):
    h = h or w
    svg = re.sub(r"<svg ", f'<svg width="{w}" height="{h}" ', svg, count=1)
    await page.set_content(f'<html><body style="margin:0;background:transparent"><div id="c" style="width:{w}px;height:{h}px">{svg}</div></body></html>')
    png = await (await page.query_selector("#c")).screenshot(omit_background=True)
    return Image.open(io.BytesIO(png)).convert("RGBA")


async def main():
    files = {"melodarium-light.svg": logo_svg(INK), "melodarium-dark.svg": logo_svg(PAPER),
             "mark-light.svg": mark_svg(INK), "mark-dark.svg": mark_svg(PAPER), "icon.svg": icon_svg("large")}
    for name, svg in files.items():
        with open(os.path.join(OUT, name), "w") as f:
            f.write(svg + "\n")
    async with async_playwright() as p:
        b = await p.chromium.launch(); page = await b.new_page()
        (await render(page, icon_svg("large"), 1024)).save(os.path.join(OUT, "icon.png"))
        full = open(os.path.join(OUT, "melodarium-light.svg")).read()
        (await render(page, full, 1200, round(2 * LOGO_H))).save(os.path.join(OUT, "melodarium-light.png"))
        full = open(os.path.join(OUT, "melodarium-dark.svg")).read()
        (await render(page, full, 1200, round(2 * LOGO_H))).save(os.path.join(OUT, "melodarium-dark.png"))
        win = {}
        for px in (16, 24, 32, 48, 64, 128, 256):
            v = "small" if px <= 32 else "medium" if px <= 64 else "large"
            win[px] = (await render(page, icon_svg(v), px * 4)).resize((px, px), Image.LANCZOS)
            win[px].save(os.path.join(OUT, f"icon-{px}.png"))
        mac = {}
        for px in (16, 32, 64, 128, 256, 512, 1024):
            v = "small" if px <= 32 else "medium" if px <= 64 else "large"
            mac[px] = (await render(page, icon_svg(v), max(px, 256) * (4 if px < 256 else 1))).resize((px, px), Image.LANCZOS)
        await b.close()
    order = sorted(win)
    win[256].save(os.path.join(OUT, "icon.ico"), format="ICO", sizes=[(s, s) for s in order],
                  append_images=[win[s] for s in order if s != 256])
    mac[1024].save(os.path.join(OUT, "icon.icns"), format="ICNS",
                   append_images=[mac[s] for s in (16, 32, 64, 128, 256, 512)])
    print("written:", ", ".join(sorted(os.listdir(OUT))))


asyncio.run(main())
