"""Static configuration. No credentials: every source used here is public."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("RS_PROOF_ROOT", Path(__file__).resolve().parent.parent))
DATA = ROOT / "data"
RAW = DATA / "raw"
CURATED = DATA / "curated"
QUARANTINE = DATA / "quarantine"
REPORTS = ROOT / "reports"

USER_AGENT = (
    "rs-data-proof/0.1 (+technical evaluation of RS public data; "
    "low-frequency, non-commercial)"
)
HTTP_TIMEOUT = (15, 120)  # (connect, read) seconds
HTTP_RETRIES = 3  # bounded; never infinite

# --- Defesa Civil RS -------------------------------------------------------
DC_DOC_URL = "https://sistemas.defesacivil.rs.gov.br/api-redehidrometeorologica"
DC_GRAPHQL_URL = "https://redehidrometeorologica.defesacivil.rs.gov.br/graphql"
DC_CLIENT = "casa-militar-defesa-civil-rs"
DC_EXPECTED_STATIONS = 130  # documented contract observation, NOT a business constant
DC_HISTORIC_INTERVAL = "MIN_5"  # always sent explicitly (doc is inconsistent about default)
DC_HISTORIC_HOURS = 24
DC_MAX_HISTORIC_CALLS = 6  # well under the 120 req/min limit
DC_SLEEP_BETWEEN_CALLS_S = 1.5

# Freshness classes (technical data quality only, NOT hydrological risk)
FRESH_MAX_MIN = 10
DELAYED_MAX_MIN = 20

# Gramado / Canela reference points (municipal seats, approximate)
SERRA_POINTS = {
    "GRAMADO": (-29.3789, -50.8742),
    "CANELA": (-29.3656, -50.8158),
}
SERRA_RADIUS_KM = 40.0

# --- SSP-RS ----------------------------------------------------------------
SSP_OPEN_DATA_URL = "https://ssp.rs.gov.br/dados-abertos"
SSP_INDICATORS_URL = "https://www.ssp.rs.gov.br/indicadores-criminais"
SSP_DICTIONARY_URL = "https://www.ssp.rs.gov.br/dicionario-de-dados"
SSP_BASE = "https://ssp.rs.gov.br"
TARGET_MUNICIPALITIES = ("GRAMADO", "CANELA")

PREFLIGHT_URLS = [
    DC_DOC_URL,
    SSP_OPEN_DATA_URL,
    SSP_INDICATORS_URL,
    SSP_DICTIONARY_URL,
]
