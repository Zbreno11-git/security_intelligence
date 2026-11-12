"""Defesa Civil RS — fetch tags_data + historic using the OFFICIAL query text.

The official API only accepts the exact queries published on the documentation
page. We therefore (1) download the documentation page, (2) extract the query
text from its <pre> blocks, (3) compare it with the copy vendored in
src/queries/ (captured from the same page), and (4) always send the live
documentation version. Any difference is recorded as source drift.
"""
from __future__ import annotations

import json
import logging
import math
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from . import config
from .http import SourceError, fetch, utcnow

log = logging.getLogger("defesa_civil.fetch")
QUERIES_DIR = Path(__file__).parent / "queries"
BRT = timezone(timedelta(hours=-3))  # Brasília, no DST since 2019


def _collapse(q: str) -> str:
    # API states whitespace/line breaks do not matter; compare token streams.
    return re.sub(r"\s+", " ", q).strip()


def extract_official_queries(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "lxml")
    out: dict[str, str] = {}
    for pre in soup.find_all("pre"):
        txt = pre.get_text().strip()
        if txt.startswith("query Tags_data"):
            out.setdefault("tags_data", txt)
        elif txt.startswith("query Historic"):
            out.setdefault("historic", txt)
    return out


def load_queries(session, raw_dir: Path) -> tuple[dict[str, str], dict]:
    vendored = {
        "tags_data": (QUERIES_DIR / "tags_data.graphql").read_text().strip(),
        "historic": (QUERIES_DIR / "historic.graphql").read_text().strip(),
    }
    drift: dict = {"doc_url": config.DC_DOC_URL, "doc_reachable": False, "queries": {}}
    try:
        _, body, rec = fetch(
            session, config.DC_DOC_URL, expect_content_type=("text/html",),
            save_to=raw_dir / "api_documentation.html",
        )
        drift["doc_reachable"] = True
        drift["doc_sha256"] = rec.sha256
        live = extract_official_queries(body.decode("utf-8", errors="replace"))
    except Exception as exc:  # documented fallback, never silent
        log.error("doc.unreachable error=%s -> using vendored queries", exc)
        drift["doc_error"] = str(exc)
        live = {}
    chosen = {}
    for name, vq in vendored.items():
        lq = live.get(name)
        status = (
            "doc_missing_query" if lq is None
            else "identical" if _collapse(lq) == _collapse(vq)
            else "CHANGED_IN_DOC"
        )
        drift["queries"][name] = status
        if status == "CHANGED_IN_DOC":
            log.warning("query.drift name=%s -> using live documentation text", name)
        chosen[name] = lq or vq  # official source prevails
    return chosen, drift


def _graphql(session, query: str, variables: dict | None, save_to: Path):
    body = {"query": query}
    if variables is not None:
        body["variables"] = variables
    resp, raw, rec = fetch(
        session, config.DC_GRAPHQL_URL, method="POST", json_body=body,
        expect_content_type=("application/json",), save_to=save_to,
    )
    payload = json.loads(raw)
    if payload.get("errors"):
        raise SourceError(f"GraphQL errors: {json.dumps(payload['errors'])[:500]}")
    return payload, rec


def fetch_tags_data(session, query: str, raw_dir: Path):
    payload, rec = _graphql(session, query, None, raw_dir / "tags_data.json")
    td = payload["data"]["tags_data"]
    if isinstance(td, list):  # tolerate list wrapper
        td = td[0]
    stations = td.get("qualle_meteorologia")
    if not isinstance(stations, list):
        raise SourceError("tags_data.qualle_meteorologia missing or not a list")
    n = len(stations)
    if n != config.DC_EXPECTED_STATIONS:
        log.warning("station_count_diff observed=%s documented=%s", n, config.DC_EXPECTED_STATIONS)
    log.info(
        "tags_data status=%s stations=%s bytes=%s elapsed_s=%s proximaAtualizacaoEm=%s",
        rec.http_status, n, rec.content_length, rec.elapsed_s, td.get("proximaAtualizacaoEm"),
    )
    return payload, rec


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def select_history_stations(stations_df, max_n: int) -> list[tuple[str, str]]:
    """Pick real stations with data: closest valid stations to Gramado/Canela,
    plus the river station with the highest official status / rising trend."""
    chosen: list[tuple[str, str]] = []
    df = stations_df
    valid = df[(df["has_river_value"] | df["has_rain_value"]) & df["latitude"].notna()]
    serra = valid.sort_values("dist_serra_km").head(max_n - 2)
    for c in serra["codigo"]:
        chosen.append((c, "nearest_to_gramado_canela"))
    river = valid[valid["has_river_value"]].copy()
    if not river.empty:
        river = river.sort_values(
            ["official_status_code", "rio_nivel_tendencia_m"], ascending=[False, False], na_position="last"
        )
        top = river.iloc[0]["codigo"]
        if top not in [c for c, _ in chosen]:
            chosen.append((top, "highest_official_status_or_rising_trend"))
        rain = valid[valid["has_rain_value"]].sort_values("rain_24h_mm", ascending=False)
        if not rain.empty and rain.iloc[0]["codigo"] not in [c for c, _ in chosen]:
            chosen.append((rain.iloc[0]["codigo"], "highest_rain_24h"))
    return chosen[:max_n]


