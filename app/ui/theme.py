"""Direction artistique Ancora, version « Liquid Glass ».

- Fond ambiant clair, panneaux en verre dépoli (flou, reflet sur le bord supérieur, ombre douce).
- Graphiques fidèles au logo : un seul ton, opacités dégressives (100 %, 62 %, 34 %…),
  extrémités arrondies et ouvertures entre les segments.
- Formats à la française ; une valeur absente s'affiche, elle n'est jamais remplacée par 0.
"""
from __future__ import annotations

import math
from html import escape
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
FAVICON = ROOT / "assets" / "icon-512.png"  # onglet du navigateur (PNG : pris en charge partout)

INK = "#1D1D1F"
MUTED = "#6E6E73"
LINE = "rgba(0,0,0,0.08)"
GAIN = "#1E7F3C"
LOSS = "#C4170C"
# Opacités des segments, dans l'ordre du logo (100 %, 62 %, 34 %), prolongées au-delà de trois.
RING_OPACITY = [1.0, 0.62, 0.34, 0.2, 0.12, 0.07]

_CSS = """
<style>
/* ---------- Fond ambiant : lumière douce, pour que le verre se lise ---------- */
.stApp { background: #ECECEF; }
.stApp::before {
  content: ""; position: fixed; inset: -10%; z-index: 0; pointer-events: none;
  background:
    radial-gradient(36% 30% at 12% 6%, rgba(255,255,255,1), rgba(255,255,255,0) 70%),
    radial-gradient(32% 30% at 86% 10%, rgba(0,0,0,.13), rgba(0,0,0,0) 70%),
    radial-gradient(40% 34% at 70% 96%, rgba(0,0,0,.11), rgba(0,0,0,0) 70%),
    radial-gradient(30% 26% at 40% 55%, rgba(0,0,0,.05), rgba(0,0,0,0) 70%),
    radial-gradient(34% 30% at 4% 82%, rgba(255,255,255,.95), rgba(255,255,255,0) 70%),
    linear-gradient(160deg, #F6F6F8 0%, #E4E4E9 100%);
}
[data-testid="stAppViewContainer"], [data-testid="stMain"] { background: transparent; position: relative; z-index: 1; }
[data-testid="stHeader"] { background: transparent; }

/* ---------- Matière « verre » ---------- */
.anc-glass, [data-testid="stMetric"], [data-testid="stExpander"] details, [data-testid="stForm"],
[data-testid="stDataFrame"], [data-testid="stPlotlyChart"] {
  background: linear-gradient(180deg, rgba(255,255,255,.78), rgba(255,255,255,.52));
  backdrop-filter: blur(26px) saturate(180%); -webkit-backdrop-filter: blur(26px) saturate(180%);
  border: 1px solid rgba(255,255,255,.9);
  box-shadow: 0 14px 36px rgba(0,0,0,.08), 0 1px 2px rgba(0,0,0,.05), inset 0 1px 0 rgba(255,255,255,1),
    inset 0 -1px 0 rgba(0,0,0,.03);
  border-radius: 24px; position: relative;
}
.anc-glass::after { content: ""; position: absolute; inset: 0; border-radius: inherit; pointer-events: none;
  background: linear-gradient(125deg, rgba(255,255,255,.55) 0%, rgba(255,255,255,0) 38%); }
.anc-glass > * { position: relative; z-index: 1; }

/* Fenêtre (fiche instrument) en verre épais, fond flouté. */
div[role="dialog"] { background: linear-gradient(180deg, rgba(250,250,252,.88), rgba(244,244,247,.80)) !important;
  backdrop-filter: blur(40px) saturate(180%); -webkit-backdrop-filter: blur(40px) saturate(180%);
  border: 1px solid rgba(255,255,255,.95) !important; border-radius: 30px !important;
  box-shadow: 0 40px 100px rgba(0,0,0,.22), inset 0 1px 0 #fff !important; }
[data-baseweb="modal"] > div:first-child, [data-testid="stDialog"] > div:first-child {
  backdrop-filter: blur(6px); -webkit-backdrop-filter: blur(6px); }
[data-testid="stDataFrame"] { padding: 6px; overflow: hidden; }
[data-testid="stPlotlyChart"] { padding: 0; overflow: hidden; }
[data-testid="stExpander"] details { overflow: hidden; }
[data-testid="stForm"] { padding: 1.2rem 1.4rem; }

/* ---------- Typographie ---------- */
h1, h2, h3 { letter-spacing: -0.022em; color: #1D1D1F; }
h1 { font-weight: 700; }
h2, h3 { font-weight: 650; }
.block-container { padding-top: 3.2rem; padding-bottom: 4rem; max-width: 1280px; }
.anc-sub { color: #6E6E73; margin: -0.5rem 0 1.4rem 0; font-size: 1.05rem; }
.anc-kicker { text-transform: uppercase; letter-spacing: 0.09em; font-size: 0.72rem; color: #86868B;
  font-weight: 650; margin-bottom: 0.15rem; }
.anc-note { color: #6E6E73; font-size: 0.86rem; }

/* ---------- Indicateurs ---------- */
[data-testid="stMetric"] { padding: 1.05rem 1.25rem; transition: transform .25s ease, box-shadow .25s ease; }
[data-testid="stMetric"]:hover { transform: translateY(-2px);
  box-shadow: 0 18px 40px rgba(0,0,0,.08), 0 1px 2px rgba(0,0,0,.05), inset 0 1px 0 #fff; }
[data-testid="stMetricLabel"] p { color: #6E6E73; font-size: 0.82rem; font-weight: 550; }
[data-testid="stMetricValue"] { font-weight: 700; letter-spacing: -0.025em; }

/* ---------- Bloc principal (grand chiffre) ---------- */
.anc-hero { padding: 1.5rem 1.8rem; margin-bottom: 1.1rem; display: flex; align-items: flex-end;
  justify-content: space-between; gap: 2rem; flex-wrap: wrap; }
.anc-hero .cap { color: #6E6E73; font-size: .95rem; font-weight: 500; }
.anc-hero .big { font-size: 3.4rem; font-weight: 750; letter-spacing: -0.035em; line-height: 1.05;
  margin: .15rem 0 .35rem; }
.anc-hero .delta { font-size: 1.05rem; font-weight: 600; }
.anc-hero .delta span.muted { color: #86868B; font-weight: 500; }
.anc-hero .side { display: flex; gap: 2.2rem; }
.anc-hero .side .k { color: #86868B; font-size: .8rem; font-weight: 550; }
.anc-hero .side .v { font-size: 1.35rem; font-weight: 700; letter-spacing: -0.02em; }

/* ---------- Anneau de répartition (DA du logo) ---------- */
.anc-ringcard { padding: 1.2rem 1.3rem; display: flex; align-items: center; gap: 1.2rem; }
.anc-ringcard .ring { position: relative; flex: 0 0 auto; }
.anc-ringcard .ring svg { display: block; transform: rotate(-90deg); }
.anc-ringcard .ring .seg { transition: opacity .25s ease; }
.anc-ringcard .center { position: absolute; inset: 0; display: flex; flex-direction: column;
  align-items: center; justify-content: center; text-align: center; }
.anc-ringcard .center .k { font-size: .78rem; color: #86868B; font-weight: 550; }
.anc-ringcard .center .v { font-size: 1.25rem; font-weight: 750; letter-spacing: -0.02em; }
.anc-ringcard .legend { flex: 1; min-width: 0; }
.anc-ringcard .legend .row { display: flex; align-items: center; gap: .65rem; padding: .5rem .6rem;
  border-radius: 12px; transition: background .2s ease; cursor: default; }
.anc-ringcard .legend .row:hover { background: rgba(0,0,0,.045); }
.anc-ringcard .legend .dot { width: .72rem; height: .72rem; border-radius: 50%; background: #000; flex: 0 0 auto; }
.anc-ringcard .legend .txt { flex: 1; min-width: 0; line-height: 1.25; }
.anc-ringcard .legend .lab { display: block; font-weight: 550; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; }
.anc-ringcard .legend .val { display: block; color: #86868B; font-size: .82rem; font-variant-numeric: tabular-nums; }
.anc-ringcard .legend .pc { font-weight: 650; font-variant-numeric: tabular-nums; min-width: 3.6rem;
  text-align: right; }

/* ---------- Performances ---------- */
.anc-perf { display: grid; grid-template-columns: repeat(6, 1fr); overflow: hidden; margin: .5rem 0 1.2rem; }
.anc-perf .cell { padding: .85rem 1rem; border-right: 1px solid rgba(0,0,0,.06); }
.anc-perf .cell:last-child { border-right: 0; }
.anc-perf .k { color: #86868B; font-size: .78rem; font-weight: 550; }
.anc-perf .v { font-size: 1.15rem; font-weight: 700; letter-spacing: -.01em; font-variant-numeric: tabular-nums; }

/* ---------- Contrôles en capsules ---------- */
.stButton button, [data-testid="stBaseButton-secondary"], [data-testid="stFormSubmitButton"] button {
  border-radius: 999px !important; border: 1px solid rgba(255,255,255,.9) !important;
  background: linear-gradient(180deg, rgba(255,255,255,.85), rgba(255,255,255,.6)) !important;
  box-shadow: 0 4px 14px rgba(0,0,0,.06), inset 0 1px 0 #fff !important;
  backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
  transition: transform .15s ease, box-shadow .2s ease !important;
}
.stButton button:hover, [data-testid="stBaseButton-secondary"]:hover { transform: translateY(-1px);
  box-shadow: 0 8px 20px rgba(0,0,0,.09), inset 0 1px 0 #fff !important; }
.stButton button:active { transform: scale(.98); }
[data-testid="stBaseButton-primary"], [data-testid="stBaseButtonPrimary"], button[kind="primary"],
button[kind="primaryFormSubmit"] {
  border-radius: 999px !important; background: #000 !important; color: #fff !important; border: 0 !important;
  box-shadow: 0 6px 18px rgba(0,0,0,.18), inset 0 1px 0 rgba(255,255,255,.18) !important;
}

/* Contrôle segmenté et onglets : piste en verre, curseur blanc. */
[data-testid="stButtonGroup"] > div { background: rgba(118,118,128,.12); border-radius: 999px; padding: 3px;
  display: inline-flex; gap: 2px; }
[data-testid="stButtonGroup"] button { border: 0 !important; border-radius: 999px !important;
  background: transparent !important;
  box-shadow: none !important; padding: .3rem .95rem !important; }
[data-testid="stButtonGroup"] button[kind*="Active"], [data-testid="stButtonGroup"] button[aria-checked="true"],
[data-testid="stButtonGroup"] button[aria-pressed="true"] {
  background: #fff !important; box-shadow: 0 3px 10px rgba(0,0,0,.10), 0 1px 1px rgba(0,0,0,.04) !important;
  font-weight: 600; }
[data-baseweb="tab-list"] { background: rgba(118,118,128,.12); border-radius: 999px; padding: 3px; gap: 2px;
  width: fit-content; }
[data-baseweb="tab-list"] button[role="tab"] { border-radius: 999px; padding: .35rem 1.05rem; margin: 0; }
[data-baseweb="tab-list"] button[role="tab"][aria-selected="true"] { background: #fff;
  box-shadow: 0 3px 10px rgba(0,0,0,.10); }
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"] { display: none; }

/* Champs de saisie */
[data-baseweb="select"] > div, [data-baseweb="input"], [data-baseweb="textarea"], [data-testid="stDateInputField"] {
  background: rgba(255,255,255,.7) !important; border-radius: 12px !important;
  border: 1px solid rgba(0,0,0,.06) !important; }

/* ---------- Barre latérale en verre ---------- */
[data-testid="stSidebar"] { background: rgba(250,250,252,.55) !important;
  backdrop-filter: blur(30px) saturate(180%); -webkit-backdrop-filter: blur(30px) saturate(180%);
  border-right: 1px solid rgba(255,255,255,.8); box-shadow: 8px 0 30px rgba(0,0,0,.04); }
[data-testid="stSidebarNavLink"] { border-radius: 12px; transition: background .2s ease; }
[data-testid="stSidebarNavLink"] span { font-weight: 550; }
[data-testid="stSidebarNavLink"][aria-current="page"] { background: rgba(255,255,255,.9);
  box-shadow: 0 4px 14px rgba(0,0,0,.07), inset 0 1px 0 #fff; }

/* Tableaux : lignes sélectionnables */
.anc-hint { color: #86868B; font-size: .82rem; margin: -.35rem 0 .6rem .2rem; }
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


def note(text: str) -> None:
    st.markdown(f'<p class="anc-note">{text}</p>', unsafe_allow_html=True)


def hint(text: str) -> None:
    st.markdown(f'<p class="anc-hint">{text}</p>', unsafe_allow_html=True)


def tone(value) -> str:
    if _missing(value) or value == 0:
        return INK
    return GAIN if value > 0 else LOSS


def hero(caption: str, value: str, delta: str = "", side: list[tuple[str, str, str]] | None = None) -> None:
    """Grand chiffre en verre, avec indicateurs secondaires à droite (libellé, valeur, couleur)."""
    side_html = "".join(f'<div><div class="k">{escape(k)}</div><div class="v" style="color:{c}">{v}</div></div>'
                        for k, v, c in (side or []))
    st.markdown(
        f'<div class="anc-glass anc-hero"><div><div class="cap">{escape(caption)}</div>'
        f'<div class="big">{value}</div><div class="delta">{delta}</div></div>'
        f'<div class="side">{side_html}</div></div>', unsafe_allow_html=True)


def perf_strip(perf: dict[str, float | None]) -> None:
    """Bandeau des performances, une cellule par période."""
    cells = "".join(f'<div class="cell"><div class="k">{escape(label)}</div>'
                    f'<div class="v" style="color:{tone(value)}">{pct(value)}</div></div>'
                    for label, value in perf.items())
    st.markdown(f'<div class="anc-glass anc-perf">{cells}</div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Anneau de répartition, dessiné comme le logo
# --------------------------------------------------------------------------

def ring_opacities(count: int) -> list[float]:
    return [RING_OPACITY[min(i, len(RING_OPACITY) - 1)] for i in range(count)]


def ring_svg(shares: list[float], size: int = 200, stroke: float = 15.0, uid: str = "r") -> str:
    """Segments d'un même noir, opacités du logo, extrémités arrondies et ouvertures."""
    total = sum(shares) or 1.0
    radius = 50 - stroke / 2 - 1
    circumference = 2 * math.pi * radius
    # Ouverture visible entre deux segments : environ 1,5 % du tour, comme dans le logo.
    gap = circumference * 0.015 if len(shares) > 1 else 0
    parts, start = [], 0.0
    for index, (share, opacity) in enumerate(zip(shares, ring_opacities(len(shares)))):
        arc = share / total * circumference
        if len(shares) == 1:
            dash, angle = circumference, 0.0
        else:
            # Les extrémités arrondies débordent d'une demi-épaisseur de chaque côté.
            dash = max(arc - gap - stroke, 0.01)
            angle = (start + (gap + stroke) / 2) / circumference * 360
        parts.append(
            f'<circle class="seg seg-{uid}-{index}" cx="50" cy="50" r="{radius:.2f}" fill="none" stroke="#000" '
            f'stroke-opacity="{opacity}" stroke-width="{stroke}" stroke-linecap="round" '
            f'stroke-dasharray="{dash:.2f} {circumference:.2f}" transform="rotate({angle:.2f} 50 50)"/>')
        start += arc
    return f'<svg width="{size}" height="{size}" viewBox="0 0 100 100" aria-hidden="true">{"".join(parts)}</svg>'


