"""Quality layer: measures, never silently fixes."""
from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd


def pct(n: float, d: float) -> float | None:
    return round(100.0 * n / d, 2) if d else None


# ============================================================ Defesa Civil
def defesa_civil_quality(st: pd.DataFrame) -> dict:
    n = len(st)
    river = st[st["has_river_sensor"]]
    rain = st[st["has_rain_sensor"]]
    status_counts = st["official_status"].value_counts().to_dict()
    fresh_counts = st["freshness"].value_counts().to_dict()
    return {
        "total_stations": n,
        "station_types": st["type"].value_counts().to_dict(),
        "stations_with_river_sensor": int(len(river)),
        "stations_with_river_level": int(st["has_river_value"].sum()),
        "stations_with_rain_sensor": int(len(rain)),
        "stations_with_rain": int(st["has_rain_value"].sum()),
        "stations_with_lat_lon": int((st["latitude"].notna() & st["longitude"].notna()).sum()),
        "maintenance_count": int((st["maintenance"] == True).sum()),  # noqa: E712
        "maintenance_percentage": pct((st["maintenance"] == True).sum(), n),  # noqa: E712
        "freshness_counts": fresh_counts,
        "stale_station_count": int(fresh_counts.get("stale", 0)),
        "stale_station_percentage": pct(fresh_counts.get("stale", 0), n),
        "age_minutes_median": float(st["age_minutes"].median()),
        "age_minutes_p95": float(st["age_minutes"].quantile(0.95)),
        "age_minutes_max": float(st["age_minutes"].max()),
        "river_level_missing_pct": pct(river["rio_nivel_m"].isna().sum(), len(river)),
        "rain_1h_missing_pct": pct(rain["rain_h001_mm"].isna().sum(), len(rain)),
        "rain_24h_missing_pct": pct(rain["rain_h024_mm"].isna().sum(), len(rain)),
        "temperature_missing_pct": pct(st["temperatura_c"].isna().sum(), n),
        "non_homologated_river_count": int((st["river_homologated"] == False).sum()),  # noqa: E712
        "non_homologated_rain_count": int((st["rain_homologated"] == False).sum()),  # noqa: E712
        "non_homologated_temp_count": int((st["temp_homologated"] == False).sum()),  # noqa: E712
        "official_status_counts": {
            "normal": int(status_counts.get("normal", 0)),
            "attention": int(status_counts.get("attention", 0)),
            "alert": int(status_counts.get("alert", 0)),
            "flood": int(status_counts.get("flood", 0)),
            "unavailable": int(status_counts.get("unavailable", 0)),
            "no_threshold": int(status_counts.get("no_threshold", 0)),
            "no_river_alarm_data": int(status_counts.get("no_river_alarm_data", 0)),
        },
        "technical_data_confidence_distribution": st["technical_data_confidence"].value_counts().sort_index(ascending=False).to_dict(),
        "duplicate_station_codes": int(st["codigo"].duplicated().sum()),
        "rain_negative_values": int((st[[c for c in st.columns if c.startswith("rain_h") or c.startswith("rain_min")]] < 0).sum().sum()),
        "rain_window_monotonic_violations": int(_rain_monotonic_violations(st)),
        "missing_rio_nome": int(river["rio_nome"].isna().sum()),
        "missing_altitude": int(st["altitude"].isna().sum()),
    }


def _rain_monotonic_violations(st: pd.DataFrame) -> int:
    """Accumulated rain over a longer window must be >= the shorter window."""
    cols = ["rain_h001_mm", "rain_h003_mm", "rain_h006_mm", "rain_h012_mm",
            "rain_h024_mm", "rain_h048_mm", "rain_h168_mm"]
    m = st[cols].to_numpy(dtype=float)
    viol = 0
    for i in range(len(cols) - 1):
        a, b = m[:, i], m[:, i + 1]
        ok = np.isnan(a) | np.isnan(b) | (b + 1e-6 >= a)
        viol += int((~ok).sum())
    return viol


def _value_at(h: pd.DataFrame, ts, col: str):
    row = h.loc[h["ts_utc"] == ts, col]
    return None if row.empty or pd.isna(row.iloc[0]) else float(row.iloc[0])


