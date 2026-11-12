"""Small, defensive HTTP layer: timeouts, bounded retries, UA, status and
content-type validation, redirect logging, raw persistence with sha256."""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import config

log = logging.getLogger("http")


class SourceError(RuntimeError):
    """Raised when a source does not honour its expected contract."""


@dataclass
class FetchRecord:
    source_url: str
    final_url: str
    method: str
    retrieved_at_utc: str
    http_status: int
    content_type: str
    content_length: int
    sha256: str
    elapsed_s: float
    redirects: list[str] = field(default_factory=list)
    saved_to: str | None = None
    request_body_sha256: str | None = None
    attempts: int = 1
    transient_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=config.HTTP_RETRIES,
        connect=config.HTTP_RETRIES,
        read=config.HTTP_RETRIES,
        status=config.HTTP_RETRIES,
        backoff_factor=2.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD", "POST"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update({"User-Agent": config.USER_AGENT})
    return s


def fetch(
    session: requests.Session,
    url: str,
    *,
    method: str = "GET",
    json_body: dict | None = None,
    expect_content_type: tuple[str, ...] = (),
    save_to: Path | None = None,
    stream: bool = False,
) -> tuple[requests.Response, bytes, FetchRecord]:
    t0 = time.monotonic()
    retrieved_at = utcnow().isoformat()
    transient: list[str] = []
    # urllib3's Retry covers connect/status errors, but NOT a body cut off
    # mid-transfer (observed: 'Connection reset by peer' on the SSP ZIP).
    # Bounded application-level retry; every failure is recorded as evidence.
    for attempt in range(1, config.HTTP_RETRIES + 2):
        try:
            resp = session.request(
                method, url, json=json_body, timeout=config.HTTP_TIMEOUT, allow_redirects=True
            )
            body = resp.content
            break
        except (requests.exceptions.ChunkedEncodingError, requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as exc:
            transient.append(f"attempt {attempt}: {type(exc).__name__}: {str(exc)[:160]}")
            log.warning("fetch.transient url=%s attempt=%s error=%s", url, attempt, type(exc).__name__)
            if attempt > config.HTTP_RETRIES:
                raise SourceError(f"{url} failed after {attempt} attempts: {transient}") from exc
            time.sleep(2 ** attempt)
    elapsed = round(time.monotonic() - t0, 3)
    redirects = [f"{r.status_code} {r.url}" for r in resp.history]
    if redirects:
        log.warning("redirect url=%s chain=%s final=%s", url, redirects, resp.url)
    ctype = resp.headers.get("Content-Type", "")
    rec = FetchRecord(
        source_url=url,
        final_url=resp.url,
        method=method,
        retrieved_at_utc=retrieved_at,
        http_status=resp.status_code,
        content_type=ctype,
        content_length=len(body),
        sha256=sha256_bytes(body),
        elapsed_s=elapsed,
        redirects=redirects,
        attempts=len(transient) + 1,
        transient_errors=transient,
        request_body_sha256=(
            sha256_bytes(json.dumps(json_body, sort_keys=True).encode()) if json_body else None
        ),
    )
    log.info(
        "fetch method=%s url=%s status=%s bytes=%s elapsed_s=%s ctype=%s",
        method, url, resp.status_code, len(body), elapsed, ctype.split(";")[0],
    )
    if save_to is not None:
        # RAW is written exactly as received, before any validation, so that
        # even a contract violation leaves forensic evidence on disk.
        write_raw(save_to, body, rec)
    if resp.status_code != 200:
        raise SourceError(f"HTTP {resp.status_code} for {url}")
    if expect_content_type and not any(ct in ctype for ct in expect_content_type):
        raise SourceError(f"Unexpected Content-Type {ctype!r} for {url}")
    return resp, body, rec


def write_raw(path: Path, body: bytes, rec: FetchRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        # Immutability: never overwrite a RAW file with different bytes.
        if sha256_file(path) == rec.sha256:
            log.info("raw.exists identical path=%s", path)
        else:
            stem = path.stem + "_" + rec.sha256[:12]
            path = path.with_name(stem + path.suffix)
            log.warning("raw.exists different-content -> new file %s", path)
    path.write_bytes(body)
    rec.saved_to = str(path.relative_to(config.ROOT)) if path.is_relative_to(config.ROOT) else str(path)
    meta = path.with_name(path.name + ".meta.json")
    meta.write_text(json.dumps(rec.to_dict(), indent=2, ensure_ascii=False))
