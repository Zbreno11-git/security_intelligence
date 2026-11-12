"""Normalization tests. Fixtures are small verbatim excerpts of real RAW files
captured from the official sources on 2026-11-12 (no invented records)."""
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from src import normalize_defesa_civil as ndc
from src import normalize_ssp as nssp
from src.fetch_defesa_civil import _collapse, extract_official_queries
from src.fetch_ssp import discover_open_data_links, pick_latest

FX = Path(__file__).parent / "fixtures"
COLLECTED = datetime(2026, 11, 12, 20, 56, 0, tzinfo=timezone.utc)


# ------------------------------------------------------------ Defesa Civil
def test_timestamp_is_brasilia_converted_to_utc():
    dt = ndc.parse_station_timestamp("2026-10-14T08:40:00.000")
    assert dt == datetime(2026, 10, 14, 11, 40, tzinfo=timezone.utc)


def test_timestamp_missing_or_garbage_is_none():
    assert ndc.parse_station_timestamp(None) is None
    assert ndc.parse_station_timestamp("") is None
    assert ndc.parse_station_timestamp("not-a-date") is None


def test_value_null_parsing():
    node = {"rio": {"rio_nivel": {"value": None}, "rio_nome": None, "x": {"value": 0}}}
    assert ndc.v(node, "rio", "rio_nivel") is None      # value: null
    assert ndc.v(node, "rio", "rio_nome") is None       # whole object null
    assert ndc.v(node, "rio", "missing", "deep") is None
    assert ndc.v(node, "rio", "x") == 0                  # zero is NOT missing


@pytest.mark.parametrize("ativo,status,expected", [
    (True, 0, "normal"), (True, 1, "attention"), (True, 2, "alert"), (True, 3, "flood"),
    (True, None, "unavailable"), (False, 0, "no_threshold"), (None, None, "no_river_alarm_data"),
    (True, 9, "unknown_code"),
])
def test_official_status(ativo, status, expected):
    assert ndc.official_status(ativo, status) == expected


@pytest.mark.parametrize("age,expected", [
    (0, "fresh"), (10, "fresh"), (10.01, "delayed"), (20, "delayed"), (20.5, "stale"),
    (None, "unknown"), (-30, "future_timestamp"),
])
def test_freshness(age, expected):
    assert ndc.freshness_class(age) == expected


def test_confidence_score_rules_and_clamp():
    assert ndc.technical_data_confidence(False, "fresh", True, False) == 100
    assert ndc.technical_data_confidence(True, "fresh", True, False) == 70
    assert ndc.technical_data_confidence(False, "stale", True, False) == 75
    assert ndc.technical_data_confidence(False, "fresh", False, False) == 80
    assert ndc.technical_data_confidence(False, "fresh", True, True) == 85
    assert ndc.technical_data_confidence(True, "stale", False, True) == 10
    assert 0 <= ndc.technical_data_confidence(True, "unknown", False, True) <= 100
    assert ndc.technical_data_confidence(None, "fresh", None, False) == 100


def test_normalize_real_stations_excerpt():
    payload = json.loads((FX / "tags_data_excerpt.json").read_text())
    df, prox = ndc.normalize_stations(payload, COLLECTED)
    assert prox and prox.endswith("Z")
    by = df.set_index("codigo")
    assert by.loc["DCRS-00001", "freshness"] == "fresh"
    assert by.loc["DCRS-00001", "official_status"] == "normal"
    assert by.loc["DCRS-00110", "official_status"] == "attention"
    # real defect: station with no timestamp and no values
    assert by.loc["DCRS-00125", "freshness"] == "unknown"
    assert "river_value_null" in by.loc["DCRS-00125", "quality_flags"]
    assert by.loc["DCRS-00125", "technical_data_confidence"] == 60
    # real defect: station without name/coordinates
    assert "no_coordinates" in by.loc["DCRS-00129", "quality_flags"]
    assert by.loc["DCRS-00062", "river_homologated"] is False or by.loc["DCRS-00062", "river_homologated"] == False  # noqa: E712


def test_normalize_history_excerpt():
    p = json.loads((FX / "historic_excerpt.json").read_text())
    h = ndc.normalize_history(p["data"]["historic"]["items"], "MIN_5", "x.json")
    assert len(h) == 25
    assert h["ts_utc"].is_monotonic_increasing
    assert str(h["ts_utc"].dt.tz) == "UTC"
    assert h["unexpected_fields"].isna().all()


def test_official_query_extraction_and_whitespace_insensitive_compare():
    q = Path("src/queries/tags_data.graphql").read_text()
    html = f"<html><body><pre><code>{q}</code></pre></body></html>"
    got = extract_official_queries(html)
    assert _collapse(got["tags_data"]) == _collapse(q)
    assert _collapse("a\n  b   c") == "a b c"


