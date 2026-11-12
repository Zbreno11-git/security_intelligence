"""Derived metrics, cross-validation and DuckDB analytical queries."""
from __future__ import annotations

import logging
import re
from pathlib import Path

import duckdb
import openpyxl
import pandas as pd

from .normalize_ssp import fold
from .quality import pct

log = logging.getLogger("metrics")

WEEKDAYS_PT = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
HOUR_BUCKETS = [(0, 5, "00-05"), (6, 11, "06-11"), (12, 17, "12-17"), (18, 23, "18-23")]
NEIGHBORHOOD_MIN_COVERAGE_PCT = 70.0


def hour_bucket(t: str | None) -> str | None:
    if not t:
        return None
    h = int(t[:2])
    for lo, hi, label in HOUR_BUCKETS:
        if lo <= h <= hi:
            return label
    return None


def municipality_metrics(df: pd.DataFrame, mun: str) -> dict:
    d = df[df["municipality"] == mun]
    n = len(d)
    if n == 0:
        return {"municipality": mun, "occurrences_total": 0}
    by_month = d["occurrence_date"].dt.to_period("M").astype(str).value_counts().sort_index()
    wd = d["occurrence_date"].dt.weekday.map(lambda i: WEEKDAYS_PT[i]).value_counts().reindex(WEEKDAYS_PT, fill_value=0)
    hb = d["occurrence_time"].map(hour_bucket).value_counts().reindex([b[2] for b in HOUR_BUCKETS], fill_value=0)
    neigh_cov = pct(d["neighborhood"].notna().sum(), n)
    out = {
        "municipality": mun,
        "occurrences_total": int(n),
        "share_of_state_pct": pct(n, len(df)),
        "state_rank_by_volume": int(df["municipality"].value_counts().rank(ascending=False, method="min")[mun]),
        "occurrences_by_month": by_month.to_dict(),
        "monthly_mean": round(float(by_month.mean()), 1),
        "monthly_min": int(by_month.min()),
        "monthly_max": int(by_month.max()),
        "occurrences_by_category_top10": d["category"].value_counts().head(10).to_dict(),
        "occurrences_by_group": d["fact_group"].value_counts().to_dict(),
        "occurrences_by_place_type": d["place_type"].value_counts().to_dict(),
        "occurrences_by_weekday": wd.to_dict(),
        "occurrences_by_hour_bucket": hb.to_dict(),
        "time_on_exact_hour_pct": pct(d["occurrence_time"].fillna("").str.endswith(":00:00").sum(), n),
        "neighborhood_coverage_pct": neigh_cov,
        "time_coverage_pct": pct(d["occurrence_time"].notna().sum(), n),
        "category_coverage_pct": pct(d["category"].notna().sum(), n),
        "victim_sex_known_pct_of_occurrences_with_victim": pct(
            d.loc[d["victim_count"] > 0, "victim_sex"].notna().sum(), (d["victim_count"] > 0).sum()),
        "neighborhood_unique_raw": int(d["neighborhood_raw"].nunique()),
        "neighborhood_unique_normalized": int(d["neighborhood"].nunique()),
        "flag_counts": {},
    }
    if neigh_cov is not None and neigh_cov >= NEIGHBORHOOD_MIN_COVERAGE_PCT:
        out["occurrences_by_neighborhood_top10"] = d["neighborhood"].value_counts().head(10).to_dict()
    else:
        out["occurrences_by_neighborhood_top10"] = None
        out["neighborhood_note"] = f"coverage {neigh_cov}% < {NEIGHBORHOOD_MIN_COVERAGE_PCT}% threshold"
    from collections import Counter
    out["flag_counts"] = dict(Counter(f for s in d["quality_flags"] for f in s.split("|") if f))
    # Year-to-date seasonality: last full month vs mean of previous months
    if len(by_month) >= 3:
        last = by_month.iloc[-1]
        prev_mean = by_month.iloc[:-1].mean()
        out["last_month_vs_prev_mean_pct"] = round(100 * (last - prev_mean) / prev_mean, 1)
    return out


