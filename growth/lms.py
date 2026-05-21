"""LMS (Lambda-Mu-Sigma) math for WHO growth standards.

Given a measurement X and the L, M, S parameters at the appropriate x-axis
position (age in days, or length in cm), the z-score is:

    z = ((X / M) ** L - 1) / (L * S)   when L != 0
    z = ln(X / M) / S                  when L == 0

Z-score is then converted to a percentile via the standard normal CDF.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class LMS:
    L: float
    M: float
    S: float


def zscore(measurement: float, lms: LMS) -> float:
    if lms.L == 0:
        return math.log(measurement / lms.M) / lms.S
    return ((measurement / lms.M) ** lms.L - 1) / (lms.L * lms.S)


def percentile(z: float) -> float:
    """Standard-normal CDF, returned as a percentile in [0, 100]."""
    return 100.0 * 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def measurement_at_zscore(z: float, lms: LMS) -> float:
    """Inverse of zscore: the measurement value corresponding to a given z."""
    if lms.L == 0:
        return lms.M * math.exp(z * lms.S)
    return lms.M * (1 + lms.L * lms.S * z) ** (1 / lms.L)
