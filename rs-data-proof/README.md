# rs-data-proof — Prova de dados RS (Defesa Civil + SSP-RS)

Prova mínima, reproduzível e mensurável de que dados públicos oficiais do RS podem alimentar uma camada
confiável de inteligência operacional:

```
fonte oficial → download/API → RAW imutável (+sha256) → normalização → quality checks → métricas → outputs legíveis
```

Escopo desta rodada: **somente dados**. Sem GCP, Databricks, agente, MCP ou UI.
Resultado e evidências: [`reports/FINAL_DATA_PROOF.md`](reports/FINAL_DATA_PROOF.md).

## Fontes (somente oficiais, públicas, sem credenciais)
| fonte | uso |
|---|---|
| Defesa Civil RS — API GraphQL `https://redehidrometeorologica.defesacivil.rs.gov.br/graphql` (doc: `https://sistemas.defesacivil.rs.gov.br/api-redehidrometeorologica`) | `tags_data` (130 estações, snapshot atual) + `historic` (24 h, `MIN_5`) |
| SSP-RS — Dados abertos Lei 15.610/2021 `https://ssp.rs.gov.br/dados-abertos` | ZIP mais recente da "publicação mensal" (link descoberto na página a cada execução) |
| SSP-RS — Indicadores criminais `https://www.ssp.rs.gov.br/indicadores-criminais` | validação cruzada (agregados mensais por município) |

A consulta GraphQL **não é escrita à mão**: o texto é extraído dos blocos `<pre>` da documentação oficial a cada
execução e comparado com a cópia em `src/queries/` (drift é registrado; a versão da documentação prevalece).

## Como rodar

### Docker (recomendado)
```bash
docker build -t rs-data-proof .                      # roda os testes unitários no build
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/data:/app/data" -v "$PWD/reports:/app/reports" rs-data-proof
# ou: docker compose up --build
```
Exit code: `0` = as duas fontes processadas · `2` = parcial (uma falhou) · `1` = nada utilizável.

**Atrás de proxy HTTPS com inspeção TLS** (como o sandbox onde esta prova rodou), passe proxy e CA
explicitamente — o CA entra como *BuildKit secret* e nunca fica numa camada da imagem:
```bash
docker build --network host --build-arg HTTPS_PROXY="$HTTPS_PROXY" \
  --secret id=extra_ca,src=/path/to/ca-bundle.crt -t rs-data-proof .
docker run --rm --network host --user "$(id -u):$(id -g)" \
  -e HTTPS_PROXY="$HTTPS_PROXY" -e REQUESTS_CA_BUNDLE=/certs/ca.crt -v /path/to/ca-bundle.crt:/certs/ca.crt:ro \
  -v "$PWD/data:/app/data" -v "$PWD/reports:/app/reports" rs-data-proof
```

### Local
```bash
pip install -r requirements.txt
python -m pytest -q
python -m src.main
```

## Estrutura
```
src/
  config.py               URLs, limites, UA, constantes (sem credenciais)
  http.py                 timeouts, retries limitados, UA, validação de status/Content-Type, redirects, RAW+sha256
  fetch_defesa_civil.py   extrai consultas da doc, tags_data, historic, sonda do limite de 3 meses
  normalize_defesa_civil.py  achatamento, timestamps BRT→UTC, status oficial, freshness, confidence V0
  fetch_ssp.py            descoberta do link na página, download, extração segura do ZIP, indicadores
  normalize_ssp.py        parser do layout real (trios de vítima repetidos), flags de qualidade
  quality.py              métricas de qualidade (nunca corrige silenciosamente)
  metrics.py              métricas Gramado/Canela, validação cruzada, tabelas mensais, consultas DuckDB
  report.py               relatórios .md/.json, checks e decisão (regras explícitas em evaluate())
  main.py                 orquestração, run_manifest.json, exit code
tests/                    45 testes; fixtures são trechos literais dos RAW reais
data/raw/<fonte>/<data>/  RAW exatamente como recebido + <arquivo>.meta.json (url, status, bytes, sha256, latência)
data/curated/             Parquet/CSV curados
data/quarantine/          cópias de linhas/estações com flags (nada é apagado do curado)
reports/                  relatórios desta execução
```

## Outputs principais
`reports/FINAL_DATA_PROOF.md` · `defesa_civil_quality.md` · `defesa_civil_summary.json` · `ssp_schema.md` ·
`ssp_quality.md` · `sample_insights.md` · `duckdb_queries.md` · `run_manifest.json` · `run.log` · `terminal_summary.txt`

## Regras seguidas
* RAW nunca é sobrescrito com conteúdo diferente (vira `<nome>_<sha12>`); metadados ficam ao lado.
* Anomalias viram `quality_flags` (+ cópia em `data/quarantine/`); valores brutos preservados em colunas `*_raw`.
* "Ocorrências registradas"/"registros administrativos", nunca "crime real". Sem reidentificação, sem scoring
  individual; atributos de vítima só em agregados.
* `technical_data_confidence` é experimental e **não** é probabilidade de enchente; freshness é qualidade técnica,
  não risco hidrológico.
* Rate limit respeitado: 1 `tags_data` + 5 `historic` + 1 sonda por execução (limite oficial: 120 req/min/IP).

## Notas de versionamento do repositório
O CSV extraído da SSP (~123 MB) excede o limite do GitHub e está no `.gitignore`; ele é reproduzível a partir de
`data/raw/ssp/<data>/source.zip` (sha256 do ZIP e do CSV em `discovery.json` e `reports/run_manifest.json`).
Os dados são públicos; antes de redistribuí-los fora deste ambiente de prova, verificar os termos de uso das fontes.
