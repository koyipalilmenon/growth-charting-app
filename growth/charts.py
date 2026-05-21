"""Render a WHO growth chart with reference percentile curves and the
child's measurement points overlaid."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import matplotlib.pyplot as plt
from matplotlib.figure import Figure

from .data import DAYS_PER_MONTH, INDICATOR_INFO, Indicator, Sex, load_table
from .lms import LMS, measurement_at_zscore, percentile, zscore

# Percentile curves to draw. Each is a (label, z-score) pair.
# These are the standard WHO percentile bands.
PERCENTILE_CURVES = [
    ("3rd",  -1.881),
    ("15th", -1.036),
    ("50th",  0.000),
    ("85th",  1.036),
    ("97th",  1.881),
]

# Heavier styling for the median; lighter for outer bands.
CURVE_STYLES = {
    "3rd":  {"color": "#d62728", "linestyle": "--", "linewidth": 1.0, "alpha": 0.7},
    "15th": {"color": "#ff7f0e", "linestyle": "-",  "linewidth": 1.0, "alpha": 0.7},
    "50th": {"color": "#2ca02c", "linestyle": "-",  "linewidth": 1.8, "alpha": 0.9},
    "85th": {"color": "#ff7f0e", "linestyle": "-",  "linewidth": 1.0, "alpha": 0.7},
    "97th": {"color": "#d62728", "linestyle": "--", "linewidth": 1.0, "alpha": 0.7},
}


@dataclass
class PlotPoint:
    x: float       # months for age-based, length-cm for WfL
    y: float       # the measurement
    label: str     # e.g. "2026-04-01"
    z: float
    pct: float
    is_latest: bool


def _build_points_age(
    indicator: Indicator,
    sex: Sex,
    dob: date,
    measurements: list[dict],
) -> list[PlotPoint]:
    """Build chart points for an age-based indicator from a list of dicts
    with keys taken_on (date), and the relevant measurement field."""
    field = {"lhfa": "length_cm", "wfa": "weight_kg", "hcfa": "head_circ_cm"}[indicator]
    table = load_table(indicator, sex)
    points: list[PlotPoint] = []
    valid = [m for m in measurements if m.get(field) is not None]
    for i, m in enumerate(valid):
        age_days = (m["taken_on"] - dob).days
        if age_days < 0 or age_days > 730:
            continue
        lms = table.at(age_days)
        z = zscore(m[field], lms)
        points.append(PlotPoint(
            x=age_days / DAYS_PER_MONTH,
            y=m[field],
            label=m["taken_on"].isoformat(),
            z=z,
            pct=percentile(z),
            is_latest=(i == len(valid) - 1),
        ))
    return points


def _build_points_wfl(
    sex: Sex,
    measurements: list[dict],
) -> list[PlotPoint]:
    """Weight-for-length: x is length, y is weight; one point per measurement
    that has both values."""
    table = load_table("wfl", sex)
    valid = [m for m in measurements
             if m.get("weight_kg") is not None and m.get("length_cm") is not None]
    points: list[PlotPoint] = []
    for i, m in enumerate(valid):
        L_cm = m["length_cm"]
        if L_cm < 45 or L_cm > 110:
            continue
        lms = table.at(L_cm)
        z = zscore(m["weight_kg"], lms)
        points.append(PlotPoint(
            x=L_cm,
            y=m["weight_kg"],
            label=m["taken_on"].isoformat(),
            z=z,
            pct=percentile(z),
            is_latest=(i == len(valid) - 1),
        ))
    return points


def render_chart(
    indicator: Indicator,
    sex: Sex,
    dob: date,
    measurements: list[dict],
) -> Figure:
    info = INDICATOR_INFO[indicator]
    table = load_table(indicator, sex)

    fig, ax = plt.subplots(figsize=(8, 5))

    # X-axis sample points for plotting the curves.
    xs_raw = table.xs
    if info["x_kind"] == "age":
        xs_plot = [x / DAYS_PER_MONTH for x in xs_raw]
    else:
        xs_plot = xs_raw

    # Draw the five percentile curves.
    for label, z in PERCENTILE_CURVES:
        ys = [measurement_at_zscore(z, LMS(table.L[i], table.M[i], table.S[i]))
              for i in range(len(xs_raw))]
        style = CURVE_STYLES[label]
        ax.plot(xs_plot, ys, label=f"{label} pct", **style)

    # Plot the child's points.
    if info["x_kind"] == "age":
        pts = _build_points_age(indicator, sex, dob, measurements)
    else:
        pts = _build_points_wfl(sex, measurements)

    if pts:
        ax.plot(
            [p.x for p in pts], [p.y for p in pts],
            color="#1f77b4", linestyle="-", linewidth=1.2, alpha=0.5, zorder=4,
        )
        for p in pts:
            ax.scatter(
                [p.x], [p.y],
                color="#1f77b4" if not p.is_latest else "#0a3a78",
                s=60 if p.is_latest else 32,
                edgecolor="white", linewidth=1.2, zorder=5,
            )
        latest = pts[-1]
        ax.annotate(
            f"{latest.label}\n{latest.pct:.1f} pct  (z={latest.z:+.2f})",
            xy=(latest.x, latest.y),
            xytext=(8, 8), textcoords="offset points",
            fontsize=8,
            bbox=dict(boxstyle="round,pad=0.3", fc="#fffbe6", ec="#888", lw=0.5),
        )

    ax.set_title(f"{info['title']} — {'Boys' if sex == 'boy' else 'Girls'} (WHO 0–24 months)")
    ax.set_xlabel(info["x_label"])
    ax.set_ylabel(info["y_label"])
    if info["x_kind"] == "age":
        ax.set_xlim(0, 24)
        ax.set_xticks(range(0, 25, 2))
    else:
        ax.set_xlim(45, 110)
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left", fontsize=8, framealpha=0.85)
    fig.tight_layout()
    return fig
