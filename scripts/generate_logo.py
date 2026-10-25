"""Génère le logo de Vigie (assets/logo.svg, logo-dark.svg, icon.svg).

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
  <path d="M{P(26, 43)} L{P(43, 68)} L{P(71, 32)}" fill="none" stroke="#FFFFFF" stroke-width="{7 * k:.2f}" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="{x + 71 * k:.2f}" cy="{y + 32 * k:.2f}" r="{6 * k:.2f}" fill="{GREEN}"/>'''

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
    _, _, cap = wordmark("Vigie", 0, 0, size, -0.02, color)
    baseline = H / 2 + cap / 2            # hauteur de capitale centrée sur l'icône
    word, width, _ = wordmark("Vigie", ICON + 22, baseline, size, -0.02, color)
    W = round(ICON + 22 + width + 8)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="Vigie">
  {icon(0, (H - ICON) / 2, ICON, "g")}
  {word}
</svg>
'''
    open(OUT + name, "w").write(svg)

logo("#1D1D1F", "logo.svg")
logo("#F5F5F7", "logo-dark.svg")
open(OUT + "icon.svg", "w").write(f'''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100" role="img" aria-label="Vigie">
  {icon(0, 0, 100, "g")}
</svg>
''')
print("Logo généré dans", OUT)
