"""SSP-RS microdata (Lei 15.610/2021, art. 3º) normalization.

Real layout (validated against the official data dictionary):
* one row per occurrence; ';' delimited; Latin-1/CP1252;
* 13 named columns, then the victim triplet (Idade, Sexo, Cor) REPEATS to the
  right once per victim — the header names only the first triplet, followed by a
  literal '...' column and blank headers.
Nothing is deleted: anomalies become `quality_flags`; critical rows are also
copied to data/quarantine/ for review.
"""
from __future__ import annotations

import csv
import logging
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path

import pandas as pd

log = logging.getLogger("ssp.normalize")

EXPECTED_HEADER = [
    "SEQUENCIA", "DATA FATO", "HORA FATO", "GRUPO FATO", "TIPO ENQUADRAMENTO",
    "TIPO FATO", "MUNICIPIO FATO", "LOCAL FATO", "BAIRRO", "QUANTIDADE VITIMAS",
    "IDADE VITIMA", "SEXO VITIMA", "COR VITIMA",
]
VICTIM_START = 10  # index of first 'Idade Vítima'
CRITICAL_FLAGS = {"date_invalid", "date_future", "municipality_empty", "category_empty"}


# ---------------------------------------------------------------- text utils
def fold(s: str | None) -> str:
    """NFKD, strip accents, collapse whitespace, trim, uppercase."""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().upper()


def normalize_municipality(s: str | None) -> str | None:
    out = fold(s)
    return out or None


def normalize_category(s: str | None) -> str | None:
    out = fold(s)
    return out or None


