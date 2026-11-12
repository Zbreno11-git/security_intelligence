"""Normalization of Defesa Civil RS payloads (pure functions, unit-tested)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from . import config

BRT = timezone(timedelta(hours=-3))

STATUS_LABELS = {0: "normal", 1: "attention", 2: "alert", 3: "flood"}


def v(node: Any, *path: str) -> Any:
    """Walk nested dicts and unwrap {'value': x}. Missing/None at any level -> None.
    `value: null` (sensor did not report in the last 20 min) also yields None."""
    cur = node
    for p in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    if isinstance(cur, dict) and "value" in cur:
        return cur["value"]
    return cur


def parse_station_timestamp(ts: str | None) -> datetime | None:
    """API timestamps are naive Brasília time (e.g. 2026-10-14T08:40:00.000).
    Returns an aware UTC datetime, or None if absent/unparseable."""
    if not ts or not isinstance(ts, str):
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=BRT)
    return dt.astimezone(timezone.utc)


def parse_utc(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def official_status(ativo: Any, status: Any) -> str:
    """Official river-level classification per API documentation table."""
    if ativo is None and status is None:
        return "no_river_alarm_data"
    if ativo is True:
        if status is None:
            return "unavailable"  # 'Sem leitura de nível recente'
        try:
            return STATUS_LABELS.get(int(status), "unknown_code")
        except (TypeError, ValueError):
            return "unknown_code"
    if ativo is False:
        return "no_threshold"  # 'Estação sem limiar cadastrado'
    return "unknown_code"


def freshness_class(age_minutes: float | None) -> str:
    """Technical freshness of the reading. NOT hydrological risk."""
    if age_minutes is None or pd.isna(age_minutes):
        return "unknown"
    if age_minutes < -5:
        return "future_timestamp"
    if age_minutes <= config.FRESH_MAX_MIN:
        return "fresh"
    if age_minutes <= config.DELAYED_MAX_MIN:
        return "delayed"
    return "stale"


def technical_data_confidence(
    maintenance: bool | None,
    freshness: str,
    relevant_sensor_homologated: bool | None,
    main_measure_missing: bool,
) -> int:
    """EXPERIMENTAL, non-official technical score (0-100). Not a flood probability."""
    score = 100
    if maintenance is True:
        score -= 30
    if freshness in ("stale", "unknown", "future_timestamp"):
        score -= 25
    if relevant_sensor_homologated is False:
        score -= 20
    if main_measure_missing:
        score -= 15
    return max(0, min(100, score))


def _num(x: Any) -> float | None:
    if x is None or isinstance(x, bool):
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


RAIN_KEYS = ["min005", "h001", "h003", "h006", "h012", "h024", "h048", "h168"]


def normalize_station(st: dict, collected_at: datetime) -> dict:
    d = st.get("data") or {}
    rio, chuva = d.get("rio") or {}, d.get("chuva") or {}
    flt = v(st, "filter", "relacao") or {}
    ts_raw = st.get("timestamp")
    ts_utc = parse_station_timestamp(ts_raw)
    age = (collected_at - ts_utc).total_seconds() / 60 if ts_utc else None
    fresh = freshness_class(age)
    has_river_sensor = bool(flt.get("tem_nivel_do_rio"))
    has_rain_sensor = bool(flt.get("tem_chuva_acumulada"))
    rio_nivel = _num(v(rio, "rio_nivel"))
    rain = {k: _num(v(chuva, "acumulado", k)) for k in RAIN_KEYS}
    ativo = v(rio, "rio_alarmes", "inundacao", "ativo")
    status_code = v(rio, "rio_alarmes", "inundacao", "status")
    river_homol = v(rio, "homologacao", "relacao", "valido")
    rain_homol = v(chuva, "homologacao", "relacao", "valido")
    maintenance = v(st, "resource", "estacao", "estado", "manutencao")
    if has_river_sensor:
        main_missing, relevant_homol = rio_nivel is None, river_homol
    elif has_rain_sensor:
        main_missing, relevant_homol = rain["h001"] is None, rain_homol
    else:
        main_missing, relevant_homol = True, None
    lat, lon = _num(v(st, "position", "latitude")), _num(v(st, "position", "longitude"))
    row = {
        "codigo": st.get("codigo"),
        "name_prefix": v(st, "name", "prefix"),
        "name_general": v(st, "name", "general"),
        "name_local": v(st, "name", "local") or None,
        "type": st.get("type"),
        "show": st.get("show"),
        "bacia": v(st, "position", "bacia"),
        "regiao": v(st, "position", "regiao"),
        "latitude": lat,
        "longitude": lon,
        "altitude": _num(v(st, "position", "altitude")),
        "crepdec_nome": v(st, "position", "filtros", "outros", "crepdec", "nome"),
        "crepdec_codigo": v(st, "position", "filtros", "outros", "crepdec", "codigo"),
        "timestamp_raw": ts_raw,
        "timestamp_utc": ts_utc,
        "collected_at_utc": collected_at,
        "age_minutes": round(age, 2) if age is not None else None,
        "freshness": fresh,
        "has_river_sensor": has_river_sensor,
        "has_rain_sensor": has_rain_sensor,
        "has_flow_sensor": bool(flt.get("tem_vazao_do_rio")),
        "rio_nome": v(rio, "rio_nome"),
        "rio_nivel_m": rio_nivel,
        "rio_nivel_tendencia_m": _num(v(rio, "rio_nivel_tendencia")),
        "rio_area_drenagem": _num(v(rio, "rio_area_drenagem")),
        "inundacao_ativo": ativo,
        "official_status_code": status_code,
        "official_status": official_status(ativo, status_code),
        "river_homologated": river_homol,
        **{f"rain_{k}_mm": rain[k] for k in RAIN_KEYS},
        "rain_homologated": rain_homol,
        "temperatura_c": _num(v(d, "temperatura", "atual")),
        "temperatura_max_dia_c": _num(v(d, "temperatura", "historico", "diaatual", "maxima")),
        "temperatura_min_dia_c": _num(v(d, "temperatura", "historico", "diaatual", "minima")),
        "umidade_pct": _num(v(d, "umidade", "atual")),
        "pressao_hpa": _num(v(d, "pressaoatmos", "atual")),
        "sensacao_termica_c": _num(v(d, "senstermica", "atual")),
        "vento_medio_kmh": _num(v(d, "vento", "velocidade_media")),
        "vento_max_kmh": _num(v(d, "vento", "velocidade_maxima")),
        "vento_direcao_graus": _num(v(d, "vento", "direcao")),
        "radiacao_wm2": _num(v(d, "radiacaosolar", "atual")),
        "temp_homologated": v(d, "temperatura", "homologacao", "relacao", "valido"),
        "maintenance": maintenance,
        "main_measure_missing": main_missing,
    }
    row["technical_data_confidence"] = technical_data_confidence(
        maintenance, fresh, relevant_homol, main_missing
    )
    row["has_river_value"] = rio_nivel is not None
    row["has_rain_value"] = rain["h001"] is not None or rain["h024"] is not None
    row["rain_1h_mm"], row["rain_24h_mm"] = rain["h001"], rain["h024"]
    if lat is not None and lon is not None:
        from .fetch_defesa_civil import haversine_km
        dists = {m: haversine_km((lat, lon), p) for m, p in config.SERRA_POINTS.items()}
        row["dist_gramado_km"] = round(dists["GRAMADO"], 2)
        row["dist_canela_km"] = round(dists["CANELA"], 2)
        row["dist_serra_km"] = round(min(dists.values()), 2)
    else:
        row["dist_gramado_km"] = row["dist_canela_km"] = row["dist_serra_km"] = None
    flags = []
    if maintenance is True:
        flags.append("maintenance")
    if fresh != "fresh":
        flags.append(f"freshness_{fresh}")
    if has_river_sensor and rio_nivel is None:
        flags.append("river_value_null")
    if has_rain_sensor and rain["h001"] is None:
        flags.append("rain_value_null")
    if river_homol is False:
        flags.append("river_not_homologated")
    if rain_homol is False:
        flags.append("rain_not_homologated")
    if lat is None or lon is None:
        flags.append("no_coordinates")
    row["quality_flags"] = "|".join(flags)
    return row


def normalize_stations(payload: dict, collected_at: datetime) -> tuple[pd.DataFrame, str | None]:
    td = payload["data"]["tags_data"]
    td = td[0] if isinstance(td, list) else td
    rows = [normalize_station(st, collected_at) for st in td["qualle_meteorologia"]]
    df = pd.DataFrame(rows)
    return df, td.get("proximaAtualizacaoEm")


HIST_FIELDS = [
    "ts", "codigo", "rio_nivel", "rio_variacao", "chuva_mm", "chuva_total",
    "chuva_taxa_med", "chuva_taxa_max", "temp_media", "sens_termica", "umid_rel",
    "pres_atmos", "vento_vel_med", "vento_vel_max", "vento_dir", "radiacao",
]


def normalize_history(items: list[dict], interval: str, source_file: str) -> pd.DataFrame:
    rows = []
    for it in items:
        r = {k: it.get(k) for k in HIST_FIELDS}
        r["unexpected_fields"] = ",".join(sorted(set(it) - set(HIST_FIELDS))) or None
        rows.append(r)
    df = pd.DataFrame(rows, columns=HIST_FIELDS + ["unexpected_fields"])
    df["ts_raw"] = df["ts"]
    df["ts_utc"] = pd.to_datetime(
        [parse_station_timestamp(x) for x in df["ts"]], utc=True
    )
    for c in HIST_FIELDS[2:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["interval"] = interval
    df["source_file"] = source_file
    return df.drop(columns=["ts"]).sort_values("ts_utc").reset_index(drop=True)
