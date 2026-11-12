"""RS data proof — end-to-end orchestration.

source -> download/API -> immutable RAW (+sha256 metadata) -> normalization ->
quality checks -> derived metrics -> readable outputs (reports/).

Exit codes: 0 = both sources processed; 2 = partial (one source failed);
1 = nothing usable.
"""
from __future__ import annotations

import json
import logging
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import config
from . import fetch_defesa_civil as fdc
from . import fetch_ssp as fssp
from . import metrics as M
from . import normalize_defesa_civil as ndc
from . import normalize_ssp as nssp
from . import quality as Q
from .http import fetch, make_session, sha256_file

log = logging.getLogger("main")


def setup_logging() -> None:
    config.REPORTS.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s", "%Y-%m-%dT%H:%M:%S%z")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    fh = logging.FileHandler(config.REPORTS / "run.log", mode="w", encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(sh)
    root.addHandler(fh)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def preflight(session) -> list[dict]:
    out = []
    for url in config.PREFLIGHT_URLS:
        t0 = time.monotonic()
        try:
            r = session.get(url, timeout=config.HTTP_TIMEOUT)
            out.append({
                "url": url, "ok": r.status_code == 200, "status_code": r.status_code,
                "content_type": r.headers.get("Content-Type"), "final_url": r.url,
                "redirects": [f"{h.status_code} {h.url}" for h in r.history],
                "bytes": len(r.content), "elapsed_s": round(time.monotonic() - t0, 3),
                "tls_verified": True,
            })
        except Exception as exc:
            out.append({"url": url, "ok": False, "error": f"{type(exc).__name__}: {exc}",
                        "elapsed_s": round(time.monotonic() - t0, 3)})
        log.info("preflight url=%s ok=%s status=%s", url, out[-1]["ok"], out[-1].get("status_code"))
    return out


def jsonable(o):
    if isinstance(o, (pd.Timestamp, datetime)):
        return o.isoformat()
    if isinstance(o, Path):
        return str(o)
    if hasattr(o, "item"):
        return o.item()
    if isinstance(o, pd.DataFrame):
        return o.to_dict(orient="records")
    return str(o)


def dump(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=jsonable))


def stage_defesa_civil(session, run_date: str, R: dict) -> None:
    ctx = fdc.run(session, run_date)
    rec = ctx["tags_record"]
    st, prox = ndc.normalize_stations(ctx["tags_payload"], ctx["collected_at"])
    config.CURATED.mkdir(parents=True, exist_ok=True)
    st.to_parquet(config.CURATED / "defesa_civil_stations.parquet", index=False)
    flagged = st[st["quality_flags"] != ""]
    flagged[["codigo", "name_general", "quality_flags", "age_minutes", "maintenance"]].to_csv(
        config.QUARANTINE / "defesa_civil_flagged_stations.csv", index=False)
    q = Q.defesa_civil_quality(st)
    log.info("defesa_civil.quality stations=%s stale=%s maintenance=%s river_null_pct=%s",
             q["total_stations"], q["stale_station_count"], q["maintenance_count"], q["river_level_missing_pct"])
    hist_ctx = fdc.run_history(session, ctx, st)
    frames, hist_metrics, hist_quality = [], [], {}
    interval_min = int(config.DC_HISTORIC_INTERVAL.split("_")[1]) * (60 if "HOUR" in config.DC_HISTORIC_INTERVAL else 1)
    for res in hist_ctx["results"]:
        if not res["ok"]:
            hist_metrics.append({"codigo": res["codigo"], "error": res["error"]})
            continue
        items = res["payload"]["data"]["historic"]["items"]
        h = ndc.normalize_history(items, config.DC_HISTORIC_INTERVAL, res["record"].saved_to)
        frames.append(h)
        srow = st[st["codigo"] == res["codigo"]].iloc[0].to_dict()
        m = Q.river_metrics(h, srow, interval_min)
        m.update({"selection_reason": res["reason"], "name_general": srow["name_general"],
                  "bacia": srow["bacia"], "rio_nome": srow["rio_nome"],
                  "dist_serra_km": srow["dist_serra_km"], "variables": res["variables"],
                  "bytes": res["record"].content_length, "elapsed_s": res["record"].elapsed_s,
                  "total_count": res["payload"]["data"]["historic"].get("totalCount")})
        start = pd.Timestamp(ndc.parse_station_timestamp(res["variables"]["startDate"].replace(" ", "T")))
        end = pd.Timestamp(ndc.parse_station_timestamp(res["variables"]["endDate"].replace(" ", "T")))
        hist_quality[res["codigo"]] = Q.history_quality(h, interval_min, start, end)
        hist_metrics.append(m)
    hist = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=ndc.HIST_FIELDS)
    hist.to_parquet(config.CURATED / "defesa_civil_history.parquet", index=False)
    serra = st[st["dist_serra_km"] <= config.SERRA_RADIUS_KM].sort_values("dist_serra_km")
    serra[["codigo", "name_general", "bacia", "rio_nome", "dist_gramado_km", "dist_canela_km",
           "has_river_value", "has_rain_value", "rio_nivel_m", "rain_h024_mm", "official_status",
           "freshness", "technical_data_confidence"]].to_csv(config.REPORTS / "serra_stations.csv", index=False)
    R["defesa_civil"] = {
        "status": "ok",
        "fetch": rec.to_dict(),
        "proximaAtualizacaoEm": prox,
        "collected_at_utc": ctx["collected_at"].isoformat(),
        "query_drift": ctx["drift"],
        "quality": q,
        "station_count_vs_documented": {"observed": int(len(st)), "documented": config.DC_EXPECTED_STATIONS},
        "history": {"metrics": hist_metrics, "quality": hist_quality, "limit_probe": hist_ctx["probe"],
                    "rows": int(len(hist))},
        "serra_stations_within_km": config.SERRA_RADIUS_KM,
        "serra_station_count": int(len(serra)),
        "serra_with_river_value": int(serra["has_river_value"].sum()),
        "serra_with_rain_value": int(serra["has_rain_value"].sum()),
        "stations_named_gramado_canela": st[st["name_general"].fillna("").str.upper().str.contains("GRAMADO|CANELA")][
            ["codigo", "name_general", "name_local"]].to_dict(orient="records"),
    }
    R["_frames"]["stations"] = st
    R["_frames"]["history"] = hist