def municipality_monthly_safety(df: pd.DataFrame) -> pd.DataFrame:
    d = df.assign(month=df["occurrence_date"].dt.to_period("M").astype(str))
    g = d.groupby(["municipality", "month"])
    base = g.size().rename("registered_occurrences").to_frame()
    top = (d.groupby(["municipality", "month", "category"]).size().rename("n").reset_index()
           .sort_values(["municipality", "month", "n"], ascending=[True, True, False])
           .drop_duplicates(["municipality", "month"]).set_index(["municipality", "month"]))
    base["top_category"] = top["category"]
    base["top_category_count"] = top["n"]
    base["neighborhood_coverage_pct"] = g["neighborhood"].apply(lambda s: round(100 * s.notna().mean(), 2))
    base["time_coverage_pct"] = g["occurrence_time"].apply(lambda s: round(100 * s.notna().mean(), 2))
    base["flagged_rows"] = g["quality_flags"].apply(lambda s: int((s.str.replace("neighborhood_empty", "").str.strip("|") != "").sum()))
    return base.reset_index()


def municipality_summary(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("municipality")
    out = pd.DataFrame({
        "registered_occurrences": g.size(),
        "months_covered": g["occurrence_date"].apply(lambda s: s.dt.to_period("M").nunique()),
        "neighborhood_coverage_pct": g["neighborhood"].apply(lambda s: round(100 * s.notna().mean(), 2)),
        "time_coverage_pct": g["occurrence_time"].apply(lambda s: round(100 * s.notna().mean(), 2)),
        "distinct_categories": g["category"].nunique(),
    })
    out["rank_by_volume"] = out["registered_occurrences"].rank(ascending=False, method="min").astype(int)
    return out.reset_index().sort_values("rank_by_volume")


# ------------------------------------------------- cross-validation vs indicators
# Heuristic mapping: microdata 'Tipo Enquadramento' -> aggregated indicator column.
# This is OUR approximation; the SSP's official aggregation rule is not published
# alongside the microdata. Differences are reported, not forced to zero.
INDICATOR_RULES = [  # (label, indicator column, rule over normalized category)
    ("HOMICIDIO DOLOSO", "HOMICIDIO DOLOSO", lambda c: c.startswith("HOMICIDIO DOLOSO")),
    ("LATROCINIO", "LATROCINIO", lambda c: "ROUBO" in c and "MORTE" in c),
    ("FURTOS (any category containing FURTO)", "FURTOS", lambda c: "FURTO" in c),
    ("ABIGEATO", "ABIGEATO", lambda c: "ABIGEATO" in c),
    ("FURTO DE VEICULO", "FURTO DE VEICULO", lambda c: c.startswith("FURTO DE VEICULO") or c.startswith("FURTO VEICULO")),
    ("ROUBOS (any category containing ROUBO)", "ROUBOS", lambda c: "ROUBO" in c),
    ("ROUBO DE VEICULO", "ROUBO DE VEICULO", lambda c: c.startswith("ROUBO DE VEICULO")),
    ("ESTELIONATO (all ESTELIONATO*)", "ESTELIONATO", lambda c: c.startswith("ESTELIONATO")),
    ("ESTELIONATO (excl. FRAUDE ELETRONICA) [hypothesis]", "ESTELIONATO",
     lambda c: c.startswith("ESTELIONATO") and "FRAUDE ELETRONICA" not in c),
    ("ENTORPECENTES - POSSE", "ENTORPECENTES - POSSE", lambda c: c.startswith("ENTORPECENTES") and "POSSE" in c),
    ("ENTORPECENTES - TRAFICO", "ENTORPECENTES - TRAFICO", lambda c: c.startswith("ENTORPECENTES") and "TRAFICO" in c),
]
MONTH_SHEETS = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]


