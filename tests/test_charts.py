"""Chart rendering smoke tests.

These tests don't inspect pixels — they confirm `render_chart` returns a
Figure for every (indicator, sex) combination without raising, both with
no measurements and with a small history."""

from __future__ import annotations

from datetime import date, timedelta

import matplotlib.pyplot as plt
import pytest
from matplotlib.figure import Figure

from growth.charts import render_chart


SAMPLE_MEASUREMENTS = [
    {"taken_on": date(2025, 1, 1),  "weight_kg": 3.5, "length_cm": 50.0, "head_circ_cm": 35.0},
    {"taken_on": date(2025, 4, 1),  "weight_kg": 6.0, "length_cm": 62.0, "head_circ_cm": 40.0},
    {"taken_on": date(2025, 7, 1),  "weight_kg": 8.0, "length_cm": 68.0, "head_circ_cm": 43.0},
    {"taken_on": date(2025, 10, 1), "weight_kg": 9.5, "length_cm": 73.0, "head_circ_cm": 45.0},
]
DOB = date(2025, 1, 1)


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


@pytest.mark.parametrize("indicator", ["lhfa", "wfa", "hcfa", "wfl"])
@pytest.mark.parametrize("sex", ["boy", "girl"])
def test_render_chart_with_measurements(indicator, sex):
    fig = render_chart(indicator, sex, DOB, SAMPLE_MEASUREMENTS)
    assert isinstance(fig, Figure)
    # We expect at least the 5 percentile-curve lines on every chart.
    ax = fig.axes[0]
    assert len(ax.lines) >= 5


@pytest.mark.parametrize("indicator", ["lhfa", "wfa", "hcfa", "wfl"])
def test_render_chart_with_no_measurements(indicator):
    fig = render_chart(indicator, "boy", DOB, [])
    assert isinstance(fig, Figure)


def test_render_chart_ignores_partial_measurement_for_wfl():
    """Weight-for-length needs *both* weight and length. A point with only
    weight should be silently skipped, not crash."""
    partial = [
        {"taken_on": date(2025, 4, 1), "weight_kg": 6.0,
         "length_cm": None, "head_circ_cm": 40.0},
    ]
    fig = render_chart("wfl", "boy", DOB, partial)
    assert isinstance(fig, Figure)


def test_render_chart_drops_out_of_range_age():
    """Measurements past 24 months should not crash; they're just dropped."""
    too_old = [
        {"taken_on": DOB + timedelta(days=900),
         "weight_kg": 14.0, "length_cm": 90.0, "head_circ_cm": 48.0},
    ]
    fig = render_chart("wfa", "boy", DOB, too_old)
    assert isinstance(fig, Figure)


def test_render_chart_handles_negative_age():
    """A measurement before DOB shouldn't crash (defensive)."""
    pre = [
        {"taken_on": DOB - timedelta(days=10),
         "weight_kg": 3.0, "length_cm": 49.0, "head_circ_cm": 34.0},
    ]
    fig = render_chart("lhfa", "girl", DOB, pre)
    assert isinstance(fig, Figure)