def stage_ssp(session, run_date: str, R: dict) -> None:
    ctx = fssp.run(session, run_date)
    disc = ctx["discovery"]
    member = disc["zip_members"][0]
    csv_path = config.ROOT / member["extracted_to"]
    ingested_at = datetime.now(timezone.utc).isoformat()
    source_version = f"{csv_path.name}|sha256:{disc['download']['sha256'][:12]}"
    t_parse = time.monotonic()
    df, vdf, info = nssp.normalize_file(csv_path, reference_date=datetime.now(timezone.utc).date(),
                                        source_version=source_version, ingested_at=ingested_at)
    parse_seconds = round(time.monotonic() - t_parse, 1)
    df.to_parquet(config.CURATED / "ssp_occurrences.parquet", index=False)
    vdf.to_parquet(config.CURATED / "ssp_victims.parquet", index=False)
    crit = df["quality_flags"].map(lambda s: bool(set(s.split("|")) & nssp.CRITICAL_FLAGS))
    vflag = df["occurrence_id"].isin(vdf.loc[vdf["age_flag"].notna(), "occurrence_id"]) | \
        df["quality_flags"].str.contains("victim_count_missing|victim_count_invalid|victim_count_mismatch")
    quarantine = df[crit | vflag]
    quarantine.drop(columns=["victim_age", "victim_sex", "victim_race"]).to_csv(
        config.QUARANTINE / "ssp_flagged_rows.csv", index=False)
    q = Q.ssp_quality(df, vdf, info["duplicate_full_rows_raw"])
    for k, v in q["anomalies"].items():
        if v:
            log.warning("ssp.quality %s=%s", k, v)
    prof_cols = ["occurrence_id", "occurrence_date_raw", "occurrence_time_raw", "fact_group", "category_raw",
                 "fact_type", "municipality_raw", "place_type", "neighborhood_raw", "victim_count",
                 "victim_age", "victim_sex", "victim_race"]
    profile = Q.schema_profile(df, prof_cols)
    raw_names = info["header_validation"]["observed_first13"]
    profile.insert(0, "raw_column", raw_names)
    mm = {m: M.municipality_metrics(df, m) for m in config.TARGET_MUNICIPALITIES}
    similar = sorted({m for m in df["municipality"].dropna().unique()
                      if any(t in m for t in config.TARGET_MUNICIPALITIES)})
    monthly = M.municipality_monthly_safety(df)
    monthly.to_csv(config.CURATED / "municipality_monthly_safety.csv", index=False)
    summary = M.municipality_summary(df)
    summary.to_csv(config.CURATED / "municipality_metrics.csv", index=False)
    cv = None
    ind = ctx["indicators"]
    if ind and "record" in ind:
        try:
            cv = M.cross_validate(df, config.ROOT / ind["record"]["saved_to"], config.TARGET_MUNICIPALITIES)
        except Exception as exc:
            log.error("ssp.crossval failed error=%s", exc)
            cv = {"error": str(exc)}
    multi = vdf.groupby("occurrence_id").size()
    R["ssp"] = {
        "status": "ok",
        "discovery": {k: disc[k] for k in ("source_page", "chosen", "download", "zip_members")},
        "candidates_mensal": disc["candidates"]["mensal"],
        "parse": info,
        "parse_seconds": parse_seconds,
        "columns_raw": len(info["header_validation"]["observed_first13"]),
        "quality": q,
        "schema_profile": profile,
        "victims": {"occurrences_with_gt1_victim": int((multi > 1).sum()), "max_victims_one_row": int(multi.max())},
        "municipality_metrics": mm,
        "municipality_name_variants_found": similar,
        "top_categories_state": df["category"].value_counts().head(15).to_dict(),
        "cross_validation": cv,
        "indicators": ind,
        "quarantine_rows": int(len(quarantine)),
        "extracted_bytes": int(member["uncompressed_size"]),
    }
    R["_frames"]["occ"] = df


