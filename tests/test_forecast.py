import numpy as np

from pipeline import forecast


def test_prior_year_means_use_only_earlier_years():
    years = np.array([2020, 2020, 2021, 2021, 2022])
    woy = np.array([10, 11, 10, 11, 10])
    vals = np.array([1.0, 3.0, 5.0, 7.0, 100.0])
    out = forecast._prior_year_means(vals, years, woy, window=0)
    assert np.isnan(out[0]) and np.isnan(out[1])      # first year: no history
    assert out[2] == 1.0 and out[3] == 3.0            # 2021 sees only 2020
    assert out[4] == 3.0                              # 2022 sees mean of 2020 and 2021 (1, 5), not its own 100


def test_window_widens_across_weeks():
    years = np.array([2020, 2020, 2021])
    woy = np.array([10, 12, 11])
    vals = np.array([2.0, 4.0, 0.0])
    out = forecast._prior_year_means(vals, years, woy, window=1)
    assert out[2] == 3.0                              # week 11 +/- 1 in 2020 -> weeks 10 and 12
