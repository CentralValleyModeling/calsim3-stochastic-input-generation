"""
Shared 2-panel plotter: monthly time series + non-exceedance CDF
================================================================
Canonical validation figure used across the repo: left panel is the monthly
time series for N series, right panel is the empirical non-exceedance CDF for
the same N series. An optional R2 / NSE / PBIAS annotation box can be rendered
on the time-series panel -- either from caller-supplied strings, or
auto-computed against a designated baseline series.

Designed to replace ~5 near-duplicate plot blocks across the Product A /
historical validation scripts (``qmap_product_a_from_pairs._plot_timeseries_cdf``,
``mod_reservoir/storage_curves/_4_oroville_level5._plot_product_a_vs_historical``,
``postprocessing/calsim_runs/_productA_postproc`` 2-panel block, etc.) so the
canonical figure style lives in one place.

Annotation-box behavior
-----------------------
- Nothing supplied            -> no box drawn (exploratory / single-series).
- ``metric_lines=[...]``       -> caller's strings rendered verbatim.
- ``compute_metrics_from=i``   -> auto-compute R2 / NSE / PBIAS for every other
  series vs ``series[i]``. Pairwise-finite masking drops NaN/inf pairs. With one
  comparison series the line has no label prefix; with multiple, each line is
  prefixed by the series' ``label``.

If both ``metric_lines`` and ``compute_metrics_from`` are supplied,
``metric_lines`` wins (manual override).

Subtitle behavior
-----------------
- ``subtitle=None`` (default)  -> auto-generate ``(WY YYYY-YYYY)`` spanning all
  series (water year = calendar year + 1 if month >= 10).
- ``subtitle="..."``           -> render the caller's string verbatim.
- ``subtitle=""``              -> no subtitle at all.

Output formats
--------------
``out_path`` suffix drives the writer. Raster suffixes (.png, .jpg, ...) honor
``dpi`` (default 300, publication grade). Vector suffixes (.pdf, .svg, .eps,
.ps) ignore ``dpi`` since line art is resolution-independent. TrueType font
embedding (``fonttype = 42``) is enabled module-wide so PDF/PS outputs are not
rejected by journals that ban Type-3 fonts.

When ``out_path is None`` the live ``matplotlib.figure.Figure`` is returned
(handy for tests or multi-page PDFs); otherwise the figure is saved with
``bbox_inches='tight'`` and a white facecolor, then closed.

Public API
----------
- ``plot_ts_cdf(series, title, ...)``         -- main entry point.
- ``Series(label, dates, values, color=None, linewidth=0.9, alpha=0.85)``
                                              -- per-series dataclass; ``color``
                                                 falls back to ``default_palette``.
- ``default_palette()``                       -- colorblind palette with
                                                 Vermillion+1 as the 2nd colour.
- ``format_metric_line(r2, nse, pbias, label="")``
                                              -- format one
                                                 ``R2=...  NSE=...  PBIAS=...%``
                                                 string with N/A guards for NaN/inf.

Defaults
--------
``figsize = (6.5, 3.25)``  -- single-column journal width
``width_ratios = (1.6, 1.0)``  -- TS panel wider than CDF
``dpi = 300``  -- raster resolution
``tick_interval_years``  -- auto-selected from the date span: 1 / 5 / 10 years

Dependencies
------------
numpy, matplotlib, seaborn

Usage
-----
::

    from utils.plot_ts_cdf import Series, plot_ts_cdf, format_metric_line

    # 1) Historical vs Product A, auto-computed metrics
    plot_ts_cdf(
        series=[
            Series("Historical", dates, hist_vals),
            Series("Product A",  dates, prod_vals),
        ],
        title="C_OROVL (TAF)",
        compute_metrics_from=0,
        out_path="figs/c_orovl.png",
    )

    # 2) Multi-scenario, auto-labels each metric row
    plot_ts_cdf(
        series=[
            Series("Historical", dates, hist),
            Series("Product A",  dates, prod_a),
            Series("Product B",  dates, prod_b),
        ],
        title="Delta Outflow (TAF)",
        compute_metrics_from=0,
        out_path="figs/delta_outflow.pdf",   # vector output
    )

    # 3) Manual override with custom metrics + period subtitle
    plot_ts_cdf(
        series=[Series("Historical", dates, hist), Series("Product A", dates, prod)],
        title="Shasta Storage (TAF)",
        metric_lines=[format_metric_line(r2_ann, nse_ann, pbias_ann, label="Annual")],
        subtitle="(WY 1972-2021)",
        out_path="figs/shasta.png",
    )

    # 4) Exploratory: just show the series, no metrics
    plot_ts_cdf(series=[...], title="Stochastic exploration",
                out_path="figs/explore.png")
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import matplotlib as mpl
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

# Embed TrueType fonts in PDF/PS so reviewers see exactly what we render
mpl.rcParams["pdf.fonttype"] = 42
mpl.rcParams["ps.fonttype"] = 42


# -- Canonical report theme --------------------------------------------------
# Applied via _apply_theme() inside plot_ts_cdf so every figure has the same
# look without polluting global rcParams at import time.
_THEME_RC: dict = {
    "figure.dpi": 200,
    "savefig.dpi": 300,
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "Calibri", "DejaVu Sans"],
    "font.size": 8,
    "axes.titlesize": 8,
    "axes.titleweight": "semibold",
    "axes.labelsize": 8,
    "axes.labelweight": "medium",
    "axes.edgecolor": "0.25",
    "axes.linewidth": 0.6,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "xtick.major.width": 0.5,
    "ytick.major.width": 0.5,
    "grid.linewidth": 0.35,
    "grid.alpha": 0.40,
    "lines.linewidth": 0.9,
    "legend.fontsize": 7,
    "legend.title_fontsize": 8,
    "legend.framealpha": 0.90,
    "legend.edgecolor": "0.55",
    "figure.titlesize": 8,
    "figure.titleweight": "bold",
    "mathtext.default": "regular",
}


def _apply_theme() -> None:
    """Apply the canonical theme (whitegrid + report-grade rcParams)."""
    sns.set_theme(style="whitegrid", context="paper", font_scale=1.0, rc=_THEME_RC)


# -- Defaults -----------------------------------------------------------------

_DEFAULT_FIGSIZE = (6.5, 3.25)
_DEFAULT_WIDTH_RATIOS = (1.6, 1.0)
_DEFAULT_DPI = 300
_VECTOR_SUFFIXES = {".pdf", ".svg", ".eps", ".ps"}


def default_palette() -> list[tuple]:
    """Canonical colorblind palette with Vermillion+1 as the 2nd colour."""
    cb = list(sns.color_palette("colorblind"))
    cb[1] = (0.918, 0.341, 0.220)  # ~#EB5738
    return cb


def format_metric_line(r2: float, nse: float, pbias: float, label: str = "") -> str:
    """Render 'R2=...  NSE=...  PBIAS=...%' with N/A guards.

    If ``label`` is non-empty, it is prepended as '<label>:  '. Use this when
    multiple comparison series share one annotation box; omit for single-series
    plots where the label would be redundant.
    """
    r2_s = f"{r2:.2f}" if np.isfinite(r2) else "N/A"
    nse_s = f"{nse:.2f}" if np.isfinite(nse) else "N/A"
    pb_s = f"{pbias:.1f}%" if np.isfinite(pbias) else "N/A"
    line = f"R\u00b2={r2_s}   NSE={nse_s}   PBIAS={pb_s}"
    return f"{label}:  {line}" if label else line


# -- Data class ---------------------------------------------------------------

@dataclass
class Series:
    """One series rendered on both the TS panel and the CDF panel."""
    label: str
    dates: Sequence
    values: Sequence
    color: tuple | str | None = None
    linewidth: float = 0.9
    alpha: float = 0.85


# -- Main API -----------------------------------------------------------------

def plot_ts_cdf(
    series: Iterable[Series],
    title: str,
    unit: str = "TAF",
    out_path: str | Path | None = None,
    metric_lines: Sequence[str] | None = None,
    compute_metrics_from: int | None = None,
    subtitle: str | None = None,
    tick_interval_years: int | None = None,
    figsize: tuple[float, float] = _DEFAULT_FIGSIZE,
    width_ratios: tuple[float, float] = _DEFAULT_WIDTH_RATIOS,
    dpi: int = _DEFAULT_DPI,
):
    """Build the 2-panel (monthly TS + non-exceedance CDF) figure.

    See module docstring for argument semantics. Returns the Figure when
    ``out_path`` is None; otherwise saves to disk, closes, and returns None.
    """
    series_list = list(series)
    if not series_list:
        raise ValueError("plot_ts_cdf requires at least one Series.")

    _apply_theme()

    palette = default_palette()
    for i, s in enumerate(series_list):
        if s.color is None:
            s.color = palette[i % len(palette)]

    # Auto-compute metrics vs a baseline series if requested and the caller
    # didn't already supply metric_lines.
    if metric_lines is None and compute_metrics_from is not None:
        metric_lines = _auto_metric_lines(series_list, compute_metrics_from)

    fig, (ax_ts, ax_cdf) = plt.subplots(
        nrows=1, ncols=2, figsize=figsize,
        gridspec_kw={"width_ratios": list(width_ratios)},
    )

    # -- Left: monthly time series --
    for s in series_list:
        ax_ts.plot(
            s.dates, s.values,
            color=s.color, linewidth=s.linewidth,
            label=s.label, alpha=s.alpha,
        )
    ax_ts.set_title("Monthly Time Series")
    ax_ts.set_xlabel("Date")
    ax_ts.set_ylabel(unit)

    if tick_interval_years is None:
        span = _date_span_years(series_list[0].dates)
        tick_interval_years = 1 if span <= 10 else 5 if span <= 30 else 10
    ax_ts.xaxis.set_major_locator(mdates.YearLocator(tick_interval_years))
    ax_ts.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate(rotation=35, ha="right")

    if metric_lines:
        ax_ts.text(
            0.02, 0.97, "\n".join(metric_lines),
            transform=ax_ts.transAxes,
            va="top", ha="left", fontsize=7,
            fontfamily="sans-serif",
            bbox=dict(
                boxstyle="round,pad=0.35",
                facecolor="white", edgecolor="0.7", alpha=0.88,
            ),
        )

    # -- Right: empirical non-exceedance CDF --
    for s in series_list:
        arr = np.sort(np.asarray(s.values, dtype=float))
        arr = arr[np.isfinite(arr)]
        if arr.size == 0:
            continue
        cdf = np.arange(1, arr.size + 1) / arr.size * 100.0
        ax_cdf.plot(
            cdf, arr,
            color=s.color, linewidth=s.linewidth, alpha=0.9,
            label=s.label,
        )
    ax_cdf.set_title("Non-Exceedance CDF")
    ax_cdf.set_xlabel("Non-Exceedance Probability (%)")
    ax_cdf.set_ylabel("")
    ax_cdf.set_xlim(0, 100)

    # -- Titles & legend --
    # Auto WY-range subtitle when caller didn't provide one.
    if subtitle is None:
        subtitle = _wy_range_subtitle(series_list)
    fig.suptitle(title, y=1.02)
    if subtitle:
        fig.text(
            0.5, 0.97, subtitle,
            ha="center", va="top",
            fontsize=8, fontstyle="italic", color="0.35",
            transform=fig.transFigure,
        )
    fig.tight_layout()

    handles, labels = ax_ts.get_legend_handles_labels()
    fig.legend(
        handles, labels,
        loc="upper left",
        bbox_to_anchor=(0.01, 0.99),
        ncol=len(series_list),
        fontsize=7,
        frameon=False,
        handlelength=2.0,
        handletextpad=0.6,
        borderpad=0.7,
    )

    if out_path is None:
        return fig

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Vector formats ignore dpi for line art; pass dpi only for raster outputs.
    save_kwargs = {"bbox_inches": "tight", "facecolor": "white"}
    if out_path.suffix.lower() not in _VECTOR_SUFFIXES:
        save_kwargs["dpi"] = dpi
    fig.savefig(out_path, **save_kwargs)
    plt.close(fig)
    return None


# -- Internals ----------------------------------------------------------------

def _date_span_years(dates: Sequence) -> int:
    try:
        d0, d1 = np.asarray(dates[0]), np.asarray(dates[-1])
        return max(1, int((d1.astype("datetime64[Y]") - d0.astype("datetime64[Y]")).astype(int)) + 1)
    except Exception:
        return 100


def _wy_range_subtitle(series_list: list[Series]) -> str | None:
    """Return '(WY YYYY-YYYY)' covering all series, or None if undatable."""
    try:
        d = np.concatenate([np.asarray(s.dates, dtype="datetime64[D]")
                            for s in series_list if len(s.dates)])
        if d.size == 0:
            return None
        years = d.astype("datetime64[Y]").astype(int) + 1970
        months = d.astype("datetime64[M]").astype(int) % 12 + 1
        wy = years + (months >= 10).astype(int)
        return f"(WY {int(wy.min())}-{int(wy.max())})"
    except Exception:
        return None


def _paired_finite(obs: np.ndarray, sim: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Drop indices where either obs or sim is NaN/inf."""
    mask = np.isfinite(obs) & np.isfinite(sim)
    return obs[mask], sim[mask]


