# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    RS_PROOF_ROOT=/app

WORKDIR /app
COPY requirements.txt .
# Optional extra CA (only for TLS-intercepting proxies). Passed as a BuildKit
# secret so it is NOT baked into any image layer:
#   docker build --secret id=extra_ca,src=/path/ca.crt ...
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export PIP_CERT=/run/secrets/extra_ca; fi; \
    pip install -r requirements.txt

COPY src/ src/
COPY tests/ tests/
# Unit tests run at build time: an image that fails its tests is never produced.
RUN python -m pytest -q tests

RUN useradd --create-home --uid 1000 app \
 && mkdir -p data/raw data/curated data/quarantine reports \
 && chown -R app:app /app
USER app

# data/ and reports/ are meant to be bind-mounted so RAW + outputs persist.
VOLUME ["/app/data", "/app/reports"]
CMD ["python", "-m", "src.main"]
