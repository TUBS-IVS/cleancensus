"""Generate the hero figure for the cleancensus README.

Two-panel matplotlib figure from the prepared 100 m parquet:
  Panel 1 — Population density (log scale), dark background, magma colormap
  Panel 2 — Home-ownership rate (Eigentuemerquote), viridis colormap

Usage:
    .venv/Scripts/python tools/make_hero_figure.py
"""
from __future__ import annotations

import re
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import pyarrow.parquet as pq

PARQUET = Path("data/inputs/cells_100m_with_gender_backf_binneds_happyorphans_with_aggs_regiostar.parquet")
OUT = Path("docs/assets/hero_grids.png")

BG = "#0d1117"
TITLE_COLOR = "#c9d1d9"
ATTR_COLOR = "#8b949e"
ATTR_TEXT = "© Statistische Ämter des Bundes und der Länder, Zensus 2022"

POP_COL = "Einwohner_Bevoelkerungszahl_100m-Gitter"
EIQ_COL = "Eigentuemerquote_Eigentuemerquote_100m-Gitter"
GID_COL = "GITTER_ID_100m"

# GITTER_ID format: CRS3035RES100mN<easting_cm>E<northing_cm>
# The documented formula: E = int(N_part) * 100 + 50 (cell midpoint, metres)
_GID_RE = re.compile(r"N(\d+)E(\d+)$")


def parse_coords(gid_series):
    """Parse GITTER_ID_100m -> (x_m, y_m) lower-left corner in EPSG:3035 metres.

    Format: CRS3035RES100mN<northing_m>E<easting_m>
    The N and E values are already the lower-left corner coordinates in whole metres.
    Cell centre = N + 50, E + 50 (50 m offset to centre of 100m cell).
    """
    import pandas as pd
    n_vals = gid_series.str.extract(r"N(\d+)E(\d+)", expand=True)
    # column 0 = N (northing / y), column 1 = E (easting / x)
    y = pd.to_numeric(n_vals[0]) + 50   # cell centre northing
    x = pd.to_numeric(n_vals[1]) + 50   # cell centre easting
    return x.values, y.values


