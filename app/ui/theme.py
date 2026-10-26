"""Direction artistique Ancora : noir et blanc, typographie système, beaucoup d'air.

Formats à la française (1 234,56 €). Une valeur absente s'affiche, elle n'est
jamais remplacée par 0.
"""
from __future__ import annotations

from typing import Iterable

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit.errors import StreamlitPageNotFoundError

from app.config.settings import ROOT
from app.ui.formatting import MASK, day, money, number, pct, qty, status, symbol  # noqa: F401
from app.ui.formatting import missing as _missing

LOGO = ROOT / "assets" / "logo.svg"
ICON = ROOT / "assets" / "icon.svg"

INK = "#1D1D1F"
MUTED = "#6E6E73"
LINE = "#E5E5EA"
GAIN = "#1E7F3C"
LOSS = "#C4170C"
# Dégradé de gris de l'anneau du logo, réutilisé pour les répartitions.
RING = ["#000000", "#48484A", "#7C7C80", "#A1A1A6", "#C7C7CC", "#D9D9DE", "#E8E8ED"]

_CSS = """
<style>
h1, h2, h3 { font-family: "Inter Display", "Inter", -apple-system, "SF Pro Display", "Helvetica Neue", sans-serif;
  letter-spacing: -0.02em; color: #1D1D1F; }
h1 { font-weight: 600; }
h2, h3 { font-weight: 600; }
.block-container { padding-top: 2.4rem; padding-bottom: 4rem; max-width: 1280px; }
.anc-sub { color: #6E6E73; margin: -0.6rem 0 1.6rem 0; font-size: 1.02rem; }
.anc-kicker { text-transform: uppercase; letter-spacing: 0.08em; font-size: 0.72rem; color: #6E6E73;
  font-weight: 600; margin-bottom: 0.2rem; }
[data-testid="stMetric"] { background: #FFFFFF; border: 1px solid #E5E5EA; border-radius: 16px;
  padding: 1rem 1.2rem; }
[data-testid="stMetricLabel"] p { color: #6E6E73; font-size: 0.82rem; font-weight: 500; }
[data-testid="stMetricValue"] { font-weight: 600; letter-spacing: -0.02em; }
[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] span { font-weight: 500; }
.anc-note { color: #6E6E73; font-size: 0.85rem; }
.anc-card { border: 1px solid #E5E5EA; border-radius: 16px; padding: 1.1rem 1.3rem; margin-bottom: 0.8rem; }
.anc-card h4 { margin: 0 0 0.2rem 0; font-weight: 600; letter-spacing: -0.01em; }
.anc-legend { color: #6E6E73; font-size: 0.8rem; }
footer { visibility: hidden; }
</style>
"""


def apply() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def header(title: str, subtitle: str | None = None, kicker: str | None = None) -> None:
    if kicker:
        st.markdown(f'<div class="anc-kicker">{kicker}</div>', unsafe_allow_html=True)
    st.title(title)
    if subtitle:
        st.markdown(f'<p class="anc-sub">{subtitle}</p>', unsafe_allow_html=True)


def link(page: str, label: str, icon: str | None = None, container=None) -> None:
    """Lien vers une page ; simple texte si la page est exécutée hors navigation (tests)."""
    target = container or st
    try:
        target.page_link(page, label=label, icon=icon)
    except StreamlitPageNotFoundError:
        target.caption(f"→ {label}")


def perf_strip(perf: dict[str, float | None]) -> None:
    """Bandeau compact des performances, une cellule par période."""
    cells = []
    for label, value in perf.items():
        color = GAIN if value and value > 0 else LOSS if value and value < 0 else INK
        cells.append(
            f'<div style="flex:1;min-width:6.5rem;padding:.7rem .9rem;border-right:1px solid {LINE}">'
            f'<div style="color:{MUTED};font-size:.78rem">{label}</div>'
            f'<div style="color:{color};font-size:1.15rem;font-weight:600;letter-spacing:-.01em">{pct(value)}</div>'
            "</div>"
        )
    st.markdown(f'<div style="display:flex;flex-wrap:wrap;border:1px solid {LINE};border-radius:16px;'
                f'overflow:hidden;margin:.4rem 0 1.2rem">{"".join(cells)}</div>', unsafe_allow_html=True)


def note(text: str) -> None:
    st.markdown(f'<p class="anc-note">{text}</p>', unsafe_allow_html=True)


