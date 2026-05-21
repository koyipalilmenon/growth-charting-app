"""Load WHO LMS reference tables and interpolate L/M/S at a given x value.

Indicators and their x-axis:
  - lhfa  length-for-age          x = age in days     (0..730)
  - wfa   weight-for-age          x = age in days     (0..730)
  - hcfa  head-circumference-age  x = age in days     (0..730)
  - wfl   weight-for-length       x = length in cm    (45.0..110.0, step 0.1)
"""

from __future__ import annotations

import csv
from bisect import bisect_left
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from .lms import LMS

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "who"

Sex = Literal["boy", "girl"]
Indicator = Literal["lhfa", "wfa", "hcfa", "wfl"]

INDICATOR_INFO: dict[Indicator, dict] = {
    "lhfa": {"title": "Length-for-age", "y_label": "Length (cm)",
             "x_label": "Age (months)", "x_kind": "age"},
    "wfa":  {"title": "Weight-for-age", "y_label": "Weight (kg)",
             "x_label": "Age (months)", "x_kind": "age"},
    "hcfa": {"title": "Head circumference-for-age", "y_label": "Head circumference (cm)",
             "x_label": "Age (months)", "x_kind": "age"},
    "wfl":  {"title": "Weight-for-length", "y_label": "Weight (kg)",
             "x_label": "Length (cm)", "x_kind": "length"},
}

DAYS_PER_MONTH = 30.4375  # average, used for age-in-months <-> days conversion


@dataclass(frozen=True)
class LMSTable:
    xs: list[float]
    L: list[float]
    M: list[float]
    S: list[float]

    def at(self, x: float) -> LMS:
        """Linearly interpolate L, M, S at x (clamped to the table range)."""
        if x <= self.xs[0]:
            return LMS(self.L[0], self.M[0], self.S[0])
        if x >= self.xs[-1]:
            return LMS(self.L[-1], self.M[-1], self.S[-1])
        i = bisect_left(self.xs, x)
        x0, x1 = self.xs[i - 1], self.xs[i]
        t = (x - x0) / (x1 - x0)
        return LMS(
            self.L[i - 1] + t * (self.L[i] - self.L[i - 1]),
            self.M[i - 1] + t * (self.M[i] - self.M[i - 1]),
            self.S[i - 1] + t * (self.S[i] - self.S[i - 1]),
        )


@lru_cache(maxsize=None)
def load_table(indicator: Indicator, sex: Sex) -> LMSTable:
    sex_token = "boys" if sex == "boy" else "girls"
    path = DATA_DIR / f"{indicator}_{sex_token}.csv"
    xs: list[float] = []
    Ls: list[float] = []
    Ms: list[float] = []
    Ss: list[float] = []
    with path.open() as f:
        reader = csv.reader(f)
        next(reader)  # header
        for row in reader:
            xs.append(float(row[0]))
            Ls.append(float(row[1]))
            Ms.append(float(row[2]))
            Ss.append(float(row[3]))
    return LMSTable(xs, Ls, Ms, Ss)
