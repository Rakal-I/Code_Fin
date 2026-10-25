"""Génère le logo d'Ancora (assets/logo.svg, logo-dark.svg, icon.svg).

Usage : python scripts/generate_logo.py [chemin/vers/InterDisplay-SemiBold.otf]
Prérequis : pip install fonttools
"""
import math
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

OUT = str(Path(__file__).resolve().parent.parent / "assets") + "/"
FONT = sys.argv[1] if len(sys.argv) > 1 else "/usr/share/fonts/opentype/inter/InterDisplay-SemiBold.otf"
NAME = "Ancora"
GLYPH = "sommet"  # "sommet" (retenu), "orbite" ou "horizon"
GREEN = "#30D158"

def squircle(x, y, size, n=5.0, steps=160):
    """Superellipse : coins continus façon icône iOS."""
    r = size / 2; cx, cy = x + r, y + r
    pts = []
    for i in range(steps):
        t = 2 * math.pi * i / steps
        c, s = math.cos(t), math.sin(t)
        px = cx + r * math.copysign(abs(c) ** (2 / n), c)
        py = cy + r * math.copysign(abs(s) ** (2 / n), s)
        pts.append(f"{px:.2f},{py:.2f}")
    return "M" + " L".join(pts) + " Z"

def stroke(d, k):
    return (f'<path d="{d}" fill="none" stroke="#FFFFFF" stroke-width="{6.5 * k:.2f}" '
            'stroke-linecap="round" stroke-linejoin="round"/>')

def dot(P, k, a, b, r=6.5):
    cx, cy = P(a, b).split(",")
    return f'<circle cx="{cx}" cy="{cy}" r="{r * k:.2f}" fill="{GREEN}"/>'

# Motifs abstraits, dessinés dans un carré de 100 × 100.
GLYPHS = {
    # Un « A » ouvert : sommet qui monte, le point vert tient lieu de barre.
    "sommet": lambda P, k: stroke(f"M{P(29, 72)} L{P(50, 29)} L{P(71, 72)}", k) + dot(P, k, 50, 60),
    # Un anneau et son point d'ancrage.
    "orbite": lambda P, k: (
        f'<circle cx="{P(50, 46).split(",")[0]}" cy="{P(50, 46).split(",")[1]}" r="{21 * k:.2f}" '
        f'fill="none" stroke="#FFFFFF" stroke-width="{6.5 * k:.2f}"/>' + dot(P, k, 50, 67, 7.5)
    ),
    # Un arc posé sur une ligne d'horizon, le point au centre.
    "horizon": lambda P, k: stroke(f"M{P(27, 66)} L{P(73, 66)}", k)
        + stroke(f"M{P(31, 53)} A{19 * k:.2f},{19 * k:.2f} 0 0 1 {P(69, 53)}", k) + dot(P, k, 50, 53),
}

def icon(x, y, size, uid):
    k = size / 100
    P = lambda a, b: f"{x + a * k:.2f},{y + b * k:.2f}"
    return f'''<defs>
    <linearGradient id="{uid}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#3A3A3C"/>
      <stop offset="1" stop-color="#1C1C1E"/>
    </linearGradient>
  </defs>
  <path d="{squircle(x, y, size)}" fill="url(#{uid})"/>
  <path d="{squircle(x + 0.5 * k, y + 0.5 * k, size - k)}" fill="none" stroke="#FFFFFF" stroke-opacity="0.12" stroke-width="{k:.2f}"/>
  {GLYPHS[GLYPH](P, k)}'''

def wordmark(text, x, baseline, size, tracking_em, color):
    font = TTFont(FONT)
    gs = font.getGlyphSet(); cmap = font.getBestCmap(); upm = font["head"].unitsPerEm
    hmtx = font["hmtx"]; s = size / upm
    paths, cursor = [], 0.0
    for ch in text:
        g = cmap[ord(ch)]
        pen = SVGPathPen(gs)
        gs[g].draw(TransformPen(pen, (s, 0, 0, -s, x + cursor, baseline)))
        paths.append(pen.getCommands())
        cursor += hmtx[g][0] * s + tracking_em * size
    cap = font["OS/2"].sCapHeight * s
    return f'<path fill="{color}" d="{" ".join(paths)}"/>', cursor - tracking_em * size, cap

def logo(color, name):
    H, ICON = 96, 80
    size = 50
    _, _, cap = wordmark(NAME, 0, 0, size, -0.02, color)
    baseline = H / 2 + cap / 2            # hauteur de capitale centrée sur l'icône
    word, width, _ = wordmark(NAME, ICON + 22, baseline, size, -0.02, color)
    W = round(ICON + 22 + width + 8)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{NAME}">
  {icon(0, (H - ICON) / 2, ICON, "g")}
  {word}
</svg>
'''
    open(OUT + name, "w").write(svg)

logo("#1D1D1F", "logo.svg")
logo("#F5F5F7", "logo-dark.svg")
open(OUT + "icon.svg", "w").write(f'''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100" role="img" aria-label="{NAME}">
  {icon(0, 0, 100, "g")}
</svg>
''')
print("Logo généré dans", OUT)