def read_indicator_months(xlsx: Path, n_months: int) -> pd.DataFrame:
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    frames = []
    for i, sheet in enumerate(MONTH_SHEETS[:n_months], start=1):
        if sheet not in wb.sheetnames:
            continue
        rows = list(wb[sheet].iter_rows(values_only=True))
        hi = next(i2 for i2, r in enumerate(rows) if r and r[0] and fold(str(r[0])).startswith("MUNICIPIOS"))
        header = [fold(str(h)) if h else "" for h in rows[hi]]
        # Some month sheets carry ~16k trailing empty columns (observed JUL-SET 2026).
        while header and header[-1] == "":
            header.pop()
        body = [r[: len(header)] for r in rows[hi + 1:] if r and r[0] and isinstance(r[1], (int, float))]
        f = pd.DataFrame(body, columns=header)
        f = f.rename(columns={header[0]: "municipality"})
        f["municipality"] = f["municipality"].map(fold)
        f["month"] = i
        frames.append(f)
    df = pd.concat(frames, ignore_index=True)
    df = df[~df["municipality"].str.startswith("TOTAL")]
    return df


def cross_validate(df: pd.DataFrame, xlsx: Path, municipalities: tuple[str, ...]) -> dict:
    months = sorted(df["occurrence_date"].dt.month.dropna().unique().astype(int))
    n_months = max(months)
    ind = read_indicator_months(xlsx, n_months)
    ind_cols = {c: c for c in ind.columns}
    results = []
    cats = df["category"].fillna("")
    for label, indicator, rule in INDICATOR_RULES:
        col = next((c for c in ind_cols if fold(c).rstrip("*").strip() == indicator), None)
        if col is None:
            continue
        mask = cats.map(rule)
        for scope in ("RS (state)",) + municipalities:
            if scope == "RS (state)":
                micro = int(mask.sum())
                agg = int(pd.to_numeric(ind[col], errors="coerce").sum())
            else:
                micro = int((mask & (df["municipality"] == scope)).sum())
                agg = int(pd.to_numeric(ind.loc[ind["municipality"] == scope, col], errors="coerce").sum())
            results.append({
                "mapping": label, "indicator": indicator, "scope": scope, "period_months": f"1-{n_months}",
                "microdata_count": micro, "indicator_count": agg, "diff": micro - agg,
                "diff_pct": round(100 * (micro - agg) / agg, 1) if agg else None,
            })
    return {"months_compared": n_months, "rows": results,
            "municipalities_in_indicator": int(ind["municipality"].nunique())}