def main() -> int:
    setup_logging()
    started = datetime.now(timezone.utc)
    run_date = started.strftime("%Y-%m-%d")
    log.info("run.start run_date=%s root=%s", run_date, config.ROOT)
    for d in (config.RAW, config.CURATED, config.QUARANTINE, config.REPORTS):
        d.mkdir(parents=True, exist_ok=True)
    session = make_session()
    R: dict = {"_frames": {}, "errors": {}}
    R["preflight"] = preflight(session)
    for name, fn in (("defesa_civil", stage_defesa_civil), ("ssp", stage_ssp)):
        try:
            fn(session, run_date, R)
        except Exception as exc:
            log.error("%s.failed error=%s", name, exc)
            R["errors"][name] = traceback.format_exc()
            R[name] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    if R["defesa_civil"]["status"] == "ok" and R["ssp"]["status"] == "ok":
        R["duckdb"] = M.run_duckdb(config.CURATED)
    else:
        R["duckdb"] = []
    finished = datetime.now(timezone.utc)
    R["run"] = {"started_at": started.isoformat(), "finished_at": finished.isoformat(),
                "duration_s": round((finished - started).total_seconds(), 1), "run_date": run_date}
    from . import report
    decision = report.write_all(R)
    raw_files = []
    for p in sorted(config.RAW.rglob("*")):
        if p.is_file() and not p.name.endswith(".meta.json"):
            raw_files.append({"path": str(p.relative_to(config.ROOT)), "bytes": p.stat().st_size,
                              "sha256": sha256_file(p)})
    manifest = {
        "run_started_at": started.isoformat(),
        "run_finished_at": finished.isoformat(),
        "sources": [
            {"name": "defesa_civil_tags_data", "url": config.DC_GRAPHQL_URL, "doc": config.DC_DOC_URL,
             "status": R["defesa_civil"]["status"]},
            {"name": "ssp_microdados_art3", "page": config.SSP_OPEN_DATA_URL,
             "url": R["ssp"].get("discovery", {}).get("chosen", {}).get("url"), "status": R["ssp"]["status"]},
            {"name": "ssp_indicadores_criminais", "page": config.SSP_INDICATORS_URL,
             "url": (R["ssp"].get("indicators") or {}).get("link", {}).get("url")},
        ],
        "raw_files": raw_files,
        "row_counts": {
            "defesa_civil_stations": R["defesa_civil"].get("quality", {}).get("total_stations"),
            "defesa_civil_history_rows": R["defesa_civil"].get("history", {}).get("rows"),
            "ssp_occurrences": R["ssp"].get("quality", {}).get("total_rows"),
            "ssp_victims": R["ssp"].get("quality", {}).get("victims_total"),
            "ssp_quarantine_rows": R["ssp"].get("quarantine_rows"),
        },
        "checks": decision["checks"],
        "errors": {k: v.splitlines()[-1] for k, v in R["errors"].items()},
        "result": decision["result"],
    }
    dump(config.REPORTS / "run_manifest.json", manifest)
    log.info("run.finish result=%s duration_s=%s", decision["result"], R["run"]["duration_s"])
    print(report.terminal_summary(R, decision))
    ok = [R[s]["status"] == "ok" for s in ("defesa_civil", "ssp")]
    return 0 if all(ok) else (2 if any(ok) else 1)


if __name__ == "__main__":
    sys.exit(main())