def fetch_historic(session, query: str, station: str, end_brt: datetime, raw_dir: Path):
    start = end_brt - timedelta(hours=config.DC_HISTORIC_HOURS)
    variables = {
        "stationCode": station,
        "startDate": start.strftime("%Y-%m-%d %H:%M:%S"),
        "endDate": end_brt.strftime("%Y-%m-%d %H:%M:%S"),
        "interval": config.DC_HISTORIC_INTERVAL,  # explicit, see doc inconsistency
    }
    payload, rec = _graphql(session, query, variables, raw_dir / f"historic_{station}.json")
    h = payload["data"]["historic"]
    items = h.get("items") if isinstance(h, dict) else None
    if items is None:
        raise SourceError(f"historic for {station}: unexpected shape {type(h)}")
    log.info("historic station=%s items=%s totalCount=%s bytes=%s", station, len(items), h.get("totalCount"), rec.content_length)
    return payload, rec, variables


def probe_history_limit(session, query: str, station: str, raw_dir: Path) -> dict:
    """One request ~100 days back: documented to fail with BAD_REQUEST (3-month
    window). Evidence for H5 (value of keeping our own history)."""
    now = datetime.now(BRT).replace(microsecond=0)
    start = now - timedelta(days=100)
    variables = {
        "stationCode": station,
        "startDate": start.strftime("%Y-%m-%d %H:%M:%S"),
        "endDate": (start + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
        "interval": "HOUR_1",
    }
    body = {"query": query, "variables": variables}
    try:
        _, raw, rec = fetch(session, config.DC_GRAPHQL_URL, method="POST", json_body=body,
                            save_to=raw_dir / "probe_history_100d.json")
        payload = json.loads(raw)
        errs = payload.get("errors")
        return {
            "variables": variables, "http_status": rec.http_status,
            "accepted": not errs, "errors": errs,
            "items": (len(payload.get("data", {}).get("historic", {}).get("items", []))
                      if not errs and payload.get("data") else None),
        }
    except SourceError as exc:
        return {"variables": variables, "accepted": False, "error": str(exc)}


def run(session, run_date: str) -> dict:
    raw_dir = config.RAW / "defesa_civil" / run_date
    raw_dir.mkdir(parents=True, exist_ok=True)
    queries, drift = load_queries(session, raw_dir)
    collected_at = utcnow()
    payload, rec = fetch_tags_data(session, queries["tags_data"], raw_dir)
    return {
        "raw_dir": raw_dir, "queries": queries, "drift": drift,
        "tags_payload": payload, "tags_record": rec, "collected_at": collected_at,
    }


def run_history(session, ctx: dict, stations_df) -> dict:
    raw_dir = ctx["raw_dir"]
    picks = select_history_stations(stations_df, config.DC_MAX_HISTORIC_CALLS - 1)
    end_brt = ctx["collected_at"].astimezone(BRT).replace(tzinfo=None, microsecond=0)
    results = []
    for code, reason in picks:
        time.sleep(config.DC_SLEEP_BETWEEN_CALLS_S)
        try:
            payload, rec, variables = fetch_historic(session, ctx["queries"]["historic"], code, end_brt, raw_dir)
            results.append({"codigo": code, "reason": reason, "payload": payload,
                            "record": rec, "variables": variables, "ok": True})
        except Exception as exc:
            log.error("historic.failed station=%s error=%s", code, exc)
            results.append({"codigo": code, "reason": reason, "ok": False, "error": str(exc)})
    time.sleep(config.DC_SLEEP_BETWEEN_CALLS_S)
    probe = probe_history_limit(session, ctx["queries"]["historic"], picks[0][0] if picks else "DCRS-00001", raw_dir)
    log.info("historic.limit_probe accepted=%s", probe.get("accepted"))
    return {"results": results, "probe": probe}
