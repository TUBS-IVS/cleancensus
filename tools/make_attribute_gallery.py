"""Generate the attribute gallery figure for the cleancensus README.

Six-panel matplotlib figure at 100 m resolution on a dark, "glowing"
background — the same visual language as the hero figure
(``tools/make_hero_figure.py``): GitHub-dark canvas, light titles and
colorbars, and colormaps whose low / average cells fade into the
background so that only the signal glows.

Layout
------
By default the panels are arranged in **2 columns x 3 rows** (portrait).
When this single image is scaled to the README content width each panel
is rendered roughly 50 % larger than in the old 3-column layout, which is
the main reason the labels are now legible on the landing page. Pass
``--ncols 3`` for the old wide layout, or ``--individual`` to additionally
write each panel as a standalone, fully legible PNG.

Panels
------
1. Male share (all ages)                    -- diverging (berlin)
2. Senior-only households (share)           -- sequential (magma)
3. Dwellings in multi-family buildings      -- sequential (viridis)
4. Home-ownership (share of households)     -- diverging (vanimo)
5. Vacancy rate (%)                         -- sequential (plasma)
6. Mean household size                      -- diverging (managua)

The three diverging panels use matplotlib's dark-centre diverging
colormaps (berlin / vanimo / managua, available since matplotlib 3.9):
their centre is near-black, so cells at the regional average melt into the
dark canvas and only above-/below-average cells light up. The three
sequential panels reuse the perceptually uniform magma / viridis / plasma
maps whose dark low end blends into the same canvas. Empty cells
(``set_bad``) are painted in the background colour.

Usage
-----
    uv run --no-sync python tools/make_attribute_gallery.py
    uv run --no-sync python tools/make_attribute_gallery.py --window-ars 09162
    uv run --no-sync python tools/make_attribute_gallery.py --individual

Data source (read-only)
------------------------
    data/outputs/cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar_v3.parquet

Default window: 50 x 50 km centred on Braunschweig (ARS-5 prefix 03101).
"""
from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
import numpy as np
import pyarrow.parquet as pq
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PARQUET = Path(
    "data/outputs/"
    "cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar_v3.parquet"
)
# All rendered figures live under one tidy gallery folder.
INDIVIDUAL_DIR = Path("docs/assets/gallery")
OUT = INDIVIDUAL_DIR / "attribute_gallery.png"

# ---------------------------------------------------------------------------
# Dark theme (shared visual language with tools/make_hero_figure.py)
# ---------------------------------------------------------------------------
BG = "#0d1117"          # GitHub-dark canvas
TITLE_COLOR = "#e6edf3"  # near-white panel / figure titles
SUBTLE_COLOR = "#8b949e"  # muted grey for colorbars + attribution
FRAME_COLOR = "#30363d"  # faint border separating panels on the dark canvas

# ---------------------------------------------------------------------------
# Columns needed
# ---------------------------------------------------------------------------
# Panel 1 - Male share
M_TOTAL = "M_TOTAL"
F_TOTAL = "F_TOTAL"

# Panel 2 - Senior-only households share
HH_SENIOR_ONLY = "HH_nurSenioren_Seniorenstatus_eines_privaten_Haushalts_100m-Gitter"
HH_SENIOR_TOT = "Insgesamt_Haushalte_Seniorenstatus_eines_privaten_Haushalts_100m-Gitter_adj"

# Panel 3 - Dwellings in MFH share  (Wohnung universe)
MFH_3_6 = "MFH_3bis6Wohnungen_Wohnung_Gebaeudetyp_Groesse_100m-Gitter"
MFH_7_12 = "MFH_7bis12Wohnungen_Wohnung_Gebaeudetyp_Groesse_100m-Gitter"
MFH_13 = "MFH_13undmehrWohnungen_Wohnung_Gebaeudetyp_Groesse_100m-Gitter"
WHG_TOT = "Insgesamt_Wohnungen_Wohnung_Gebaeudetyp_Groesse_100m-Gitter_adj"

# Panel 4 - Home-ownership
EIGNER_HH = "EigentuemerHH_Tenure_100m-Gitter"
MIETER_HH = "MieterHH_Tenure_100m-Gitter"

# Panel 5 - Vacancy rate
LEER = "Leerstandsquote_Leerstandsquote_100m-Gitter"

# Panel 6 - Mean HH size
EINWOHNER = "Einwohner_Bevoelkerungszahl_100m-Gitter"
HH_TOT_GROESSE = "Insgesamt_Haushalte_Groesse_des_privaten_Haushalts_100m-Gitter_adj"

# ARS / geography
GITTER_ID = "GITTER_ID_100m"
LAND_COL = "Land"
KREIS_COL = "Kreis"
RB_COL = "Regierungsbezirk"

NEEDED_COLS = [
    GITTER_ID, LAND_COL, KREIS_COL, RB_COL,
    M_TOTAL, F_TOTAL,
    HH_SENIOR_ONLY, HH_SENIOR_TOT,
    MFH_3_6, MFH_7_12, MFH_13, WHG_TOT,
    EIGNER_HH, MIETER_HH,
    LEER,
    EINWOHNER, HH_TOT_GROESSE,
]

# Coordinate formula: GITTER_ID = CRS3035RES100mN<N_m>E<E_m>
# Cell centre = N_m + 50, E_m + 50  (metres in EPSG:3035)
_GID_RE = re.compile(r"N(\d+)E(\d+)$")

