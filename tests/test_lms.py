"""LMS math: z-score, percentile, and the inverse measurement_at_zscore."""

from __future__ import annotations

import math

import pytest

from growth.lms import LMS, measurement_at_zscore, percentile, zscore


class TestZscore:
    def test_at_median_is_zero(self):
        lms = LMS(L=0.5, M=10.0, S=0.1)
        assert zscore(10.0, lms) == pytest.approx(0.0, abs=1e-12)

    def test_l_zero_uses_log_formula(self):
        lms = LMS(L=0.0, M=10.0, S=0.1)
        # Independently: z = ln(11/10) / 0.1
        expected = math.log(11.0 / 10.0) / 0.1
        assert zscore(11.0, lms) == pytest.approx(expected, abs=1e-12)

    def test_who_boys_wfa_day_0_median(self):
        """WHO boys weight-for-age day 0: L=0.3487, M=3.3464, S=0.14602.
        A baby at the median weight should have z ~= 0."""
        lms = LMS(L=0.3487, M=3.3464, S=0.14602)
        assert zscore(3.3464, lms) == pytest.approx(0.0, abs=1e-6)

    def test_who_boys_wfa_day_0_large_baby(self):
        """A 4.5 kg newborn boy should land at roughly z=2 (~97th percentile)."""
        lms = LMS(L=0.3487, M=3.3464, S=0.14602)
        z = zscore(4.5, lms)
        assert 1.8 < z < 2.4


class TestPercentile:
    def test_zero_z_is_fiftieth(self):
        assert percentile(0.0) == pytest.approx(50.0, abs=1e-9)

    def test_z_1p96_is_about_975th(self):
        # 1.96 is the canonical "97.5%" cutoff for the normal CDF.
        assert percentile(1.96) == pytest.approx(97.5, abs=0.1)

    def test_z_neg_1p96_is_about_25th(self):
        assert percentile(-1.96) == pytest.approx(2.5, abs=0.1)

    def test_who_band_cutoffs(self):
        # WHO percentile bands we draw on the charts:
        assert percentile(-1.881) == pytest.approx(3.0, abs=0.1)
        assert percentile(1.881) == pytest.approx(97.0, abs=0.1)
        assert percentile(-1.036) == pytest.approx(15.0, abs=0.2)
        assert percentile(1.036) == pytest.approx(85.0, abs=0.2)


class TestInverse:
    @pytest.mark.parametrize(
        "lms",
        [
            LMS(L=0.5,    M=10.0,   S=0.1),
            LMS(L=-0.2,   M=50.0,   S=0.05),
            LMS(L=1.0,    M=3.0,    S=0.15),
            LMS(L=0.0,    M=12.0,   S=0.12),  # log-formula branch
        ],
    )
    @pytest.mark.parametrize("z", [-2.0, -1.0, 0.0, 1.0, 2.0])
    def test_inverse_is_consistent(self, lms, z):
        x = measurement_at_zscore(z, lms)
        assert zscore(x, lms) == pytest.approx(z, abs=1e-9)
