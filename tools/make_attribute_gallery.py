"""Generate the attribute gallery figure for the cleancensus README.

Six-panel 2×3 matplotlib figure at 100 m resolution, white background,
centred on a 50 × 50 km regional window.

Panels
------
1. Male share (all ages)
2. Senior-only households (share)
3. Dwellings in multi-family buildings (share)
4. Home-ownership (share of households)
5. Vacancy rate (%)
6. Mean household size

Usage
-----
    uv run --no-sync python tools/make_attribute_gallery.py
    uv run --no-sync python tools/make_attribute_gallery.py --window-ars 09162

Data source (read-only)
------------------------
    data/outputs/cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar_v3.parquet

Default window: 50 × 50 km centred on Braunschweig (ARS-5 prefix 03101).
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
OUT = Path("docs/assets/attribute_gallery.png")

# ---------------------------------------------------------------------------
# Columns needed
# ---------------------------------------------------------------------------
# Panel 1 — Male share
M_TOTAL = "M_TOTAL"
F_TOTAL = "F_TOTAL"

# Panel 2 — Senior-only households share
HH_SENIOR_ONLY = "HH_nurSenioren_Seniorenstatus_eines_privaten_Haushalts_100m-Gitter"
HH_SENIOR_TOT = "Insgesamt_Haushalte_Seniorenstatus_eines_privaten_Haushalts_100m-Gitter_adj"

# Panel 3 — Dwellings in MFH share  (Wohnung universe)
MFH_3_6 = "MFH_3bis6Wohnungen_Wohnung_Gebaeudetyp_Groesse_100m-Gitter"
MFH_7_12 = "MFH_7bis12Wohnungen_Wohnung_Gebaeudetyp_Groesse_100m-Gitter"
MFH_13 = "MFH_13undmehrWohnungen_Wohnung_Gebaeudetyp_Groesse_100m-Gitter"
WHG_TOT = "Insgesamt_Wohnungen_Wohnung_Gebaeudetyp_Groesse_100m-Gitter_adj"

# Panel 4 — Home-ownership
EIGNER_HH = "EigentuemerHH_Tenure_100m-Gitter"
MIETER_HH = "MieterHH_Tenure_100m-Gitter"

# Panel 5 — Vacancy rate
LEER = "Leerstandsquote_Leerstandsquote_100m-Gitter"

# Panel 6 — Mean HH size
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

WINDOW_KM = 50_000  # ±25 000 m from centre
ATTR_TEXT = (
    "© Statistische Ämter des Bundes und der Länder, Zensus 2022 — processed by cleancensus"
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
    """Element-wise ratio; NaN where denominator ≤ 0."""
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.where(den > 0, num / den, np.nan)
    return r


def robust_vmax(arr: np.ndarray, pct: float) -> float:
    finite = arr[np.isfinite(arr) & (arr > 0)]
    if len(finite) == 0:
        return 1.0
    return float(np.percentile(finite, pct))


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
    """Place scalar values on a 2-D raster (nh rows × nw cols).

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


def add_colorbar(fig, ax, im, label: str, fontsize: float = 7.5):
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02, shrink=0.85)
    cb.set_label(label, fontsize=fontsize, labelpad=4)
    cb.ax.tick_params(labelsize=fontsize - 0.5)
    return cb


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_window(df: pd.DataFrame, ars5: str, half: float = 25_000.0):
    """Return a sub-DataFrame clipped to a half×2 km window around the ARS centroid."""
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