WINDOW_KM = 50_000  # +/-25 000 m from centre
ATTR_TEXT = (
    "(c) Statistische Aemter des Bundes und der Laender, Zensus 2022 - processed by cleancensus"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_coords(gid_series: pd.Series):
    """Return (x_centre, y_centre) in EPSG:3035 metres from GITTER_ID_100m."""
    extracted = gid_series.str.extract(r"N(\d+)E(\d+)", expand=True)
    y = pd.to_numeric(extracted[0]) + 50   # northing midpoint
    x = pd.to_numeric(extracted[1]) + 50   # easting midpoint
    return x.values, y.values


def safe_ratio(num: np.ndarray, den: np.ndarray) -> np.ndarray:
    """Element-wise ratio; NaN where denominator <= 0."""
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.where(den > 0, num / den, np.nan)
    return r


def robust_vmax(arr: np.ndarray, pct: float) -> float:
    finite = arr[np.isfinite(arr) & (arr > 0)]
    if len(finite) == 0:
        return 1.0
    return float(np.percentile(finite, pct))


# Fixed, reproducible display ranges per attribute (the same scale is used in
# the close-up gallery AND the zoomed-out macro maps, so a colour means the same
# value everywhere). These are display-only ASSUMPTIONS chosen to keep regional
# contrast visible while staying stable across regions; they do not affect any
# computed value. Shares are 0..1, vacancy is a percent, household size is
# persons/HH. Cells outside a range saturate at the end colour.
FIXED_DISPLAY_BOUNDS = {
    "male_share":     (0.45, 0.55),   # share; centred on the ~0.5 balance
    "senior_only":    (0.0, 0.5),     # share
    "mfh":            (0.0, 1.0),     # share
    "home_ownership": (0.0, 1.0),     # share
    "vacancy":        (0.0, 20.0),    # percent
    "mean_hh_size":   (1.8, 2.8),     # persons / HH
}

# Per-attribute percentile pair used only by scale_mode="robust".
_ROBUST_PCT = {
    "male_share": (2, 98), "senior_only": (0, 98), "mfh": (2, 98),
    "home_ownership": (2, 98), "vacancy": (0, 96), "mean_hh_size": (5, 95),
}


def resolve_scale(key: str, grid: np.ndarray, cb_label: str, scale_mode: str):
    """Resolve the display grid, (vmin, vmax) and colorbar label for one
    attribute under the chosen ``scale_mode``.

    - "fixed"   : the reproducible FIXED_DISPLAY_BOUNDS for this attribute.
    - "uniform" : every ratio attribute on an identical 0-100 % scale
                  (shares are converted to percent; mean_hh_size is exempt).
    - "robust"  : data-driven percentile bounds (per-region, not reproducible).
    """
    is_ratio = key != "mean_hh_size"
    if scale_mode == "uniform" and is_ratio:
        if cb_label == "share":
            grid = grid * 100.0
        return grid, 0.0, 100.0, "%"
    if scale_mode == "robust":
        finite = grid[np.isfinite(grid)]
        lo, hi = _ROBUST_PCT[key]
        vmin = float(np.percentile(finite, lo)) if len(finite) else 0.0
        vmax = float(np.percentile(finite, hi)) if len(finite) else 1.0
        return grid, vmin, vmax, cb_label
    # "fixed" (default)
    vmin, vmax = FIXED_DISPLAY_BOUNDS[key]
    return grid, vmin, vmax, cb_label


def glow_cmap(name: str) -> mcolors.Colormap:
    """Return a copy of a named colormap whose 'bad' (NaN / empty) colour is
    the dark canvas, so empty cells melt into the background and only data
    glows. The base colormap is never mutated."""
    cmap = matplotlib.colormaps[name].copy()
    cmap.set_bad(BG)
    return cmap


def place_on_grid(
    x: np.ndarray,
    y: np.ndarray,
    values: np.ndarray,
    x_min: float,
    y_min: float,
    nw: int,
    nh: int,
    cell: float = 100.0,
) -> np.ndarray:
    """Place scalar values on a 2-D raster (nh rows x nw cols).

    Row 0 = southernmost strip (origin="lower" convention).
    Out-of-bounds indices are clipped and silently overwritten.
    """
    grid = np.full((nh, nw), np.nan, dtype=np.float64)
    xi = np.round((x - x_min) / cell).astype(np.intp)
    yi = np.round((y - y_min) / cell).astype(np.intp)
    mask = (xi >= 0) & (xi < nw) & (yi >= 0) & (yi < nh)
    xi, yi, vals = xi[mask], yi[mask], values[mask]
    grid[yi, xi] = vals
    return grid


def style_colorbar(cb, fontsize: float, label: str) -> None:
    """Apply the dark theme to a colorbar (muted grey ticks / outline,
    light label)."""
    cb.set_label(label, fontsize=fontsize, labelpad=6, color=TITLE_COLOR)
    cb.ax.tick_params(labelsize=fontsize - 1.5, color=SUBTLE_COLOR, labelcolor=SUBTLE_COLOR)
    cb.outline.set_edgecolor(SUBTLE_COLOR)
    cb.outline.set_linewidth(0.5)


def set_titles(ax, title: str, subtitle: str | None, title_fs: float) -> None:
    """Set a plain-language panel title with an optional smaller grey subtitle.

    The subtitle states the precise meaning in everyday words so the panel is
    understandable without domain knowledge. It is drawn just above the axes and
    the title pad is enlarged so the title clears it.
    """
    sub_fs = title_fs * 0.72
    pad = 10 + (sub_fs * 1.7 if subtitle else 0)
    ax.set_title(title, fontsize=title_fs, pad=pad, color=TITLE_COLOR, fontweight="normal")
    if subtitle:
        ax.text(0.5, 1.015, subtitle, transform=ax.transAxes, ha="center", va="bottom",
                fontsize=sub_fs, color=SUBTLE_COLOR, style="italic")


# ---------------------------------------------------------------------------
# Braunschweig highlight (frame / outline marking the focus Kreis)
# ---------------------------------------------------------------------------
# A small accent palette that reads on both the cool (viridis / berlin) and
# the warm (magma / plasma) panels.
HL_CYAN = "#39d0ff"
HL_AMBER = "#ffb454"
HL_WHITE = "#f0f6fc"

# Each style is a recipe consumed by draw_highlight():
#   kind     : "box"     -> bounding rectangle
#              "hull"    -> convex hull of the Kreis cells (clean shape-fitting polygon)
#              "outline" -> closed outline of the morphologically filled footprint
#   color    : line colour
#   glow     : draw a soft wide low-alpha stroke beneath the crisp line
#   label    : annotate "Braunschweig" next to the marker
HIGHLIGHT_STYLES = {
    "box_cyan":       {"kind": "box",     "color": HL_CYAN,  "glow": True,  "label": False},
    "box_amber":      {"kind": "box",     "color": HL_AMBER, "glow": True,  "label": False},
    "box_white":      {"kind": "box",     "color": HL_WHITE, "glow": False, "label": False},
    "box_cyan_label": {"kind": "box",     "color": HL_CYAN,  "glow": True,  "label": True},
    "hull_cyan":      {"kind": "hull",    "color": HL_CYAN,  "glow": True,  "label": False},
    "hull_amber":     {"kind": "hull",    "color": HL_AMBER, "glow": True,  "label": False},
    "outline_cyan":   {"kind": "outline", "color": HL_CYAN,  "glow": True,  "label": False},
    "outline_amber":  {"kind": "outline", "color": HL_AMBER, "glow": True,  "label": False},
}


def compute_focus_geometry(win_df: pd.DataFrame, x_w: np.ndarray, y_w: np.ndarray,
                           ars5: str, cx: float, cy: float, nw: int = 500, nh: int = 500):
    """Return the focus Kreis geometry in panel pixel coordinates.

    Produces both a bounding box ``(x0, y0, width, height)`` and a boolean
    cell-footprint mask (nh x nw) for the cells whose ARS-5 equals ``ars5``,
    so the highlight can be drawn either as a rectangle or as the true outline.
    """
    x_min = cx - 25_000
    y_min = cy - 25_000
    land, rb, kreis = ars5[:2], ars5[2], ars5[3:]
    rows = (
        (win_df[LAND_COL] == land)
        & (win_df[RB_COL] == rb)
        & (win_df[KREIS_COL] == kreis)
    ).values
    if not rows.any():
        print(f"  WARNING: no focus cells for ARS {ars5} inside the window - highlight skipped")
        return None

    xi = np.round((x_w[rows] - x_min) / 100.0).astype(np.intp)
    yi = np.round((y_w[rows] - y_min) / 100.0).astype(np.intp)
    inb = (xi >= 0) & (xi < nw) & (yi >= 0) & (yi < nh)
    xi, yi = xi[inb], yi[inb]
    if len(xi) == 0:
        print(f"  WARNING: focus cells for ARS {ars5} fall outside the window - highlight skipped")
        return None

    mask = np.zeros((nh, nw), dtype=bool)
    mask[yi, xi] = True
    # imshow(origin="lower") places cell centres at integer indices, so the
    # cell edges run from -0.5 to n-0.5.
    box = (xi.min() - 0.5, yi.min() - 0.5,
           (xi.max() - xi.min()) + 1.0, (yi.max() - yi.min()) + 1.0)

    # Clean Kreis-shaped outline: close small gaps between populated cells,
    # fill interior holes, then keep only the largest connected component so a
    # single contour traces the Kreis rather than one ring per populated cluster.
    from scipy import ndimage
    filled = ndimage.binary_closing(mask, iterations=3)
    filled = ndimage.binary_fill_holes(filled)
    labels, n_comp = ndimage.label(filled)
    if n_comp > 1:
        sizes = ndimage.sum(np.ones_like(labels), labels, index=range(1, n_comp + 1))
        filled = labels == (int(np.argmax(sizes)) + 1)

    # Convex hull (shape-fitting polygon) of the populated cell centres.
    from scipy.spatial import ConvexHull
    pts = np.column_stack([xi, yi]).astype(float)
    hull_xy = None
    if len(pts) >= 3:
        try:
            hull = ConvexHull(pts)
            verts = pts[hull.vertices]
            hull_xy = np.vstack([verts, verts[:1]])  # close the ring
        except Exception as exc:  # degenerate / collinear cells
            print(f"  WARNING: convex hull failed ({exc}); hull styles unavailable")

    print(f"  Focus ARS {ars5}: {len(xi):,} cells, "
          f"box x[{xi.min()}-{xi.max()}] y[{yi.min()}-{yi.max()}], "
          f"filled components={n_comp}")
    return {"box": box, "mask": mask, "filled": filled, "hull": hull_xy}


def draw_highlight(ax, spec: dict, focus: dict, lw: float = 2.0) -> None:
    """Draw the Braunschweig marker on ``ax`` according to ``spec``."""
    if focus is None:
        return
    color = spec["color"]
    glow_fx = [pe.Stroke(linewidth=lw + 3.0, foreground=color, alpha=0.25),
               pe.Normal()] if spec.get("glow") else None

    x0, y0, w, h = focus["box"]
    label_xy = (x0 + w / 2.0, y0 + h)
    kind = spec["kind"]

    if kind == "box":
        rect = mpatches.Rectangle(
            (x0, y0), w, h, fill=False, edgecolor=color, linewidth=lw,
            joinstyle="round", zorder=5,
        )
        if glow_fx is not None:
            rect.set_path_effects(glow_fx)
        ax.add_patch(rect)
    elif kind == "hull":
        verts = focus.get("hull")
        if verts is None:
            return
        line, = ax.plot(verts[:, 0], verts[:, 1], color=color, linewidth=lw,
                        solid_joinstyle="round", zorder=5)
        if glow_fx is not None:
            line.set_path_effects(glow_fx)
    else:  # "outline" - closed boundary of the filled Kreis footprint
        cs = ax.contour(
            focus["filled"].astype(float), levels=[0.5], colors=[color],
            linewidths=lw, origin="lower", zorder=5,
        )
        if glow_fx is not None:
            try:
                cs.set_path_effects(glow_fx)
            except Exception:
                pass

    if spec.get("label"):
        ax.annotate(
            "Braunschweig", xy=label_xy, xytext=(0, 6),
            textcoords="offset points", ha="center", va="bottom",
            color=color, fontsize=11, fontweight="bold", zorder=6,
            path_effects=[pe.withStroke(linewidth=2.5, foreground=BG)],
        )


def draw_scalebar(ax, nw: int, nh: int, *, cell_m: float = 100.0,
                  length_km: float = 10.0, fontsize: float = 11.0,
                  color: str = TITLE_COLOR) -> None:
    """Draw a scale bar in the lower-left corner.

    The raster is in pixel coordinates where one cell = ``cell_m`` metres, so a
    bar of ``length_km`` spans ``length_km * 1000 / cell_m`` pixels. A dark
    stroke keeps the bar and its label legible over bright cells.
    """
    length_px = length_km * 1000.0 / cell_m
    x0 = nw * 0.05
    y0 = nh * 0.06
    cap = nh * 0.012  # end-cap half height
    stroke = [pe.withStroke(linewidth=3.0, foreground=BG)]

    ax.plot([x0, x0 + length_px], [y0, y0], color=color, linewidth=2.0,
            solid_capstyle="butt", zorder=7, path_effects=stroke)
    for xc in (x0, x0 + length_px):
        ax.plot([xc, xc], [y0 - cap, y0 + cap], color=color, linewidth=2.0,
                zorder=7, path_effects=stroke)
    ax.text(x0 + length_px / 2.0, y0 + cap + nh * 0.012, f"{length_km:g} km",
            ha="center", va="bottom", color=color, fontsize=fontsize,
            fontweight="bold", zorder=7, path_effects=stroke)


# ---------------------------------------------------------------------------
# Panel rendering
# ---------------------------------------------------------------------------

def draw_panel(fig, ax, panel: dict, *, title_fs: float, cb_fs: float,
               cb_shrink: float = 0.88, highlight: dict | None = None,
               focus: dict | None = None, scalebar: bool = True,
               scalebar_fs: float = 11.0) -> None:
    """Render one attribute panel (image + title + dark colorbar) on ``ax``.

    If ``highlight`` (a HIGHLIGHT_STYLES recipe) and ``focus`` geometry are
    given, the focus Kreis is marked on top of the raster.
    """
    ax.set_facecolor(BG)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_edgecolor(FRAME_COLOR)
        spine.set_linewidth(0.8)

    im = ax.imshow(
        panel["grid"],
        origin="lower",
        cmap=panel["cmap"],
        norm=panel["norm"],
        interpolation="nearest",
        aspect="equal",
    )
    if highlight is not None:
        draw_highlight(ax, highlight, focus)
    if scalebar:
        nh, nw = panel["grid"].shape
        draw_scalebar(ax, nw, nh, fontsize=scalebar_fs)
    set_titles(ax, panel["title"], panel.get("subtitle"), title_fs)
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02, shrink=cb_shrink)
    style_colorbar(cb, cb_fs, panel["cb_label"])


# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------

def build_window(df: pd.DataFrame, ars5: str, half: float = 25_000.0):
    """Return a sub-DataFrame clipped to a half*2 km window around the ARS centroid."""
    land = ars5[:2]
    rb = ars5[2]
    kreis = ars5[3:]

    mask = (df[LAND_COL] == land) & (df[RB_COL] == rb) & (df[KREIS_COL] == kreis)
    sub = df[mask]
    if len(sub) == 0:
        raise ValueError(
            f"No cells found for ARS-5 prefix {ars5!r} "
            f"(Land={land!r}, RB={rb!r}, Kreis={kreis!r}). "
            "Check that the parquet file covers this region."
        )

    x, y = parse_coords(sub[GITTER_ID])
    cx = x.mean()
    cy = y.mean()
    print(f"  Window centre: E={cx:.0f} m, N={cy:.0f} m  (EPSG:3035)")

    x_all, y_all = parse_coords(df[GITTER_ID])
    win = (
        (x_all >= cx - half) & (x_all <= cx + half) &
        (y_all >= cy - half) & (y_all <= cy + half)
    )
    return df[win].copy(), cx, cy, x_all[win], y_all[win]


# ---------------------------------------------------------------------------
# Panel computation
# ---------------------------------------------------------------------------

def compute_panels(win_df: pd.DataFrame, x_w: np.ndarray, y_w: np.ndarray,
                   cx: float, cy: float, scale_mode: str = "fixed") -> list[dict]:
    """Compute the six attribute rasters and their display specs.

    The scientific computation is unchanged from the original gallery; only
    the display colormaps / norms target the dark 'glow' theme.

    ``scale_mode`` selects the colour scale (see resolve_scale): "fixed"
    (default, reproducible FIXED_DISPLAY_BOUNDS shared with the macro maps),
    "uniform" (all ratio panels on 0-100 %), or "robust" (per-region percentiles).
    """
    x_min = cx - 25_000
    y_min = cy - 25_000
    NW, NH = 500, 500  # 100 m cells in a 50 x 50 km box

    def grid(values):
        return place_on_grid(x_w, y_w, np.asarray(values, dtype=np.float64),
                             x_min, y_min, NW, NH, cell=100.0)

    # ---- Panel 1: Male share ----
    m = win_df[M_TOTAL].fillna(0).values
    f = win_df[F_TOTAL].fillna(0).values
    g1 = grid(safe_ratio(m, m + f))

    # ---- Panel 2: Senior-only HH share ----
    g2 = grid(safe_ratio(
        win_df[HH_SENIOR_ONLY].fillna(0).values,
        win_df[HH_SENIOR_TOT].fillna(0).values,
    ))

    # ---- Panel 3: MFH dwelling share ----
    mfh = (
        win_df[MFH_3_6].fillna(0).values +
        win_df[MFH_7_12].fillna(0).values +
        win_df[MFH_13].fillna(0).values
    )
    g3 = grid(safe_ratio(mfh, win_df[WHG_TOT].fillna(0).values))

    # ---- Panel 4: Owner-occupancy share ----
    eig = win_df[EIGNER_HH].fillna(0).values
    mie = win_df[MIETER_HH].fillna(0).values
    g4 = grid(safe_ratio(eig, eig + mie))

    # ---- Panel 5: Vacancy rate (%) ----
    leer_raw = win_df[LEER].fillna(0).values
    g5 = grid(np.where(leer_raw > 0, leer_raw, np.nan))

    # ---- Panel 6: Mean HH size ----
    pop = win_df[EINWOHNER].fillna(0).values
    hh = win_df[HH_TOT_GROESSE].fillna(0).values
    g6 = grid(safe_ratio(pop, hh))

    panels = [
        {
            "grid": g1, "key": "male_share",
            "title": "Share of men",
            "subtitle": "men as a fraction of all residents",
            # Diverging, dark centre: balanced cells melt into the canvas,
            # blue = more women, red = more men.
            "cmap": glow_cmap("berlin"),
            "cb_label": "share",
            "slug": "01_male_share",
        },
        {
            "grid": g2, "key": "senior_only",
            "title": "Senior-only households",
            "subtitle": "households where everyone is 65 or older",
            "cmap": glow_cmap("magma"),
            "cb_label": "share",
            "slug": "02_senior_only_households",
        },
        {
            "grid": g3, "key": "mfh",
            "title": "Homes in apartment buildings",
            "subtitle": "dwellings in buildings with 3 or more units",
            "cmap": glow_cmap("viridis"),
            "cb_label": "share",
            "slug": "03_multifamily_dwellings",
        },
        {
            "grid": g4, "key": "home_ownership",
            "title": "Home ownership",
            "subtitle": "households that own (not rent) their home",
            # Diverging, dark centre: green = more owners, pink = more renters.
            "cmap": glow_cmap("vanimo"),
            "cb_label": "share",
            "slug": "04_home_ownership",
        },
        {
            "grid": g5, "key": "vacancy",
            "title": "Vacant homes",
            "subtitle": "share of dwellings standing empty",
            "cmap": glow_cmap("plasma"),
            "cb_label": "%",
            "slug": "05_vacancy_rate",
        },
        {
            "grid": g6, "key": "mean_hh_size",
            "title": "Average household size",
            "subtitle": "people per private household",
            # Diverging, dark centre around a typical ~2.2 persons / HH.
            "cmap": glow_cmap("managua"),
            "cb_label": "persons / HH",
            "slug": "06_mean_household_size",
        },
    ]

    # ---- Resolve the colour scale (fixed / uniform / robust) ----
    for p in panels:
        p["grid"], vmin, vmax, p["cb_label"] = resolve_scale(
            p["key"], p["grid"], p["cb_label"], scale_mode)
        p["norm"] = mcolors.Normalize(vmin=vmin, vmax=vmax)

    # ---- Diagnostics ----
    print("\nPer-panel statistics (window cells):")
    for p in panels:
        v = p["grid"][np.isfinite(p["grid"])]
        if len(v):
            print(f"  {p['title']:46s} n={len(v):6d}  "
                  f"min={v.min():.3f}  median={np.median(v):.3f}  max={v.max():.3f}")
        else:
            print(f"  {p['title']:46s} - no finite values")

    return panels


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_combined(panels: list[dict], ars5: str, ncols: int, dpi: int,
                    region_name: str, out: Path = OUT,
                    highlight: dict | None = None,
                    focus: dict | None = None) -> Path:
    """Render all panels into one dark figure and save to ``out``."""
    nrows = int(np.ceil(len(panels) / ncols))
    # Roughly square panels; portrait when ncols < nrows.
    panel_w, panel_h = 7.6, 7.2
    figsize = (panel_w * ncols, panel_h * nrows)

    print(f"\nRendering combined figure ({ncols} x {nrows}) -> {out.name} ...")
    fig, axes = plt.subplots(
        nrows, ncols, figsize=figsize,
        facecolor=BG,
        gridspec_kw={"wspace": 0.16, "hspace": 0.14},
    )
    fig.patch.set_facecolor(BG)
    flat_axes = np.atleast_1d(axes).ravel()

    for ax, panel in zip(flat_axes, panels):
        draw_panel(fig, ax, panel, title_fs=17, cb_fs=14, cb_shrink=0.9,
                   highlight=highlight, focus=focus)
    for ax in flat_axes[len(panels):]:
        ax.axis("off")

    fig.suptitle(
        f"Computed attributes at 100 m - {region_name} (50 x 50 km)",
        fontsize=26, y=0.995, color=TITLE_COLOR, fontweight="bold",
    )
    fig.text(
        0.5, 0.004, ATTR_TEXT,
        ha="center", va="bottom", fontsize=12, color=SUBTLE_COLOR,
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=dpi, facecolor=BG, bbox_inches="tight")
    plt.close(fig)

    size_mb = out.stat().st_size / 1_000_000
    print(f"Saved {out}  ({size_mb:.2f} MB)")
    if size_mb > 3.5:
        print(f"WARNING: file size {size_mb:.2f} MB > 3.5 MB - re-rendering at lower dpi ...")
        plt.close("all")
        return render_combined(panels, ars5, ncols, max(80, dpi - 30), region_name,
                               out=out, highlight=highlight, focus=focus)
    return out