# --------------------------------------------------------------- DuckDB
DUCKDB_QUERIES = {
    "DC — estações em atenção/alerta/inundação": """
        SELECT codigo, name_general, bacia, official_status, rio_nivel_m, freshness
        FROM stations WHERE official_status IN ('attention','alert','flood') ORDER BY official_status_code DESC""",
    "DC — estações stale, sem leitura recente ou em manutenção": """
        SELECT codigo, name_general, freshness, age_minutes, maintenance, quality_flags
        FROM stations WHERE freshness <> 'fresh' OR maintenance ORDER BY age_minutes DESC NULLS LAST LIMIT 20""",
    "DC — maior subida (máx. variação em 1h) nas séries históricas coletadas": """
        WITH h AS (SELECT codigo, ts_utc, rio_nivel,
                     rio_nivel - LAG(rio_nivel, 12) OVER  -- 12 blocos de 5 min = 1h (assume série sem lacunas)
                      (PARTITION BY codigo ORDER BY ts_utc) AS d1h
                   FROM history WHERE rio_nivel IS NOT NULL)
        SELECT codigo, MAX(d1h) AS max_rise_1h_m, MIN(rio_nivel) AS min_m, MAX(rio_nivel) AS max_m
        FROM h GROUP BY codigo ORDER BY max_rise_1h_m DESC NULLS LAST""",
    "DC — maior subida de nível (tendência atual, todas as estações)": """
        SELECT codigo, name_general, rio_nivel_m, rio_nivel_tendencia_m, official_status
        FROM stations WHERE rio_nivel_tendencia_m IS NOT NULL ORDER BY rio_nivel_tendencia_m DESC LIMIT 5""",
    "DC — mais chuva nas últimas 24h": """
        SELECT codigo, name_general, regiao, rain_h024_mm, rain_h001_mm, rain_homologated
        FROM stations WHERE rain_h024_mm IS NOT NULL ORDER BY rain_h024_mm DESC LIMIT 10""",
    "DC — estações a até 40 km de Gramado/Canela": """
        SELECT codigo, name_general, bacia, dist_serra_km, has_river_value, has_rain_value,
               official_status, freshness, technical_data_confidence
        FROM stations WHERE dist_serra_km <= 40 ORDER BY dist_serra_km""",
    "SSP — ocorrências registradas em Gramado e Canela no período": """
        SELECT municipality, COUNT(*) AS ocorrencias_registradas, MIN(occurrence_date) AS de, MAX(occurrence_date) AS ate
        FROM occ WHERE municipality IN ('GRAMADO','CANELA') GROUP BY 1 ORDER BY 1""",
    "SSP — 10 categorias mais frequentes em Gramado": """
        SELECT category, COUNT(*) AS n FROM occ WHERE municipality = 'GRAMADO'
        GROUP BY 1 ORDER BY n DESC LIMIT 10""",
    "SSP — distribuição mensal (Gramado e Canela)": """
        SELECT strftime(occurrence_date, '%Y-%m') AS mes,
               SUM(CASE WHEN municipality='GRAMADO' THEN 1 ELSE 0 END) AS gramado,
               SUM(CASE WHEN municipality='CANELA' THEN 1 ELSE 0 END) AS canela
        FROM occ WHERE municipality IN ('GRAMADO','CANELA') GROUP BY 1 ORDER BY 1""",
    "SSP — cobertura de bairro e horário (Gramado, Canela, demais municípios)": """
        SELECT COALESCE(CASE WHEN municipality IN ('GRAMADO','CANELA') THEN municipality END, 'DEMAIS MUNICÍPIOS') AS escopo,
               ROUND(100.0*AVG(CASE WHEN neighborhood IS NOT NULL THEN 1 ELSE 0 END),2) AS bairro_pct,
               ROUND(100.0*AVG(CASE WHEN occurrence_time IS NOT NULL THEN 1 ELSE 0 END),2) AS hora_pct,
               ROUND(100.0*AVG(CASE WHEN occurrence_time LIKE '%:00:00' THEN 1 ELSE 0 END),2) AS hora_cheia_pct
        FROM occ GROUP BY ROLLUP(1) HAVING escopo IS NOT NULL ORDER BY 1""",
    "SSP — bairros com maior volume de registros (Gramado)": """
        SELECT neighborhood, COUNT(*) AS n FROM occ WHERE municipality='GRAMADO' AND neighborhood IS NOT NULL
        GROUP BY 1 ORDER BY n DESC LIMIT 10""",
    "SSP — bairros com maior volume de registros (Canela)": """
        SELECT neighborhood, COUNT(*) AS n FROM occ WHERE municipality='CANELA' AND neighborhood IS NOT NULL
        GROUP BY 1 ORDER BY n DESC LIMIT 10""",
}


def run_duckdb(curated: Path) -> list[dict]:
    con = duckdb.connect()
    con.execute(f"CREATE VIEW stations AS SELECT * FROM read_parquet('{curated / 'defesa_civil_stations.parquet'}')")
    con.execute(f"CREATE VIEW history AS SELECT * FROM read_parquet('{curated / 'defesa_civil_history.parquet'}')")
    con.execute(f"CREATE VIEW occ AS SELECT * FROM read_parquet('{curated / 'ssp_occurrences.parquet'}')")
    out = []
    for title, sql in DUCKDB_QUERIES.items():
        try:
            res = con.execute(sql).fetchdf()
            out.append({"title": title, "sql": re.sub(r"\n\s+", "\n", sql.strip()), "result": res, "error": None})
        except Exception as exc:  # report, do not hide
            out.append({"title": title, "sql": sql.strip(), "result": None, "error": str(exc)})
            log.error("duckdb.query_failed title=%s error=%s", title, exc)
    return out
