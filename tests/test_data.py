"""WHO LMS table loading + interpolation."""

from __future__ import annotations

import pytest

from growth.data import INDICATOR_INFO, LMSTable, load_table


class TestLoadTable:
    @pytest.mark.parametrize("indicator", ["lhfa", "wfa", "hcfa"])
    @pytest.mark.parametrize("sex", ["boy", "girl"])
    def test_age_table_covers_0_to_730_days(self, indicator, sex):
        t = load_table(indicator, sex)
        assert t.xs[0] == 0
        assert t.xs[-1] == 730
        assert len(t.xs) == 731

    @pytest.mark.parametrize("sex", ["boy", "girl"])
    def test_wfl_table_covers_45_to_110_cm(self, sex):
        t = load_table("wfl", sex)
        assert t.xs[0] == pytest.approx(45.0)
        assert t.xs[-1] == pytest.approx(110.0)
        # 45 .. 110 in 0.1cm steps = 651 rows
        assert len(t.xs) == 651

    def test_lhfa_boys_day_0_median(self):
        """Spot-check against the WHO-published value (LHFA boys day 0: M=49.8842 cm)."""
        t = load_table("lhfa", "boy")
        lms = t.at(0)
        assert lms.M == pytest.approx(49.8842, abs=1e-3)
        assert lms.L == 1.0

    def test_wfa_boys_day_0_median(self):
        """WFA boys day 0 median is published as 3.3464 kg."""
        t = load_table("wfa", "boy")
        lms = t.at(0)
        assert lms.M == pytest.approx(3.3464, abs=1e-3)

    def test_load_table_is_cached(self):
        """load_table uses lru_cache — same call returns same object."""
        t1 = load_table("lhfa", "boy")
        t2 = load_table("lhfa", "boy")
        assert t1 is t2


class TestInterpolation:
    def test_exact_table_x_returns_stored_lms(self):
        table = LMSTable(
            xs=[0.0, 10.0, 20.0],
            L=[1.0, 0.5, 0.0],
            M=[10.0, 20.0, 30.0],
            S=[0.1, 0.2, 0.3],
        )
        lms = table.at(10.0)
        assert lms.L == pytest.approx(0.5)
        assert lms.M == pytest.approx(20.0)
        assert lms.S == pytest.approx(0.2)

    def test_midpoint_is_linear_average(self):
        table = LMSTable(
            xs=[0.0, 10.0],
            L=[1.0, 0.0],
            M=[10.0, 20.0],
            S=[0.1, 0.3],
        )
        lms = table.at(5.0)
        assert lms.L == pytest.approx(0.5)
        assert lms.M == pytest.approx(15.0)
        assert lms.S == pytest.approx(0.2)

    def test_below_range_clamps_to_first(self):
        table = LMSTable(xs=[10.0, 20.0], L=[1.0, 0.5], M=[10.0, 20.0], S=[0.1, 0.2])
        lms = table.at(-5.0)
        assert (lms.L, lms.M, lms.S) == (1.0, 10.0, 0.1)

    def test_above_range_clamps_to_last(self):
        table = LMSTable(xs=[10.0, 20.0], L=[1.0, 0.5], M=[10.0, 20.0], S=[0.1, 0.2])
        lms = table.at(99.0)
        assert (lms.L, lms.M, lms.S) == (0.5, 20.0, 0.2)


class TestIndicatorMetadata:
    def test_all_four_indicators_have_metadata(self):
        assert set(INDICATOR_INFO.keys()) == {"lhfa", "wfa", "hcfa", "wfl"}

    def test_wfl_is_length_axis_others_are_age(self):
        assert INDICATOR_INFO["wfl"]["x_kind"] == "length"
        for ind in ("lhfa", "wfa", "hcfa"):
            assert INDICATOR_INFO[ind]["x_kind"] == "age"