def _r2(obs: np.ndarray, sim: np.ndarray) -> float:
    if obs.size < 2:
        return float("nan")
    with np.errstate(invalid="ignore"):
        c = np.corrcoef(obs, sim)[0, 1]
    return float(c * c) if np.isfinite(c) else float("nan")


def _nse(obs: np.ndarray, sim: np.ndarray) -> float:
    if obs.size < 2:
        return float("nan")
    ss_tot = np.sum((obs - obs.mean()) ** 2)
    if ss_tot <= 0:
        return float("nan")
    ss_res = np.sum((sim - obs) ** 2)
    return float(1.0 - ss_res / ss_tot)


def _pbias(obs: np.ndarray, sim: np.ndarray) -> float:
    denom = obs.sum()
    if denom == 0:
        return float("nan")
    return float(100.0 * (sim.sum() - denom) / denom)


def _auto_metric_lines(series_list: list[Series], baseline_idx: int) -> list[str]:
    """Compute R2/NSE/PBIAS for each non-baseline series vs the baseline."""
    if not (0 <= baseline_idx < len(series_list)):
        raise IndexError(
            f"compute_metrics_from={baseline_idx} out of range for {len(series_list)} series"
        )
    base_vals = np.asarray(series_list[baseline_idx].values, dtype=float)
    others = [s for i, s in enumerate(series_list) if i != baseline_idx]
    label_each = len(others) > 1
    lines: list[str] = []
    for s in others:
        sim_vals = np.asarray(s.values, dtype=float)
        if sim_vals.shape != base_vals.shape:
            raise ValueError(
                f"Series '{s.label}' length {sim_vals.shape} != baseline length {base_vals.shape}"
            )
        obs_c, sim_c = _paired_finite(base_vals, sim_vals)
        lines.append(format_metric_line(
            _r2(obs_c, sim_c), _nse(obs_c, sim_c), _pbias(obs_c, sim_c),
            label=s.label if label_each else "",
        ))
    return lines