def make_gallery(ars5: str = "03101", dpi: int = 140) -> Path:
    t0 = time.time()
    print(f"Reading {PARQUET} ...")
    table = pq.read_table(PARQUET, columns=NEEDED_COLS)
    df = table.to_pandas()
    print(f"  {len(df):,} rows loaded in {time.time()-t0:.1f}s")

    # Window
    t1 = time.time()
    win_df, cx, cy, x_w, y_w = build_window(df, ars5)
    print(f"  Window {len(win_df):,} cells  ({time.time()-t1:.1f}s)")

    x_min = cx - 25_000
    y_min = cy - 25_000
    NW, NH = 500, 500  # 100 m cells in a 50 × 50 km box

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

    # ---- Robust bounds ----
    vmax_senior = robust_vmax(g2, 98)
    vmax_leer = robust_vmax(g5, 95)

    # ---- Diagnostics ----
    print("\nPer-panel statistics (window cells):")
    for name, arr in [
        ("Male share", g1), ("Senior-only HH share", g2),
        ("MFH dwelling share", g3), ("Owner-occupancy share", g4),
        ("Vacancy rate (%)", g5), ("Mean HH size", g6),
    ]:
        v = arr[np.isfinite(arr)]
        if len(v):
            print(f"  {name:30s} n={len(v):6d}  "
                  f"min={v.min():.3f}  median={np.median(v):.3f}  "
                  f"max={v.max():.3f}")
        else:
            print(f"  {name:30s} — no finite values")

    # ---- Figure ----
    print("\nRendering figure ...")
    fig, axes = plt.subplots(
        2, 3, figsize=(20, 13),
        facecolor="white",
        gridspec_kw={"wspace": 0.28, "hspace": 0.20},
    )
    fig.patch.set_facecolor("white")

    panels = [
        # (grid, title, cmap, norm, colorbar_label)
        (
            g1,
            "Male share (all ages)",
            "coolwarm",
            mcolors.Normalize(vmin=0.42, vmax=0.58),
            "share",
        ),
        (
            g2,
            "Senior-only households (share)",
            "magma",
            mcolors.Normalize(vmin=0, vmax=vmax_senior),
            "share",
        ),
        (
            g3,
            "Dwellings in multi-family buildings (share)",
            "viridis",
            mcolors.Normalize(vmin=0, vmax=1),
            "share",
        ),
        (
            g4,
            "Home-ownership (share of households)",
            "coolwarm_r",
            mcolors.Normalize(vmin=0, vmax=1),
            "share",
        ),
        (
            g5,
            "Vacancy rate (%)",
            "plasma",
            mcolors.Normalize(vmin=0, vmax=vmax_leer),
            "%",
        ),
        (
            g6,
            "Mean household size",
            "coolwarm",
            mcolors.Normalize(vmin=1.2, vmax=3.2),
            "persons / HH",
        ),
    ]

    for ax, (arr, title, cmap, norm, cb_label) in zip(axes.flat, panels):
        ax.set_facecolor("white")
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_edgecolor("black")
            spine.set_linewidth(0.6)

        im = ax.imshow(
            arr,
            origin="lower",
            cmap=cmap,
            norm=norm,
            interpolation="nearest",
            aspect="equal",
        )
        ax.set_title(title, fontsize=10.5, pad=6, color="black", fontweight="normal")
        add_colorbar(fig, ax, im, cb_label, fontsize=7.5)

    # Suptitle + attribution
    fig.suptitle(
        "Computed attributes at 100 m — Braunschweig region (50 × 50 km)",
        fontsize=13, y=0.98, color="black", fontweight="bold",
    )
    fig.text(
        0.5, -0.005,
        ATTR_TEXT,
        ha="center", va="bottom", fontsize=6.5, color="#555555",
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=dpi, facecolor="white", bbox_inches="tight")
    plt.close(fig)

    size_mb = OUT.stat().st_size / 1_000_000
    elapsed = time.time() - t0
    print(f"\nSaved {OUT}  ({size_mb:.2f} MB)  in {elapsed:.1f}s total")

    if size_mb > 3.5:
        print(f"WARNING: file size {size_mb:.2f} MB > 3.5 MB — re-running at lower dpi ...")
        plt.close("all")
        return make_gallery(ars5=ars5, dpi=max(80, dpi - 30))

    return OUT


def main():
    parser = argparse.ArgumentParser(
        description="Render a 6-panel attribute gallery for a 50×50 km regional window."
    )
    parser.add_argument(
        "--window-ars",
        default="03101",
        metavar="ARS5",
        help="5-character ARS prefix identifying the target Kreis (default: 03101 = Braunschweig)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=140,
        help="Output DPI (default: 140; auto-reduced if file > 3.5 MB)",
    )
    args = parser.parse_args()
    make_gallery(ars5=args.window_ars, dpi=args.dpi)


if __name__ == "__main__":
    main()
