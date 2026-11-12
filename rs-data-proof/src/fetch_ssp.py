"""SSP-RS open data — discover the latest monthly (art. 3º) file on the official
page at each run (no hard-coded ZIP URL), download, preserve, extract safely."""
from __future__ import annotations

import json
import logging
import re
import unicodedata
import zipfile
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from . import config
from .http import SourceError, fetch, sha256_file

log = logging.getLogger("ssp.fetch")


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def discover_open_data_links(html: str, base: str = config.SSP_BASE) -> dict:
    """Walk the page in document order, tracking the section headings
    'publicação mensal' / 'publicação semestral'. Returns candidates per section."""
    soup = BeautifulSoup(html, "lxml")
    content = soup.find(id="conteudo") or soup.find("main") or soup.body or soup
    section = None
    out: dict[str, list[dict]] = {"mensal": [], "semestral": [], "other": []}
    seen = set()
    for el in content.descendants:
        if isinstance(el, str):
            t = _fold(el)
            if "publicacao mensal" in t:
                section = "mensal"
            elif "publicacao semestral" in t:
                section = "semestral"
            continue
        if getattr(el, "name", None) != "a" or not el.get("href"):
            continue
        href = el["href"].strip()
        if not re.search(r"\.(zip|csv|xlsx?)($|\?)", href, re.I):
            continue
        url = urljoin(base + "/", href)
        if url in seen:
            continue
        seen.add(url)
        text = " ".join(el.get_text(" ", strip=True).split())
        years = [int(y) for y in re.findall(r"\b(20\d{2})\b", text)]
        if not years:  # fall back to file name, e.g. ...-jan-set-2026-...
            years = [int(y) for y in re.findall(r"(20\d{2})", href.rsplit("/", 1)[-1])]
        out[section or "other"].append({"text": text, "url": url, "years": years})
    return out


def pick_latest(cands: list[dict]) -> dict:
    zips = [c for c in cands if c["years"]]
    if not zips:
        raise SourceError("No dated candidate link found in 'publicação mensal' section")
    # The FIRST year in the label is the coverage year; later years are
    # revision dates (e.g. "2024 (janeiro a dezembro) – atualizado em janeiro de 2026").
    return max(zips, key=lambda c: (c["years"][0], c["url"].endswith(".zip")))


def discover_indicator_links(html: str, base: str = config.SSP_BASE) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not re.search(r"\.xlsx?$", href, re.I):
            continue
        url = urljoin(base + "/", href)
        text = " ".join(a.get_text(" ", strip=True).split())
        if url in seen or "indicadores" not in _fold(text):
            continue
        seen.add(url)
        years = [int(y) for y in re.findall(r"\b(20\d{2})\b", text)]
        out.append({"text": text, "url": url, "years": years})
    return out


def safe_extract(zip_path: Path, dest: Path) -> list[dict]:
    dest.mkdir(parents=True, exist_ok=True)
    members = []
    with zipfile.ZipFile(zip_path) as zf:
        bad = zf.testzip()
        if bad:
            raise SourceError(f"Corrupt member in ZIP: {bad}")
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            utf8_flag = bool(info.flag_bits & 0x800)
            target = (dest / Path(name).name).resolve()
            if not str(target).startswith(str(dest.resolve())):
                raise SourceError(f"Unsafe path in ZIP: {name}")
            with zf.open(info) as src, open(target, "wb") as dst:
                while chunk := src.read(1 << 20):
                    dst.write(chunk)
            members.append({
                "member_name_in_zip": name,
                "utf8_name_flag": utf8_flag,
                "extracted_to": str(target.relative_to(config.ROOT)) if target.is_relative_to(config.ROOT) else str(target),
                "compressed_size": info.compress_size,
                "uncompressed_size": info.file_size,
                "zip_datetime": "%04d-%02d-%02dT%02d:%02d:%02d" % info.date_time,
                "crc32": f"{info.CRC:08x}",
                "sha256": sha256_file(target),
            })
    return members


def run(session, run_date: str) -> dict:
    raw_dir = config.RAW / "ssp" / run_date
    raw_dir.mkdir(parents=True, exist_ok=True)
    _, page, page_rec = fetch(session, config.SSP_OPEN_DATA_URL, expect_content_type=("text/html",),
                              save_to=raw_dir / "dados_abertos_page.html")
    links = discover_open_data_links(page.decode("utf-8", errors="replace"))
    log.info("ssp.discover mensal=%s semestral=%s other=%s",
             len(links["mensal"]), len(links["semestral"]), len(links["other"]))
    latest = pick_latest(links["mensal"])
    log.info("ssp.latest text=%r url=%s", latest["text"], latest["url"])
    _, zbytes, zrec = fetch(session, latest["url"],
                            expect_content_type=("zip", "octet-stream", "csv", "text/plain"),
                            save_to=raw_dir / "source.zip")
    log.info("ssp.download bytes=%s sha256=%s", zrec.content_length, zrec.sha256[:16])
    zip_path = config.ROOT / zrec.saved_to
    if not zipfile.is_zipfile(zip_path):
        raise SourceError("Downloaded monthly file is not a ZIP (format drift)")
    members = safe_extract(zip_path, raw_dir / "extracted")
    discovery = {
        "source_page": config.SSP_OPEN_DATA_URL,
        "page_sha256": page_rec.sha256,
        "candidates": links,
        "chosen": latest,
        "download": zrec.to_dict(),
        "zip_members": members,
    }
    (raw_dir / "discovery.json").write_text(json.dumps(discovery, indent=2, ensure_ascii=False))

    # Optional cross-validation source: aggregated criminal indicators (same year).
    indicators = None
    try:
        _, ipage, _ = fetch(session, config.SSP_INDICATORS_URL, expect_content_type=("text/html",),
                            save_to=raw_dir / "indicadores_page.html")
        ilinks = discover_indicator_links(ipage.decode("utf-8", errors="replace"))
        year = latest["years"][0]
        same_year = [l for l in ilinks if l["years"] and l["years"][0] == year]
        if same_year:
            pick = same_year[0]
            _, _, irec = fetch(session, pick["url"], save_to=raw_dir / f"indicadores_{year}.xlsx")
            indicators = {"link": pick, "record": irec.to_dict(), "year": year}
            log.info("ssp.indicators url=%s bytes=%s", pick["url"], irec.content_length)
    except Exception as exc:
        log.warning("ssp.indicators unavailable error=%s", exc)
        indicators = {"error": str(exc)}
    return {"raw_dir": raw_dir, "discovery": discovery, "indicators": indicators}