def ring_card(values: dict[str, float], masked: bool, center_caption: str, uid: str) -> None:
    """Anneau + légende. Survoler une ligne met son segment en avant."""
    ordered = dict(sorted(values.items(), key=lambda kv: kv[1], reverse=True))
    total = sum(ordered.values()) or 1.0
    opacities = ring_opacities(len(ordered))
    rows = "".join(
        f'<div class="row leg-{uid}-{i}"><span class="dot" style="opacity:{op}"></span>'
        f'<span class="txt"><span class="lab">{escape(label)}</span>'
        f'<span class="val">{money(value, masked=masked, decimals=0)}</span></span>'
        f'<span class="pc">{number(value / total * 100, 1)} %</span></div>'
        for i, ((label, value), op) in enumerate(zip(ordered.items(), opacities)))
    # Mise en avant au survol, sans JavaScript (sélecteur :has).
    focus = "".join(
        f".anc-ringcard:has(.leg-{uid}-{i}:hover) .seg:not(.seg-{uid}-{i}){{opacity:.18}}"
        for i in range(len(ordered)))
    center_value = money(total, masked=masked, decimals=0)
    st.markdown(
        f'<style>{focus}</style><div class="anc-glass anc-ringcard">'
        f'<div class="ring">{ring_svg(list(ordered.values()), size=160, uid=uid)}'
        f'<div class="center"><span class="k">{escape(center_caption)}</span>'
        f'<span class="v">{center_value}</span></div></div>'
        f'<div class="legend">{rows}</div></div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Tableaux
# --------------------------------------------------------------------------

def gain_color(value) -> str:
    if _missing(value) or value == 0:
        return ""
    return f"color: {GAIN if value > 0 else LOSS}"


def table(frame: pd.DataFrame, formats: dict, gains: Iterable[str] = (),
          overrides: dict[str, list[str]] | None = None, height: int | str = "auto",
          key: str | None = None) -> int | None:
    """Tableau formaté à la française, nombres alignés à droite, gains en vert ou rouge.

    Avec ``key``, les lignes sont sélectionnables : renvoie l'index de la ligne
    nouvellement choisie (une seule fois par choix), sinon ``None``.
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
    if key is None:
        st.dataframe(styler, hide_index=True, width="stretch", height=height, column_config=config)
        return None
    event = st.dataframe(styler, hide_index=True, width="stretch", height=height, column_config=config,
                         key=key, on_select="rerun", selection_mode="single-row")
    rows = list(getattr(getattr(event, "selection", None), "rows", []) or [])
    picked = rows[0] if rows else None
    previous = st.session_state.get(f"_prev_{key}")
    st.session_state[f"_prev_{key}"] = picked
    return picked if picked is not None and picked != previous else None


# --------------------------------------------------------------------------
# Graphiques (Plotly), monochromes
# --------------------------------------------------------------------------

_FONT = dict(family='-apple-system, BlinkMacSystemFont, "SF Pro Text", Inter, "Helvetica Neue", Arial, sans-serif',
             color=INK, size=13)


def _layout(fig: go.Figure, height: int = 320) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=14, r=18, t=16, b=30), paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", font=_FONT, showlegend=False, hovermode="x unified",
        hoverlabel=dict(bgcolor="rgba(255,255,255,.95)", bordercolor="rgba(0,0,0,.08)", font=_FONT),
    )
    return fig


def line(days: list, values: list, height: int = 300, currency: str = "") -> go.Figure:
    """Courbe noire, remplissage dégradé façon verre, point final comme repère du cours actuel."""
    low, high = min(values), max(values)
    pad = (high - low) * 0.08 or high * 0.02 or 1
    fig = go.Figure(go.Scatter(
        x=days, y=values, mode="lines", line=dict(color="#000000", width=2.2, shape="spline", smoothing=0.3),
        fill="tozeroy", fillgradient=dict(type="vertical", colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0.10)"]]),
        hovertemplate=f"%{{y:,.2f}} {symbol(currency)}<extra></extra>"))
    fig.add_trace(go.Scatter(x=[days[-1]], y=[values[-1]], mode="markers", hoverinfo="skip",
                             marker=dict(size=9, color="#000", line=dict(color="#fff", width=2.5))))
    fig = _layout(fig, height)
    fig.update_xaxes(showgrid=False, showline=False, tickfont=dict(color=MUTED), tickformat="%m/%Y",
                     showspikes=True, spikecolor="rgba(0,0,0,.25)", spikethickness=1, spikedash="solid")
    fig.update_yaxes(gridcolor="rgba(0,0,0,.05)", zeroline=False, tickfont=dict(color=MUTED),
                     range=[low - pad, high + pad])
    return fig


def bars(labels: list, values: list, height: int = 280, masked: bool = False,
         emphasis: list[bool] | None = None) -> go.Figure:
    """Barres en capsules : pleines si mises en avant, sinon à 34 % comme le dernier segment du logo."""
    template = "%{x}<extra></extra>" if masked else "%{x}<br>%{y:,.2f} €<extra></extra>"
    emphasis = emphasis or [True] * len(values)
    colors = ["rgba(0,0,0,1)" if strong else "rgba(0,0,0,0.34)" for strong in emphasis]
    fig = go.Figure(go.Bar(x=labels, y=values, marker=dict(color=colors, cornerradius="50%"), width=0.32,
                           hovertemplate=template))
    fig = _layout(fig, height)
    fig.update_layout(hovermode="closest")
    fig.update_xaxes(showgrid=False, showline=False, tickfont=dict(color=MUTED), type="category")
    fig.update_yaxes(gridcolor="rgba(0,0,0,.05)", zeroline=False, tickfont=dict(color=MUTED), showticklabels=not masked)
    return fig


CHART_CONFIG = {"displayModeBar": False}
