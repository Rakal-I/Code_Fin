"""Génère le logo d'Ancora (assets/logo.svg, logo-dark.svg, icon.svg).

Usage : python scripts/generate_logo.py [chemin/vers/InterDisplay-Light.otf]
Prérequis : pip install fonttools
"""
import math
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

OUT = Path(__file__).resolve().parent.parent / "assets"
FONT = sys.argv[1] if len(sys.argv) > 1 else "/usr/share/fonts/opentype/inter/InterDisplay-Light.otf"
NAME = "ancora"

BLACK, WHITE = "#000000", "#FFFFFF"
# Anneau de répartition : trois segments (50 %, 30 %, 20 %) d'un même ton,
# de plus en plus transparents.
SEGMENTS = [(0.50, 1.0), (0.30, 0.62), (0.20, 0.34)]


def squircle(size, n=5.0, steps=160):
    """Superellipse : coins continus façon icône iOS."""
    r = size / 2
    pts = []
    for i in range(steps):
        t = 2 * math.pi * i / steps
        c, s = math.cos(t), math.sin(t)
        pts.append(f"{r + r * math.copysign(abs(c) ** (2 / n), c):.2f},"
                   f"{r + r * math.copysign(abs(s) ** (2 / n), s):.2f}")
    return "M" + " L".join(pts) + " Z"


def ring(color, r=23, width=9, gap=11):
    circumference = 2 * math.pi * r
    parts, start = [], -90.0
    for share, opacity in SEGMENTS:
        length = circumference * share - gap
        angle = start + (gap / 2) / circumference * 360
        parts.append(
            f'<circle cx="50" cy="50" r="{r}" fill="none" stroke="{color}" stroke-opacity="{opacity}" '
            f'stroke-width="{width}" stroke-linecap="round" stroke-dasharray="{length:.2f} {circumference:.2f}" '
            f'transform="rotate({angle:.2f} 50 50)"/>'
        )
        start += share * 360
    return "".join(parts)


def icon(background, foreground, x=0.0, y=0.0, size=100):
    """Icône dans un carré de 100 × 100, mise à l'échelle et placée en (x, y)."""
    k = size / 100
    hairline = WHITE if background == BLACK else BLACK
    return (
        f'<g transform="translate({x:.2f} {y:.2f}) scale({k:.4f})">'
        f'<path d="{squircle(100)}" fill="{background}"/>'
        f'<path d="{squircle(99)}" transform="translate(0.5 0.5)" fill="none" stroke="{hairline}" '
        f'stroke-opacity="0.16" stroke-width="1"/>'
        f"{ring(foreground)}</g>"
    )


def wordmark(text, size):
    font = TTFont(FONT)
    gs, cmap, upm = font.getGlyphSet(), font.getBestCmap(), font["head"].unitsPerEm
    scale, cursor, commands = size / upm, 0.0, []
    for ch in text:
        glyph = cmap[ord(ch)]
        pen = SVGPathPen(gs)
        gs[glyph].draw(TransformPen(pen, (scale, 0, 0, -scale, cursor, 0)))
        commands.append(pen.getCommands())
        cursor += font["hmtx"][glyph][0] * scale
    x_height = font["OS/2"].sxHeight * scale
    return " ".join(commands), cursor, x_height


def logo(text_color, icon_bg, icon_fg):
    height, icon_size, gap = 96, 80, 22
    path, width, x_height = wordmark(NAME, 50)
    baseline = height / 2 + x_height / 2  # hauteur d'x centrée sur l'icône
    total = icon_size + gap + width + 6
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total:.0f}" height="{height}" '
        f'viewBox="0 0 {total:.1f} {height}" role="img" aria-label="Ancora">'
        f"{icon(icon_bg, icon_fg, 0, (height - icon_size) / 2, icon_size)}"
        f'<path transform="translate({icon_size + gap} {baseline:.2f})" fill="{text_color}" d="{path}"/>'
        "</svg>\n"
    )


# Fond clair : icône noire. Fond sombre : icône inversée pour rester visible.
(OUT / "logo.svg").write_text(logo(BLACK, BLACK, WHITE), encoding="utf-8")
(OUT / "logo-dark.svg").write_text(logo(WHITE, WHITE, BLACK), encoding="utf-8")
(OUT / "icon.svg").write_text(
    '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100" '
    f'role="img" aria-label="Ancora">{icon(BLACK, WHITE)}</svg>\n',
    encoding="utf-8",
)
print("Logo généré dans", OUT)