def history_quality(h: pd.DataFrame, interval_min: int, window_start, window_end) -> dict:
    expected = int((window_end - window_start).total_seconds() // (interval_min * 60))
    nulls = {c: (pct(h[c].isna().sum(), len(h)) if c in h else None) for c in
             ["rio_nivel", "chuva_mm", "temp_media", "umid_rel", "pres_atmos"]}
    diffs = h["ts_utc"].diff().dt.total_seconds().div(60).dropna()
    gaps = int((diffs > interval_min * 1.5).sum())
    run = _max_flat_run(h["rio_nivel"])
    return {
        "rows": int(len(h)),
        "expected_blocks_approx": expected,
        "completeness_pct": pct(len(h), expected),
        "first_ts_utc": str(h["ts_utc"].min()) if len(h) else None,
        "last_ts_utc": str(h["ts_utc"].max()) if len(h) else None,
        "gaps_over_1_5_interval": gaps,
        "duplicate_ts": int(h["ts_utc"].duplicated().sum()),
        "null_pct": nulls,
        "rio_nivel_max_identical_run_blocks": run,
        "rio_nivel_max_identical_run_hours": round(run * interval_min / 60, 2) if run else 0,
        "rio_nivel_jumps_gt_0_5m_per_block": int((h["rio_nivel"].diff().abs() > 0.5).sum()),
        "negative_rain_blocks": int((h["chuva_mm"] < 0).sum()),
    }


def _max_flat_run(s: pd.Series) -> int:
    best = cur = 0
    prev = object()
    for x in s:
        if pd.notna(x) and x == prev:
            cur += 1
        else:
            cur = 1 if pd.notna(x) else 0
        prev = x
        best = max(best, cur)
    return best


def river_metrics(h: pd.DataFrame, station: dict, interval_min: int) -> dict:
    """Observational metrics only. NULL + reason when data is insufficient."""
    out: dict = {"codigo": station["codigo"], "reasons": {}}
    valid = h.dropna(subset=["rio_nivel"])
    if valid.empty:
        for k in ["current_river_level", "delta_10m", "delta_30m", "delta_1h", "rise_rate_per_hour",
                  "max_rise_1h_in_window"]:
            out[k] = None
        out["reasons"]["river"] = "no non-null rio_nivel in window (station may have no river sensor)"
    else:
        last = valid.iloc[-1]
        out["current_river_level"] = float(last["rio_nivel"])
        out["last_river_ts_utc"] = str(last["ts_utc"])
        for label, mins in (("delta_10m", 10), ("delta_30m", 30), ("delta_1h", 60)):
            prev = _value_at(h, last["ts_utc"] - pd.Timedelta(minutes=mins), "rio_nivel")
            out[label] = round(out["current_river_level"] - prev, 3) if prev is not None else None
            if prev is None:
                out["reasons"][label] = f"no reading exactly {mins} min before last valid reading"
        last_hour = valid[valid["ts_utc"] > last["ts_utc"] - pd.Timedelta(minutes=60)]
        if len(last_hour) >= 3:
            x = (last_hour["ts_utc"] - last_hour["ts_utc"].iloc[0]).dt.total_seconds() / 3600
            out["rise_rate_per_hour"] = round(float(np.polyfit(x, last_hour["rio_nivel"], 1)[0]), 4)
        else:
            out["rise_rate_per_hour"] = None
            out["reasons"]["rise_rate_per_hour"] = "fewer than 3 valid readings in last hour"
        s = valid.set_index("ts_utc")["rio_nivel"]
        lag = s.shift(freq=pd.Timedelta(minutes=60))
        rise = (s - lag.reindex(s.index)).dropna()
        out["max_rise_1h_in_window"] = round(float(rise.max()), 3) if len(rise) else None
        out["max_rise_1h_at_utc"] = str(rise.idxmax()) if len(rise) else None
        out["range_in_window_m"] = round(float(s.max() - s.min()), 3)
    last_ts = h["ts_utc"].max() if len(h) else None
    for label, mins in (("rain_30m", 30), ("rain_1h", 60), ("rain_3h", 180), ("rain_24h", 1440)):
        if last_ts is None:
            out[label] = None
            continue
        w = h[h["ts_utc"] > last_ts - pd.Timedelta(minutes=mins)]
        exp = mins // interval_min
        got = int(w["chuva_mm"].notna().sum())
        if got < 0.8 * exp:
            out[label] = None
            out["reasons"][label] = f"only {got}/{exp} non-null rain blocks (<80%)"
        else:
            out[label] = round(float(w["chuva_mm"].sum()), 2)
    out["max_rain_rate_mm_h_24h"] = (float(h["chuva_taxa_max"].max()) if h["chuva_taxa_max"].notna().any() else None)
    out["official_flood_status"] = station.get("official_status")
    out["data_freshness"] = station.get("freshness")
    out["technical_data_confidence"] = station.get("technical_data_confidence")
    out["tags_rain_24h_mm"] = station.get("rain_h024_mm")
    out["tags_rain_1h_mm"] = station.get("rain_h001_mm")
    return out


# ===================================================================== SSP
def schema_profile(df: pd.DataFrame, columns: list[str], max_samples: int = 5,
                   redact: set[str] = frozenset()) -> pd.DataFrame:
    rows = []
    n = len(df)
    for c in columns:
        s = df[c]
        empty = s.isna() | (s.astype(str).str.strip() == "")
        nn = s[~empty]
        if c in redact:
            samples = "[omitted: minimization]"
        else:
            samples = ", ".join(map(str, nn.value_counts().head(max_samples).index.tolist()))
        rows.append({
            "column": c,
            "dtype_inferred": _infer_dtype(nn),
            "null_count": int(empty.sum()),
            "null_pct": pct(int(empty.sum()), n),
            "unique_count": int(nn.nunique()),
            "sample_values": samples[:160],
        })
    return pd.DataFrame(rows)


def _infer_dtype(s: pd.Series) -> str:
    if s.empty:
        return "empty"
    sample = s.astype(str).head(5000)
    if sample.str.fullmatch(r"-?\d+").all():
        return "integer"
    if sample.str.fullmatch(r"-?\d+([.,]\d+)?").all():
        return "decimal"
    if sample.str.fullmatch(r"\d{2}/\d{2}/\d{4}").all():
        return "date(DD/MM/YYYY)"
    if sample.str.fullmatch(r"\d{2}:\d{2}:\d{2}").all():
        return "time(HH:MM:SS)"
    return "text"


def flag_counts(df: pd.DataFrame) -> dict:
    c = Counter(f for s in df["quality_flags"] for f in s.split("|") if f)
    return dict(sorted(c.items(), key=lambda kv: -kv[1]))


def ssp_quality(df: pd.DataFrame, vdf: pd.DataFrame, raw_dup_full: int) -> dict:
    n = len(df)
    biz_cols = ["occurrence_date_raw", "occurrence_time_raw", "fact_group", "category_raw",
                "fact_type", "municipality_raw", "place_type", "neighborhood_raw",
                "victim_count", "victim_age", "victim_sex", "victim_race"]
    dup_wo_id = int(df.duplicated(subset=biz_cols, keep="first").sum())
    times = df["occurrence_time"].dropna()
    on_hour = times.str.endswith(":00:00").sum()
    neigh_raw_u = df["neighborhood_raw"].nunique()
    neigh_norm_u = df["neighborhood"].nunique()
    sex = vdf["victim_sex"]
    race = vdf["victim_race"]
    return {
        "total_rows": n,
        "duplicate_full_rows_raw": raw_dup_full,
        "duplicate_rows_ignoring_sequence_id": dup_wo_id,
        "duplicate_rows_ignoring_sequence_id_pct": pct(dup_wo_id, n),
        "municipality_null_pct": pct(df["municipality"].isna().sum(), n),
        "date_null_pct": pct(df["occurrence_date"].isna().sum(), n),
        "time_null_pct": pct(df["occurrence_time"].isna().sum(), n),
        "category_null_pct": pct(df["category"].isna().sum(), n),
        "neighborhood_null_pct": pct(df["neighborhood"].isna().sum(), n),
        "victim_count_zero_pct": pct((df["victim_count"] == 0).sum(), n),
        "victims_total": int(len(vdf)),
        "victim_age_null_pct": pct(vdf["victim_age"].isna().sum(), len(vdf)),
        "victim_sex_null_pct": pct(sex.isna().sum(), len(vdf)),
        "victim_race_null_pct": pct(race.isna().sum(), len(vdf)),
        "victim_race_sem_informacao_pct": pct((race.fillna("").str.upper() == "SEM INFORMAÇÃO").sum()
                                              + (race.fillna("").str.upper() == "SEM INFORMACAO").sum(), len(vdf)),
        "victim_age_126_count": int((vdf["victim_age"] == 126).sum()),
        "municipality_unique_count": int(df["municipality"].nunique()),
        "category_unique_count": int(df["category"].nunique()),
        "category_raw_unique_count": int(df["category_raw"].nunique()),
        "neighborhood_unique_count_raw": int(neigh_raw_u),
        "neighborhood_unique_count_normalized": int(neigh_norm_u),
        "time_on_exact_hour_pct": pct(on_hour, len(times)),
        "time_midnight_0000_or_0001_pct": pct(times.isin(["00:00:00", "00:01:00"]).sum(), len(times)),
        "date_min": str(df["occurrence_date"].min().date()) if df["occurrence_date"].notna().any() else None,
        "date_max": str(df["occurrence_date"].max().date()) if df["occurrence_date"].notna().any() else None,
        "fact_type_values": df["fact_type"].value_counts().to_dict(),
        "fact_group_values": df["fact_group"].value_counts().to_dict(),
        "flag_counts": flag_counts(df),
        "anomalies": {
            "age_negative": int((vdf["age_flag"] == "age_negative").sum()),
            "age_gt_115": int((vdf["age_flag"] == "age_gt_115").sum()),
            "age_non_numeric": int((vdf["age_flag"] == "age_non_numeric").sum()),
            "date_future": int(df["quality_flags"].str.contains("date_future").sum()),
            "date_invalid": int(df["quality_flags"].str.contains("date_invalid").sum()),
            "date_outside_declared_period": int(df["quality_flags"].str.contains("date_outside_declared_period").sum()),
            "time_invalid": int(df["quality_flags"].str.contains("time_invalid").sum()),
            "municipality_empty": int(df["quality_flags"].str.contains("municipality_empty").sum()),
            "category_empty": int(df["quality_flags"].str.contains("category_empty").sum()),
            "victim_count_missing": int(df["quality_flags"].str.contains("victim_count_missing").sum()),
            "victim_count_mismatch": int(df["quality_flags"].str.contains("victim_count_mismatch").sum()),
        },
    }
