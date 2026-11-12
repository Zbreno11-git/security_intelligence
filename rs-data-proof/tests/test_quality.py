import pandas as pd

from src import quality as Q
from src.metrics import hour_bucket


def _hist(levels, rain=None, start="2026-11-12 19:00:00+00:00"):
    ts = pd.date_range(start, periods=len(levels), freq="5min")
    return pd.DataFrame({"ts_utc": ts, "rio_nivel": levels,
                         "chuva_mm": rain if rain is not None else [0.0] * len(levels),
                         "chuva_taxa_max": [0.0] * len(levels)})


def test_river_metrics_deltas_and_rate():
    levels = [1.0 + 0.01 * i for i in range(13)]  # +0.12 m in 60 min
    m = Q.river_metrics(_hist(levels), {"codigo": "X", "official_status": "normal"}, 5)
    assert m["current_river_level"] == 1.12
    assert m["delta_10m"] == 0.02 and m["delta_30m"] == 0.06 and m["delta_1h"] == 0.12
    assert abs(m["rise_rate_per_hour"] - 0.12) < 1e-6


def test_river_metrics_null_with_reason_when_insufficient():
    m = Q.river_metrics(_hist([None, None, 2.0]), {"codigo": "X"}, 5)
    assert m["delta_1h"] is None and "delta_1h" in m["reasons"]
    assert m["rain_24h"] is None and "rain_24h" in m["reasons"]
    m2 = Q.river_metrics(_hist([None] * 5), {"codigo": "X"}, 5)
    assert m2["current_river_level"] is None and "river" in m2["reasons"]


def test_history_quality_detects_gaps_and_flatline():
    h = _hist([2.0] * 10)
    h = h.drop(index=[4, 5]).reset_index(drop=True)
    q = Q.history_quality(h, 5, h["ts_utc"].min() - pd.Timedelta(minutes=5), h["ts_utc"].max())
    assert q["gaps_over_1_5_interval"] == 1
    assert q["rio_nivel_max_identical_run_blocks"] == 8
    assert q["rows"] == 8


def test_rain_window_monotonicity():
    st = pd.DataFrame({c: [1.0, 5.0] for c in ["rain_h001_mm", "rain_h003_mm", "rain_h006_mm",
                                               "rain_h012_mm", "rain_h024_mm", "rain_h048_mm", "rain_h168_mm"]})
    assert Q._rain_monotonic_violations(st) == 0
    st.loc[1, "rain_h024_mm"] = 1.0  # 24h < 12h is impossible
    assert Q._rain_monotonic_violations(st) == 1  # 24h < 12h (48h >= 24h still holds)


def test_flag_counts_and_pct():
    df = pd.DataFrame({"quality_flags": ["a|b", "", "a"]})
    assert Q.flag_counts(df) == {"a": 2, "b": 1}
    assert Q.pct(1, 3) == 33.33 and Q.pct(1, 0) is None


def test_hour_bucket():
    assert hour_bucket("00:01:00") == "00-05"
    assert hour_bucket("11:59:59") == "06-11"
    assert hour_bucket("23:00:00") == "18-23"
    assert hour_bucket(None) is None