# --------------------------------------------------------------------- SSP
def test_municipality_normalization():
    assert nssp.normalize_municipality("  gramado ") == "GRAMADO"
    assert nssp.normalize_municipality("São  Francisco de Paula") == "SAO FRANCISCO DE PAULA"
    assert nssp.normalize_municipality("") is None
    # exact match matters: these must NOT become GRAMADO
    assert nssp.normalize_municipality("Gramado Xavier") != "GRAMADO"


def test_date_parsing():
    assert nssp.parse_date_br("01/09/2026") == date(2026, 9, 1)
    assert nssp.parse_date_br("31/02/2026") is None
    assert nssp.parse_date_br("2026-09-01") is None
    assert nssp.parse_date_br("") is None


def test_time_parsing():
    assert nssp.parse_time_hms("00:01:00") == "00:01:00"
    assert nssp.parse_time_hms("7:05") == "07:05:00"
    assert nssp.parse_time_hms("24:00:00") is None
    assert nssp.parse_time_hms("12:60:00") is None


@pytest.mark.parametrize("raw,flag", [
    ("", None), ("0", None), ("45", None), ("115", None),
    ("116", "age_gt_115"), ("126", "age_gt_115"), ("-1", "age_negative"), ("abc", "age_non_numeric"),
])
def test_age_quality_flag(raw, flag):
    assert nssp.age_flag(raw) == flag


def test_future_date_flag():
    ref = date(2026, 11, 12)
    assert "date_future" in nssp.date_flags(date(2026, 12, 1), "01/12/2026", ref)
    assert nssp.date_flags(date(2026, 9, 1), "01/09/2026", ref) == []
    assert nssp.date_flags(None, "99/99/2026", ref) == ["date_invalid"]
    assert nssp.date_flags(None, "", ref) == ["date_missing"]
    period = (date(2026, 1, 1), date(2026, 9, 30))
    assert "date_outside_declared_period" in nssp.date_flags(date(2025, 12, 31), "x", ref, period)


def test_split_victims_variable_width():
    row = ["1", "01/01/2026", "00:01:00", "CRIMES", "X", "Consumado", "A", "B", "C", "2",
           "30", "Masculino", "Branca", "41", "Feminino", "Parda", "", "", "", "", ""]
    assert nssp.split_victims(row) == [("30", "Masculino", "Branca"), ("41", "Feminino", "Parda")]


def test_declared_period_and_extraction_date_from_real_name():
    name = "SPJ_DADOS_ABERTOS_OCORR#U00caNCIAS_JAN_SET_2026 - Em 06.10.2026.csv"
    assert nssp.declared_period_from_name(name) == (date(2026, 1, 1), date(2026, 9, 30))
    assert nssp.extraction_date_from_name(name) == date(2026, 10, 6)


def test_normalize_real_ssp_excerpt():
    f = next(FX.glob("ssp_excerpt_*.csv"))
    df, vdf, info = nssp.normalize_file(f, reference_date=date(2026, 11, 12),
                                        source_version="test", ingested_at="t")
    assert info["encoding"] in ("latin-1", "cp1252")
    assert info["delimiter"] == ";"
    assert info["header_validation"]["ok"]
    assert len(df) == 12
    assert set(df["municipality"]) >= {"GRAMADO", "GRAMADO XAVIER", "CANELA"}
    assert (df["municipality"] == "GRAMADO").sum() == 2
    flags = "|".join(df["quality_flags"])
    assert "victim_count_missing" in flags
    assert "age_gt_115" in flags
    three = df[df["victim_count"] == 3].iloc[0]
    assert three["victims_listed"] == 3
    assert len(vdf[vdf["occurrence_id"] == three["occurrence_id"]]) == 3
    assert "victim_count_mismatch" not in flags
    assert df["category_raw"].notna().all()   # raw preserved next to normalized


def test_schema_drift_is_detected(tmp_path):
    bad = tmp_path / "x.csv"
    bad.write_bytes("Seq;Data;Hora\n1;01/01/2026;00:00:00\n".encode("latin-1"))
    with pytest.raises(ValueError, match="schema drift"):
        nssp.normalize_file(bad, reference_date=date(2026, 11, 12), source_version="t", ingested_at="t")


def test_link_discovery_uses_coverage_year_not_revision_year():
    html = """<div id='conteudo'><p>Dados abertos - publicação mensal</p>
      <a href='/upload/a/2026.zip'>2026 (janeiro a setembro) (.zip)</a>
      <a href='/upload/a/2024.zip'>2024 (janeiro a dezembro) – atualizado em janeiro de 2026 (.zip)</a>
      <p>Dados abertos - publicação semestral</p>
      <a href='/upload/a/s.zip'>1º semestre de 2027 (.zip)</a></div>"""
    links = discover_open_data_links(html)
    assert len(links["mensal"]) == 2 and len(links["semestral"]) == 1
    assert pick_latest(links["mensal"])["url"].endswith("/2026.zip")