def gain_color(value) -> str:
    if _missing(value) or value == 0:
        return ""
    return f"color: {GAIN if value > 0 else LOSS}"


def table(frame: pd.DataFrame, formats: dict, gains: Iterable[str] = (),
          overrides: dict[str, list[str]] | None = None, height: int | str = "auto") -> None:
    """Tableau formaté à la française, nombres alignés à droite, gains en vert ou rouge.

    Les valeurs sont converties en texte par leur formateur : une donnée absente
    affiche le libellé choisi par celui-ci (« — », « N/A », « Non disponible »).
    """
    display = frame.copy()
    for column, formatter in formats.items():
        if column in display.columns:
            display[column] = [formatter(v) for v in frame[column]]
    for column, texts in (overrides or {}).items():
        display[column] = texts
    styler = display.style
    gains = [c for c in gains if c in frame.columns]
    if gains:
        styler = styler.apply(lambda col: [gain_color(v) for v in frame[col.name]], subset=gains)
    aligned = set(formats) | set(overrides or {})
    config = {c: st.column_config.Column(alignment="right") for c in aligned if c in display.columns}
    st.dataframe(styler, hide_index=True, width="stretch", height=height, column_config=config)


# --------------------------------------------------------------------------
# Graphiques (Plotly), monochromes
# --------------------------------------------------------------------------

_FONT = dict(family='Inter, -apple-system, "SF Pro Text", "Helvetica Neue", Arial, sans-serif', color=INK, size=13)


def _layout(fig: go.Figure, height: int = 320) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", font=_FONT, showlegend=False,
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor=LINE, font=_FONT),
    )
    return fig


def ring(values: dict[str, float], masked: bool = False, height: int = 300) -> go.Figure:
    """Répartition en anneau, dans l'esprit du logo."""
    labels = list(values)
    data = list(values.values())
    colors = [RING[i % len(RING)] for i in range(len(labels))]
    template = "%{label}<br>%{percent}<extra></extra>" if masked else \
        "%{label}<br>%{value:,.0f} €<br>%{percent}<extra></extra>"
    fig = go.Figure(go.Pie(labels=labels, values=data, hole=0.72, sort=False, direction="clockwise",
                           marker=dict(colors=colors, line=dict(color="#FFFFFF", width=3)),
                           textinfo="none", hovertemplate=template))
    return _layout(fig, height)


def legend(values: dict[str, float]) -> None:
    total = sum(values.values()) or 1
    rows = []
    for i, (label, value) in enumerate(values.items()):
        color = RING[i % len(RING)]
        rows.append(
            f'<div style="display:flex;align-items:center;gap:.55rem;margin:.28rem 0">'
            f'<span style="width:.7rem;height:.7rem;border-radius:50%;background:{color};'
            f'box-shadow:inset 0 0 0 1px rgba(0,0,0,.08)"></span>'
            f'<span style="flex:1">{label}</span>'
            f'<span style="color:{MUTED}">{number(value / total * 100, 1)} %</span></div>'
        )
    st.markdown("".join(rows), unsafe_allow_html=True)


def line(days: list, values: list, height: int = 300, currency: str = "") -> go.Figure:
    fig = go.Figure(go.Scatter(x=days, y=values, mode="lines", line=dict(color="#000000", width=1.8),
                               hovertemplate=f"%{{x|%d/%m/%Y}}<br>%{{y:,.2f}} {symbol(currency)}<extra></extra>"))
    fig = _layout(fig, height)
    fig.update_xaxes(showgrid=False, linecolor=LINE, tickfont=dict(color=MUTED), tickformat="%m/%Y")
    fig.update_yaxes(gridcolor="#F2F2F7", zeroline=False, tickfont=dict(color=MUTED))
    return fig


def bars(labels: list, values: list, height: int = 280, masked: bool = False) -> go.Figure:
    template = "%{x}<extra></extra>" if masked else "%{x}<br>%{y:,.2f} €<extra></extra>"
    fig = go.Figure(go.Bar(x=labels, y=values, marker=dict(color="#000000"), hovertemplate=template))
    fig = _layout(fig, height)
    fig.update_xaxes(showgrid=False, linecolor=LINE, tickfont=dict(color=MUTED), type="category")
    fig.update_yaxes(gridcolor="#F2F2F7", zeroline=False, tickfont=dict(color=MUTED), showticklabels=not masked)
    return fig


CHART_CONFIG = {"displayModeBar": False}