def bin_to_grid(x, y, values, bin_m=1000, agg="sum", weights=None):
    """Aggregate values into (bin_m × bin_m) bins. Returns (grid_2d, extent)."""
    xi = (x // bin_m).astype(np.int64)
    yi = (y // bin_m).astype(np.int64)

    xi_min, xi_max = xi.min(), xi.max()
    yi_min, yi_max = yi.min(), yi.max()

    nx = int(xi_max - xi_min + 1)
    ny = int(yi_max - yi_min + 1)

    xi_idx = (xi - xi_min).astype(np.int32)
    yi_idx = (yi - yi_min).astype(np.int32)

    if agg == "sum":
        grid = np.zeros((ny, nx), dtype=np.float64)
        np.add.at(grid, (yi_idx, xi_idx), values)
    elif agg == "wmean":
        assert weights is not None
        num = np.zeros((ny, nx), dtype=np.float64)
        den = np.zeros((ny, nx), dtype=np.float64)
        np.add.at(num, (yi_idx, xi_idx), values * weights)
        np.add.at(den, (yi_idx, xi_idx), weights)
        with np.errstate(invalid="ignore", divide="ignore"):
            grid = np.where(den > 0, num / den, np.nan)
    else:
        raise ValueError(f"Unknown agg={agg!r}")

    extent = (
        xi_min * bin_m, (xi_max + 1) * bin_m,  # left, right
        yi_min * bin_m, (yi_max + 1) * bin_m,  # bottom, top
    )
    return grid, extent


def main():
    t0 = time.time()
    print(f"Reading columns from {PARQUET} ...")

    table = pq.read_table(PARQUET, columns=[GID_COL, POP_COL, EIQ_COL])
    df = table.to_pandas()
    print(f"  {len(df):,} rows loaded in {time.time()-t0:.1f}s")

    # Parse coordinates
    t1 = time.time()
    x, y = parse_coords(df[GID_COL])
    print(f"  Coordinates parsed in {time.time()-t1:.1f}s")

    pop = df[POP_COL].fillna(0).values.astype(np.float64)
    eiq = df[EIQ_COL].fillna(0).values.astype(np.float64)

    # Mask cells with no population for owner-occupancy weighted mean
    pop_mask = pop > 0
    eiq_nonzero = np.where(pop_mask & (eiq > 0), eiq, np.nan)

    # Bin to 1 km grid (641x859 for Germany - very manageable)
    print("  Binning to 1 km grid ...")
    t2 = time.time()
    pop_grid, extent = bin_to_grid(x, y, pop, bin_m=1000, agg="sum")
    eiq_grid, _ = bin_to_grid(x, y, np.where(np.isfinite(eiq_nonzero), eiq_nonzero, 0),
                               bin_m=1000, agg="wmean",
                               weights=np.where(np.isfinite(eiq_nonzero), pop, 0))
    print(f"  Binning done in {time.time()-t2:.1f}s")

    # Mask zero-pop cells
    pop_grid = np.where(pop_grid > 0, pop_grid, np.nan)
    # eiq_grid already has NaN for no-signal cells

    # Build figure
    fig, axes = plt.subplots(1, 2, figsize=(16, 10),
                             facecolor=BG, gridspec_kw={"wspace": 0.04})
    fig.patch.set_facecolor(BG)

    # --- Panel 1: Population density (log scale) ---
    ax1 = axes[0]
    ax1.set_facecolor(BG)

    lnorm = mcolors.LogNorm(vmin=1, vmax=np.nanmax(pop_grid))
    im1 = ax1.imshow(
        pop_grid,
        origin="lower",
        extent=extent,
        norm=lnorm,
        cmap="magma",
        aspect="equal",
        interpolation="nearest",
    )
    ax1.set_title("Population — Germany at 100 m (log scale)",
                  color=TITLE_COLOR, fontsize=13, pad=8)
    ax1.axis("off")
    cb1 = fig.colorbar(im1, ax=ax1, fraction=0.03, pad=0.01, shrink=0.7)
    cb1.ax.yaxis.set_tick_params(color=ATTR_COLOR, labelcolor=ATTR_COLOR)
    cb1.outline.set_edgecolor(ATTR_COLOR)
    ax1.text(0.99, 0.01, ATTR_TEXT, transform=ax1.transAxes,
             ha="right", va="bottom", color=ATTR_COLOR, fontsize=5.5)

    # --- Panel 2: Home-ownership rate ---
    ax2 = axes[1]
    ax2.set_facecolor(BG)

    # Eigentuemerquote is ALREADY in percent (0-100) — do not rescale.
    im2 = ax2.imshow(
        eiq_grid,
        origin="lower",
        extent=extent,
        vmin=0, vmax=100,
        cmap="viridis",
        aspect="equal",
        interpolation="nearest",
    )
    ax2.set_title("Home-ownership rate (%) — household-weighted, 1 km bins",
                  color=TITLE_COLOR, fontsize=13, pad=8)
    ax2.axis("off")
    cb2 = fig.colorbar(im2, ax=ax2, fraction=0.03, pad=0.01, shrink=0.7)
    cb2.ax.yaxis.set_tick_params(color=ATTR_COLOR, labelcolor=ATTR_COLOR)
    cb2.outline.set_edgecolor(ATTR_COLOR)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=150, facecolor=BG, bbox_inches="tight")
    plt.close(fig)

    size_mb = OUT.stat().st_size / 1_000_000
    print(f"Saved {OUT} ({size_mb:.2f} MB) in {time.time()-t0:.1f}s total")
    if size_mb > 3.0:
        print("WARNING: file > 3 MB — re-saving at dpi=100 ...")
        fig2, axes2 = plt.subplots(1, 2, figsize=(16, 10),
                                   facecolor=BG, gridspec_kw={"wspace": 0.04})
        fig2.patch.set_facecolor(BG)
        ax1b = axes2[0]; ax1b.set_facecolor(BG)
        ax1b.imshow(pop_grid, origin="lower", extent=extent, norm=lnorm,
                    cmap="magma", aspect="equal", interpolation="nearest")
        ax1b.set_title("Population — Germany at 100 m (log scale)",
                       color=TITLE_COLOR, fontsize=11, pad=6)
        ax1b.axis("off")
        ax1b.text(0.99, 0.01, ATTR_TEXT, transform=ax1b.transAxes,
                  ha="right", va="bottom", color=ATTR_COLOR, fontsize=5)
        ax2b = axes2[1]; ax2b.set_facecolor(BG)
        ax2b.imshow(eiq_grid * 100, origin="lower", extent=extent,
                    vmin=0, vmax=100, cmap="viridis", aspect="equal",
                    interpolation="nearest")
        ax2b.set_title("Home-ownership rate (%)", color=TITLE_COLOR, fontsize=11, pad=6)
        ax2b.axis("off")
        fig2.savefig(OUT, dpi=100, facecolor=BG, bbox_inches="tight")
        plt.close(fig2)
        size_mb = OUT.stat().st_size / 1_000_000
        print(f"Re-saved at dpi=100: {size_mb:.2f} MB")


if __name__ == "__main__":
    main()