def render_individual(panels: list[dict], dpi: int,
                      highlight: dict | None = None,
                      focus: dict | None = None) -> list[Path]:
    """Render each panel as its own standalone, fully legible dark PNG."""
    INDIVIDUAL_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    print(f"\nRendering {len(panels)} standalone panels into {INDIVIDUAL_DIR}/ ...")
    for panel in panels:
        fig, ax = plt.subplots(figsize=(9.5, 9.0), facecolor=BG)
        fig.patch.set_facecolor(BG)
        draw_panel(fig, ax, panel, title_fs=20, cb_fs=15, cb_shrink=0.82,
                   highlight=highlight, focus=focus, scalebar_fs=14)
        fig.text(
            0.5, 0.02, ATTR_TEXT,
            ha="center", va="bottom", fontsize=10, color=SUBTLE_COLOR,
        )
        out = INDIVIDUAL_DIR / f"{panel['slug']}.png"
        fig.savefig(out, dpi=dpi, facecolor=BG, bbox_inches="tight")
        plt.close(fig)
        print(f"  Saved {out}  ({out.stat().st_size / 1_000_000:.2f} MB)")
        written.append(out)
    return written


def render_variants_sheet(panels: list[dict], focus: dict | None, dpi: int,
                          backdrop_slug: str = "03_multifamily_dwellings") -> Path | None:
    """Render one representative panel with every highlight style side by side.

    This contact sheet lets the user compare Braunschweig markers (box vs
    outline, cyan / amber / white, with / without label) and pick one. The
    chosen style is then applied everywhere via --highlight <style>.
    """
    if focus is None:
        print("No focus geometry - skipping variants sheet.")
        return None

    backdrop = next((p for p in panels if p["slug"] == backdrop_slug), panels[2])
    styles = list(HIGHLIGHT_STYLES.items())
    ncols = 3
    nrows = int(np.ceil((len(styles) + 1) / ncols))  # +1 for the "no marker" reference

    out = INDIVIDUAL_DIR / "highlight_variants.png"
    INDIVIDUAL_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\nRendering highlight variants sheet -> {out} ...")

    fig, axes = plt.subplots(nrows, ncols, figsize=(6.4 * ncols, 6.6 * nrows),
                             facecolor=BG, gridspec_kw={"wspace": 0.06, "hspace": 0.16})
    fig.patch.set_facecolor(BG)
    flat = np.atleast_1d(axes).ravel()

    def _backdrop(ax):
        ax.set_facecolor(BG)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_edgecolor(FRAME_COLOR)
            sp.set_linewidth(0.8)
        ax.imshow(backdrop["grid"], origin="lower", cmap=backdrop["cmap"],
                  norm=backdrop["norm"], interpolation="nearest", aspect="equal")

    # Reference tile (no marker).
    _backdrop(flat[0])
    flat[0].set_title("no marker", fontsize=15, pad=8, color=SUBTLE_COLOR)

    for ax, (name, spec) in zip(flat[1:], styles):
        _backdrop(ax)
        draw_highlight(ax, spec, focus, lw=2.2)
        ax.set_title(name, fontsize=15, pad=8, color=TITLE_COLOR, fontweight="normal")
    for ax in flat[len(styles) + 1:]:
        ax.axis("off")

    fig.suptitle(
        f"Braunschweig highlight variants  (backdrop: {backdrop['title']})",
        fontsize=22, y=0.995, color=TITLE_COLOR, fontweight="bold",
    )
    fig.savefig(out, dpi=dpi, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {out}  ({out.stat().st_size / 1_000_000:.2f} MB)")
    return out


# ---------------------------------------------------------------------------
# Macro maps (zoomed-out, regionally aggregated attribute maps)
# ---------------------------------------------------------------------------
# A zoomed-out view shows where attributes differ *regionally* (north / south,
# east / west, urban / rural). At this scale the 100 m cells are aggregated to
# coarse bins (default 1 km, like the hero figure). Each attribute is a
# numerator / denominator ratio that MUST be aggregated as
# sum(numerator) / sum(denominator) per bin -- never as the mean of per-cell
# ratios -- so that dense and sparse cells are weighted correctly.
OUT_MACRO = INDIVIDUAL_DIR / "attribute_gallery_macro.png"

# Northern Germany = the coastal / northern Bundeslaender (Land code prefix).
NORTH_LAENDER = {"01", "02", "03", "04", "13"}  # SH, HH, NI, HB, MV

# Each macro attribute is a recipe; ``num`` / ``den`` are callables on the full
# DataFrame returning the per-cell numerator and denominator arrays.
MACRO_ATTRS = {
    "mean_hh_size": {
        "title": "Average household size",
        "subtitle": "people per private household",
        "cb_label": "persons / HH",
        "cmap": "managua",
        "num": lambda d: d[EINWOHNER].fillna(0).values,
        "den": lambda d: d[HH_TOT_GROESSE].fillna(0).values,
    },
    "senior_only": {
        "title": "Senior-only households",
        "subtitle": "households where everyone is 65 or older",
        "cb_label": "share",
        "cmap": "magma",
        "num": lambda d: d[HH_SENIOR_ONLY].fillna(0).values,
        "den": lambda d: d[HH_SENIOR_TOT].fillna(0).values,
    },
    "home_ownership": {
        "title": "Home ownership",
        "subtitle": "households that own (not rent) their home",
        "cb_label": "share",
        "cmap": "vanimo",
        "num": lambda d: d[EIGNER_HH].fillna(0).values,
        "den": lambda d: (d[EIGNER_HH].fillna(0).values + d[MIETER_HH].fillna(0).values),
    },
    "vacancy": {
        "title": "Vacant homes",
        "subtitle": "share of dwellings standing empty",
        "cb_label": "%",
        "cmap": "plasma",
        # Dwelling-weighted mean of the per-cell Leerstandsquote.
        "num": lambda d: d[LEER].fillna(0).values * d[WHG_TOT].fillna(0).values,
        "den": lambda d: d[WHG_TOT].fillna(0).values,
    },
    "male_share": {
        "title": "Share of men",
        "subtitle": "men as a fraction of all residents",
        "cb_label": "share",
        "cmap": "berlin",
        "num": lambda d: d[M_TOTAL].fillna(0).values,
        "den": lambda d: (d[M_TOTAL].fillna(0).values + d[F_TOTAL].fillna(0).values),
    },
    "mfh": {
        "title": "Homes in apartment buildings",
        "subtitle": "dwellings in buildings with 3 or more units",
        "cb_label": "share",
        "cmap": "viridis",
        "num": lambda d: (d[MFH_3_6].fillna(0).values + d[MFH_7_12].fillna(0).values
                          + d[MFH_13].fillna(0).values),
        "den": lambda d: d[WHG_TOT].fillna(0).values,
    },
}
# The two most legible regional stories: vacancy (a sharp east/west divide) and
# average household size (large in the rural south, small in cities / the east).
DEFAULT_MACRO_ATTRS = ["vacancy", "mean_hh_size"]


def bin_ratio_to_grid(x: np.ndarray, y: np.ndarray, num: np.ndarray,
                      den: np.ndarray, bin_m: float):
    """Aggregate num / den into (bin_m x bin_m) bins as sum(num)/sum(den).

    Returns (grid_2d, extent_in_metres). Bins with no denominator are NaN.
    """
    xi = (x // bin_m).astype(np.int64)
    yi = (y // bin_m).astype(np.int64)
    xi0, xi1 = xi.min(), xi.max()
    yi0, yi1 = yi.min(), yi.max()
    nx = int(xi1 - xi0 + 1)
    ny = int(yi1 - yi0 + 1)
    xidx = (xi - xi0).astype(np.int32)
    yidx = (yi - yi0).astype(np.int32)

    num_grid = np.zeros((ny, nx), dtype=np.float64)
    den_grid = np.zeros((ny, nx), dtype=np.float64)
    np.add.at(num_grid, (yidx, xidx), num)
    np.add.at(den_grid, (yidx, xidx), den)
    with np.errstate(invalid="ignore", divide="ignore"):
        grid = np.where(den_grid > 0, num_grid / den_grid, np.nan)

    extent = (xi0 * bin_m, (xi1 + 1) * bin_m, yi0 * bin_m, (yi1 + 1) * bin_m)
    return grid, extent


def render_macro(df: pd.DataFrame, attr_keys: list[str], region: str,
                 bin_km: float, dpi: int, focus_xy: tuple[float, float] | None = None,
                 out: Path = OUT_MACRO, scale_mode: str = "fixed") -> Path:
    """Render zoomed-out, regionally aggregated maps of the chosen attributes.

    One dark panel per attribute, side by side, in the hero visual language.
    ``focus_xy`` (EPSG:3035 metres) places a small Braunschweig marker so the
    study area is locatable within the wider region.

    ``scale_mode`` selects the colour scale (see resolve_scale): "fixed"
    (default, reproducible FIXED_DISPLAY_BOUNDS shared with the close-up
    gallery), "uniform" (all ratio panels on 0-100 %) or "robust" (per-region
    percentiles).
    """
    bin_m = bin_km * 1000.0
    if region == "north":
        sub = df[df[LAND_COL].isin(NORTH_LAENDER)]
        region_label = "Northern Germany"
    else:
        sub = df
        region_label = "Germany"
    print(f"\nMacro view: {region_label}, {len(sub):,} cells, {bin_km:g} km bins"
          f" ({scale_mode} scale)")

    x, y = parse_coords(sub[GITTER_ID])

    n = len(attr_keys)
    # A roomy wspace keeps each colorbar (and its rotated label) clear of the
    # neighbouring map.
    fig, axes = plt.subplots(1, n, figsize=(8.8 * n, 10), facecolor=BG,
                             gridspec_kw={"wspace": 0.5})
    fig.patch.set_facecolor(BG)
    flat = np.atleast_1d(axes).ravel()

    for ax, key in zip(flat, attr_keys):
        spec = MACRO_ATTRS[key]
        grid, extent = bin_ratio_to_grid(x, y, spec["num"](sub), spec["den"](sub), bin_m)
        grid, vmin, vmax, cb_label = resolve_scale(key, grid, spec["cb_label"], scale_mode)
        v = grid[np.isfinite(grid)]
        print(f"  {spec['title']:46s} bins={np.isfinite(grid).sum():6d}  "
              f"vmin={vmin:.3f}  vmax={vmax:.3f}  "
              f"(data {v.min():.3f}..{v.max():.3f})" if len(v) else
              f"  {spec['title']:46s} - no finite bins")

        ax.set_facecolor(BG)
        im = ax.imshow(grid, origin="lower", extent=extent,
                       cmap=glow_cmap(spec["cmap"]),
                       norm=mcolors.Normalize(vmin=vmin, vmax=vmax),
                       aspect="equal", interpolation="nearest")
        set_titles(ax, spec["title"], spec.get("subtitle"), 17)
        ax.axis("off")

        # A Braunschweig marker only makes sense for the regional (north) view;
        # the all-Germany maps are general and need no study-area marker.
        if focus_xy is not None and region == "north":
            fx, fy = focus_xy
            ax.plot([fx], [fy], marker="o", markersize=7, markeredgecolor=HL_CYAN,
                    markerfacecolor="none", markeredgewidth=2.0, zorder=6,
                    path_effects=[pe.withStroke(linewidth=3.0, foreground=BG)])
            ax.annotate("Braunschweig", xy=(fx, fy), xytext=(8, 8),
                        textcoords="offset points", color=HL_CYAN, fontsize=12,
                        fontweight="bold", zorder=6,
                        path_effects=[pe.withStroke(linewidth=2.5, foreground=BG)])

        cb = fig.colorbar(im, ax=ax, fraction=0.045, pad=0.015, shrink=0.72)
        style_colorbar(cb, 13, cb_label)

    fig.suptitle(
        f"Regional variation at {bin_km:g} km - {region_label}",
        fontsize=22, y=0.97, color=TITLE_COLOR, fontweight="bold",
    )
    fig.text(0.5, 0.02, ATTR_TEXT, ha="center", va="bottom", fontsize=11,
             color=SUBTLE_COLOR)

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=dpi, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    size_mb = out.stat().st_size / 1_000_000
    print(f"Saved {out}  ({size_mb:.2f} MB)")
    if size_mb > 3.5:
        print(f"WARNING: file {size_mb:.2f} MB > 3.5 MB - re-rendering at lower dpi ...")
        plt.close("all")
        return render_macro(df, attr_keys, region, bin_km, max(80, dpi - 30),
                            focus_xy=focus_xy, out=out, scale_mode=scale_mode)
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def make_gallery(ars5: str = "03101", dpi: int = 150, ncols: int = 2,
                 individual: bool = False, region_name: str | None = None,
                 highlight: str | None = None, variants: bool = False,
                 macro: bool = False, macro_attrs: list[str] | None = None,
                 macro_region: str = "germany", macro_bin_km: float = 5.0,
                 render_gallery: bool = True, scale_mode: str = "fixed") -> Path | None:
    t0 = time.time()
    print(f"Reading {PARQUET} ...")
    table = pq.read_table(PARQUET, columns=NEEDED_COLS)
    df = table.to_pandas()
    print(f"  {len(df):,} rows loaded in {time.time()-t0:.1f}s")

    t1 = time.time()
    win_df, cx, cy, x_w, y_w = build_window(df, ars5)
    print(f"  Window {len(win_df):,} cells  ({time.time()-t1:.1f}s)")

    if highlight is not None and highlight not in HIGHLIGHT_STYLES:
        raise ValueError(
            f"Unknown --highlight {highlight!r}. Choose one of: "
            f"{', '.join(HIGHLIGHT_STYLES)}"
        )
    hl_spec = HIGHLIGHT_STYLES[highlight] if highlight else None

    out: Path | None = None
    if render_gallery:
        panels = compute_panels(win_df, x_w, y_w, cx, cy, scale_mode=scale_mode)
        focus = compute_focus_geometry(win_df, x_w, y_w, ars5, cx, cy)
        region = region_name or ("Braunschweig region" if ars5 == "03101" else f"ARS {ars5}")
        out = render_combined(panels, ars5, ncols, dpi, region, highlight=hl_spec, focus=focus)
        if individual:
            render_individual(panels, dpi, highlight=hl_spec, focus=focus)
        if variants:
            render_variants_sheet(panels, focus, dpi)

    if macro:
        keys = macro_attrs or DEFAULT_MACRO_ATTRS
        unknown = [k for k in keys if k not in MACRO_ATTRS]
        if unknown:
            raise ValueError(
                f"Unknown macro attribute(s) {unknown}. Choose from: "
                f"{', '.join(MACRO_ATTRS)}"
            )
        out = render_macro(df, keys, macro_region, macro_bin_km, dpi, focus_xy=(cx, cy),
                           scale_mode=scale_mode)

    print(f"\nDone in {time.time()-t0:.1f}s total")
    return out


def main():
    parser = argparse.ArgumentParser(
        description="Render a dark, glowing 6-panel attribute gallery for a 50x50 km regional window."
    )
    parser.add_argument(
        "--window-ars",
        default="03101",
        metavar="ARS5",
        help="5-character ARS prefix identifying the target Kreis (default: 03101 = Braunschweig)",
    )
    parser.add_argument(
        "--region-name",
        default=None,
        help="Human-readable region label for the title (default: derived from --window-ars)",
    )
    parser.add_argument(
        "--ncols",
        type=int,
        default=2,
        choices=(2, 3),
        help="Panels per row in the combined figure (default: 2 = larger panels, README-legible)",
    )
    parser.add_argument(
        "--individual",
        action="store_true",
        help="Additionally write each panel as a standalone PNG into docs/assets/gallery/",
    )
    parser.add_argument(
        "--highlight",
        default=None,
        choices=sorted(HIGHLIGHT_STYLES),
        help="Mark the focus Kreis (Braunschweig) with this style on every panel",
    )
    parser.add_argument(
        "--variants",
        action="store_true",
        help="Render a contact sheet comparing all highlight styles (for choosing one)",
    )
    parser.add_argument(
        "--macro",
        action="store_true",
        help="Additionally render zoomed-out, regionally aggregated attribute maps",
    )
    parser.add_argument(
        "--macro-attrs",
        default=None,
        help=("Comma-separated macro attributes (default: "
              f"{','.join(DEFAULT_MACRO_ATTRS)}). Available: {','.join(MACRO_ATTRS)}"),
    )
    parser.add_argument(
        "--macro-region",
        default="germany",
        choices=("germany", "north"),
        help="Macro extent: all of Germany or Northern Germany (default: germany)",
    )
    parser.add_argument(
        "--macro-bin-km",
        type=float,
        default=5.0,
        help="Aggregation bin size for macro maps in km (default: 5.0)",
    )
    parser.add_argument(
        "--scale",
        default="fixed",
        choices=("fixed", "uniform", "robust"),
        help=("Colour scale for all plots: 'fixed' (default; reproducible per-attribute "
              "ranges, same in gallery and macro), 'uniform' (all ratio attributes on "
              "0-100%%; low contrast on narrow-band ones), or 'robust' (per-region "
              "percentiles; max contrast, not reproducible)."),
    )
    parser.add_argument(
        "--no-gallery",
        action="store_true",
        help="Skip the standard windowed gallery (useful when iterating on --macro)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=150,
        help="Output DPI (default: 150; combined figure auto-reduced if > 3.5 MB)",
    )
    args = parser.parse_args()
    macro_attrs = (
        [s.strip() for s in args.macro_attrs.split(",") if s.strip()]
        if args.macro_attrs else None
    )
    make_gallery(
        ars5=args.window_ars,
        dpi=args.dpi,
        ncols=args.ncols,
        individual=args.individual,
        region_name=args.region_name,
        highlight=args.highlight,
        variants=args.variants,
        macro=args.macro,
        macro_attrs=macro_attrs,
        macro_region=args.macro_region,
        macro_bin_km=args.macro_bin_km,
        render_gallery=not args.no_gallery,
        scale_mode=args.scale,
    )


if __name__ == "__main__":
    main()