def parse_date_br(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def parse_time_hms(s: str | None) -> str | None:
    if not s:
        return None
    m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", s.strip())
    if not m:
        return None
    h, mi, se = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    if h > 23 or mi > 59 or se > 59:
        return None
    return f"{h:02d}:{mi:02d}:{se:02d}"


def age_flag(raw: str | None) -> str | None:
    """Return a quality flag for a victim age value, or None when acceptable/absent."""
    if raw is None or str(raw).strip() == "":
        return None
    try:
        a = float(str(raw).strip().replace(",", "."))
    except ValueError:
        return "age_non_numeric"
    if a < 0:
        return "age_negative"
    if a > 115:
        return "age_gt_115"
    return None


def parse_age(raw: str | None) -> float | None:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return float(str(raw).strip().replace(",", "."))
    except ValueError:
        return None


def date_flags(d: date | None, raw: str | None, reference: date,
               period: tuple[date, date] | None = None) -> list[str]:
    flags = []
    if d is None:
        flags.append("date_missing" if not raw else "date_invalid")
        return flags
    if d > reference:
        flags.append("date_future")
    if period and not (period[0] <= d <= period[1]):
        flags.append("date_outside_declared_period")
    return flags


# ------------------------------------------------------------ file handling
def detect_encoding(path: Path) -> str:
    data = path.read_bytes()
    try:
        data.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    # C1 control range used as printable in CP1252 but not in Latin-1.
    return "cp1252" if re.search(rb"[\x80-\x9f]", data) else "latin-1"


def detect_delimiter(header_line: str) -> str:
    counts = {d: header_line.count(d) for d in (";", ",", "\t", "|")}
    return max(counts, key=counts.get)


def declared_period_from_name(name: str) -> tuple[date, date] | None:
    months = {"JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6,
              "JUL": 7, "AGO": 8, "SET": 9, "OUT": 10, "NOV": 11, "DEZ": 12}
    m = re.search(r"([A-Z]{3})_([A-Z]{3})_(20\d{2})", fold(name).replace(" ", "_"))
    if not m or m.group(1) not in months or m.group(2) not in months:
        return None
    y = int(m.group(3))
    start = date(y, months[m.group(1)], 1)
    em = months[m.group(2)]
    end = (date(y + 1, 1, 1) if em == 12 else date(y, em + 1, 1))
    return start, date.fromordinal(end.toordinal() - 1)


def extraction_date_from_name(name: str) -> date | None:
    m = re.search(r"(\d{2})\.(\d{2})\.(20\d{2})", name)
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def read_raw_rows(path: Path):
    enc = detect_encoding(path)
    with open(path, encoding=enc, newline="") as fh:
        first = fh.readline()
    delim = detect_delimiter(first)
    with open(path, encoding=enc, newline="") as fh:
        reader = csv.reader(fh, delimiter=delim)
        header = next(reader)
        rows = list(reader)
    return enc, delim, header, rows


def validate_header(header: list[str]) -> dict:
    named = [fold(h) for h in header[: len(EXPECTED_HEADER)]]
    ok = named == EXPECTED_HEADER
    return {
        "ok": ok,
        "observed_first13": header[: len(EXPECTED_HEADER)],
        "expected_first13_folded": EXPECTED_HEADER,
        "total_header_cells": len(header),
        "extra_header_cells": header[len(EXPECTED_HEADER):len(EXPECTED_HEADER) + 3],
    }


def split_victims(row: list[str]) -> list[tuple[str, str, str]]:
    cells = row[VICTIM_START:]
    trip = [tuple((cells[i:i + 3] + ["", "", ""])[:3]) for i in range(0, len(cells), 3)]
    while trip and not any(x.strip() for x in trip[-1]):
        trip.pop()
    return trip


def normalize_file(path: Path, *, reference_date: date, source_version: str,
                   ingested_at: str) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    enc, delim, header, rows = read_raw_rows(path)
    hv = validate_header(header)
    if not hv["ok"]:
        raise ValueError(f"SSP schema drift: {hv}")
    period = declared_period_from_name(path.name)
    width_counts: dict[int, int] = {}
    occ, victims = [], []
    for r in rows:
        width_counts[len(r)] = width_counts.get(len(r), 0) + 1
        r = r + [""] * (13 - len(r)) if len(r) < 13 else r
        seq, d_raw, t_raw, grp, cat_raw, tf, mun_raw, local, bairro_raw, qv_raw = r[:10]
        d = parse_date_br(d_raw)
        t = parse_time_hms(t_raw)
        trip = split_victims(r)
        listed = [x for x in trip if any(c.strip() for c in x)]
        flags = date_flags(d, d_raw, reference_date, period)
        if t_raw and t is None:
            flags.append("time_invalid")
        if not t_raw:
            flags.append("time_missing")
        mun = normalize_municipality(mun_raw)
        cat = normalize_category(cat_raw)
        if not mun:
            flags.append("municipality_empty")
        if not cat:
            flags.append("category_empty")
        if not bairro_raw.strip():
            flags.append("neighborhood_empty")
        try:
            qv = int(qv_raw)
        except ValueError:
            qv = None
            flags.append("victim_count_missing" if not qv_raw.strip() else "victim_count_invalid")
        if qv is not None and qv != len(trip):
            flags.append("victim_count_mismatch")
        for i, (age, sex, race) in enumerate(trip):
            af = age_flag(age)
            if af and af not in flags:
                flags.append(af)
            victims.append({
                "occurrence_id": int(seq) if seq.isdigit() else None,
                "victim_index": i + 1,
                "victim_age": parse_age(age),
                "victim_age_raw": age or None,
                "victim_sex": sex.strip() or None,
                "victim_race": race.strip() or None,
                "age_flag": af,
            })
        first = trip[0] if trip else ("", "", "")
        occ.append({
            "occurrence_id": int(seq) if seq.isdigit() else None,
            "occurrence_date": d,
            "occurrence_date_raw": d_raw,
            "occurrence_time": t,
            "occurrence_time_raw": t_raw,
            "fact_group": fold(grp) or None,
            "category": cat,
            "category_raw": cat_raw,
            "fact_type": tf.strip() or None,
            "municipality": mun,
            "municipality_raw": mun_raw,
            "place_type": fold(local) or None,
            "neighborhood": fold(bairro_raw) or None,
            "neighborhood_raw": bairro_raw or None,
            "victim_count": qv,
            "victims_listed": len(listed),
            "victim_age": parse_age(first[0]),
            "victim_sex": first[1].strip() or None,
            "victim_race": first[2].strip() or None,
            "quality_flags": "|".join(flags),
        })
    df = pd.DataFrame(occ)
    df["occurrence_date"] = pd.to_datetime(df["occurrence_date"])
    df["source_file"] = path.name
    df["source_version"] = source_version
    df["ingested_at"] = ingested_at
    vdf = pd.DataFrame(victims)
    info = {
        "encoding": enc, "delimiter": delim, "header_validation": hv,
        "row_width_distribution": width_counts, "data_rows": len(rows),
        "duplicate_full_rows_raw": len(rows) - len(set(map(tuple, rows))),
        "declared_period": [str(x) for x in period] if period else None,
        "extraction_date_in_name": str(extraction_date_from_name(path.name)),
    }
    log.info("ssp.parse rows=%s victims=%s encoding=%s", len(df), len(vdf), enc)
    return df, vdf, info
