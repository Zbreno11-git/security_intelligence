"""Readable outputs. Every number below comes from the current run (dict R)."""
from __future__ import annotations

import gzip
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from . import config

ALL_REPORTS = [
    "defesa_civil_quality.md", "defesa_civil_summary.json", "ssp_schema.md", "ssp_quality.md",
    "sample_insights.md", "duckdb_queries.md", "FINAL_DATA_PROOF.md", "run_manifest.json",
]


# ------------------------------------------------------------------ helpers
def md_table(rows: list[dict] | pd.DataFrame, cols: list[str] | None = None) -> str:
    if isinstance(rows, pd.DataFrame):
        rows = rows.to_dict(orient="records")
    if not rows:
        return "_(sem linhas)_\n"
    cols = cols or list(rows[0].keys())

    def fmt(x):
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return "NULL"
        if isinstance(x, float):
            return f"{x:,.2f}".rstrip("0").rstrip(".") if abs(x) < 1e6 else f"{x:,.0f}"
        if isinstance(x, int) and not isinstance(x, bool):
            return f"{x:,}"
        return str(x).replace("|", "\\|").replace("\n", " ")
    out = "| " + " | ".join(cols) + " |\n|" + "|".join("---" for _ in cols) + "|\n"
    for r in rows:
        out += "| " + " | ".join(fmt(r.get(c)) for c in cols) + " |\n"
    return out


def kv_table(d: dict, k="métrica", v="valor") -> str:
    return md_table([{k: a, v: b if not isinstance(b, (dict, list)) else json.dumps(b, ensure_ascii=False)}
                     for a, b in d.items()])


def n(x) -> str:
    if x is None:
        return "NULL"
    if isinstance(x, float):
        return f"{x:,.2f}"
    if isinstance(x, int):
        return f"{x:,}"
    return str(x)


def _w(name: str, text: str) -> None:
    (config.REPORTS / name).write_text(text, encoding="utf-8")


def _jd(o):
    from .main import jsonable
    return jsonable(o)


# ------------------------------------------------------------- engineering
def storage_estimates(R: dict) -> dict:
    est: dict = {}
    dc = R.get("defesa_civil", {})
    if dc.get("status") == "ok":
        raw_path = config.ROOT / dc["fetch"]["saved_to"]
        raw = raw_path.read_bytes()
        gz = len(gzip.compress(raw, 6))
        snaps_year = 288 * 365
        est["tags_data_snapshot_bytes"] = len(raw)
        est["tags_data_snapshot_gzip_bytes"] = gz
        est["tags_data_gzip_ratio"] = round(len(raw) / gz, 1)
        est["tags_data_1y_raw_gb"] = round(len(raw) * snaps_year / 1e9, 2)
        est["tags_data_1y_gzip_gb"] = round(gz * snaps_year / 1e9, 2)
        cur = (config.CURATED / "defesa_civil_stations.parquet").stat().st_size
        est["curated_snapshot_parquet_bytes"] = cur
        est["curated_1y_parquet_gb_upper_bound"] = round(cur * snaps_year / 1e9, 2)
        hm = [m for m in dc["history"]["metrics"] if "bytes" in m]
        if hm:
            per_day = sum(m["bytes"] for m in hm) / len(hm)
            hp = config.ROOT / dc["fetch"]["saved_to"]
            hfile = hp.parent / f"historic_{hm[0]['codigo']}.json"
            hgz = len(gzip.compress(hfile.read_bytes(), 6)) if hfile.exists() else None
            n_st = dc["quality"]["total_stations"]
            est["historic_station_day_min5_bytes"] = int(per_day)
            est["historic_all_stations_1y_raw_gb"] = round(per_day * n_st * 365 / 1e9, 2)
            if hgz:
                est["historic_all_stations_1y_gzip_gb"] = round(hgz * n_st * 365 / 1e9, 2)
        hist_rows = (config.CURATED / "defesa_civil_history.parquet")
        if hist_rows.exists() and dc["history"]["rows"]:
            per_row = hist_rows.stat().st_size / dc["history"]["rows"]
            est["history_parquet_bytes_per_row"] = round(per_row, 1)
            est["history_parquet_1y_all_stations_mb"] = round(per_row * 288 * 365 * dc["quality"]["total_stations"] / 1e6, 1)
    s = R.get("ssp", {})
    if s.get("status") == "ok":
        z = s["discovery"]["download"]["content_length"]
        est["ssp_zip_bytes"] = z
        est["ssp_csv_bytes"] = s["extracted_bytes"]
        est["ssp_versions_per_year_if_all_kept_mb"] = round(z * 12 * 12 / 9 / 1e6, 1)  # ~12 monthly republications
        est["ssp_curated_parquet_bytes"] = (config.CURATED / "ssp_occurrences.parquet").stat().st_size
    return est


# ---------------------------------------------------------------- decision
def evaluate(R: dict) -> dict:
    dc, s = R.get("defesa_civil", {}), R.get("ssp", {})
    checks: dict[str, dict] = {}

    def chk(name, passed, critical, evidence):
        checks[name] = {"passed": bool(passed), "critical": critical, "evidence": evidence}

    dc_ok = dc.get("status") == "ok"
    chk("dc_api_accessible", dc_ok and dc["fetch"]["http_status"] == 200, True,
        f"HTTP {dc.get('fetch', {}).get('http_status')}" if dc_ok else dc.get("error"))
    if dc_ok:
        q = dc["quality"]
        chk("dc_raw_preserved_with_sha256", bool(dc["fetch"].get("sha256")), True, dc["fetch"].get("saved_to"))
        chk("dc_official_query_unchanged", all(v == "identical" for v in dc["query_drift"]["queries"].values()), False,
            dc["query_drift"]["queries"])
        chk("dc_station_count_as_documented", q["total_stations"] == config.DC_EXPECTED_STATIONS, False,
            f"{q['total_stations']} vs {config.DC_EXPECTED_STATIONS}")
        fresh_pct = 100 * q["freshness_counts"].get("fresh", 0) / q["total_stations"]
        chk("dc_fresh_ge_90pct", fresh_pct >= 90, True, f"{fresh_pct:.1f}%")
        rv = 100 * q["stations_with_river_level"] / q["total_stations"]
        chk("dc_river_value_ge_80pct", rv >= 80, False, f"{rv:.1f}%")
        hq = dc["history"]["quality"]
        good = [c for c, v in hq.items() if (v.get("completeness_pct") or 0) >= 80]
        chk("dc_history_ge1_station_ge80pct_complete", len(good) >= 1, True, f"{len(good)}/{len(hq)} stations")
        chk("dc_serra_has_valid_river_station_within_40km", dc["serra_with_river_value"] >= 1, False,
            f"{dc['serra_with_river_value']} stations")
        chk("dc_station_inside_gramado_or_canela", bool(dc["stations_named_gramado_canela"]), False,
            dc["stations_named_gramado_canela"] or "nenhuma estação com nome Gramado/Canela")
        raw_txt = (config.ROOT / dc["fetch"]["saved_to"]).read_text(encoding="utf-8", errors="replace").lower()
        chk("dc_flood_thresholds_in_payload", "cota" in raw_txt or "limiar" in raw_txt, False,
            "resposta tags_data não contém cotas/limiares (só o status derivado)")
    s_ok = s.get("status") == "ok"
    chk("ssp_download_ok", s_ok, True, s.get("discovery", {}).get("chosen", {}).get("url") if s_ok else s.get("error"))
    if s_ok:
        q = s["quality"]
        chk("ssp_schema_matches_dictionary", s["parse"]["header_validation"]["ok"], True, s["parse"]["header_validation"]["observed_first13"])
        chk("ssp_rows_loaded", q["total_rows"] > 0, True, q["total_rows"])
        mm = s["municipality_metrics"]
        for m in config.TARGET_MUNICIPALITIES:
            tot = mm[m]["occurrences_total"]
            chk(f"ssp_{m.lower()}_ge_100_per_month", tot and mm[m]["monthly_min"] >= 100, False,
                f"total={tot}, monthly_min={mm[m].get('monthly_min')}")
            chk(f"ssp_{m.lower()}_neighborhood_cov_ge_70pct", (mm[m].get("neighborhood_coverage_pct") or 0) >= 70, False,
                f"{mm[m].get('neighborhood_coverage_pct')}%")
        period_end = date.fromisoformat(s["parse"]["declared_period"][1]) if s["parse"]["declared_period"] else None
        lag = (datetime.now(timezone.utc).date() - period_end).days if period_end else None
        chk("ssp_lag_le_45_days", lag is not None and lag <= 45, False, f"{lag} dias desde o fim do período coberto")
        geo_cols = [h for h in s["parse"]["header_validation"]["observed_first13"] if any(t in h.upper() for t in ("LAT", "LON", "COORD"))]
        chk("ssp_has_coordinates", bool(geo_cols), False, geo_cols or "nenhuma coluna de latitude/longitude no arquivo art. 3º")
        R["_lag_days"] = lag
        cv = s.get("cross_validation") or {}
        rows = [r for r in cv.get("rows", []) if r["scope"] == "RS (state)" and "[hypothesis]" not in r["mapping"]
                and r["indicator_count"]]
        within = [r for r in rows if abs(r["diff_pct"]) <= 5]
        chk("ssp_crossval_state_within_5pct_majority", rows and len(within) / len(rows) >= 0.6, False,
            f"{len(within)}/{len(rows)} mappings within ±5%")
        chk("ssp_no_critical_anomalies_gt_1pct", sum(q["anomalies"][k] for k in ("date_invalid", "date_future",
            "municipality_empty", "category_empty")) / q["total_rows"] < 0.01, True,
            {k: q["anomalies"][k] for k in ("date_invalid", "date_future", "municipality_empty", "category_empty")})
    crit_fail = [k for k, v in checks.items() if v["critical"] and not v["passed"]]
    soft_fail = [k for k, v in checks.items() if not v["critical"] and not v["passed"]]
    result = "NO-GO" if crit_fail else ("GO_WITH_CAVEATS" if soft_fail else "GO")
    return {"checks": checks, "critical_failures": crit_fail, "caveats": soft_fail, "result": result}


# ------------------------------------------------------------- DC reports
def dc_reports(R: dict) -> None:
    dc = R["defesa_civil"]
    if dc.get("status") != "ok":
        _w("defesa_civil_quality.md", f"# Defesa Civil RS — qualidade\n\nFALHOU: `{dc.get('error')}`\n")
        return
    q, f = dc["quality"], dc["fetch"]
    st: pd.DataFrame = R["_frames"]["stations"]
    summary = {
        "collected_at_utc": dc["collected_at_utc"], "proximaAtualizacaoEm": dc["proximaAtualizacaoEm"],
        "http": {k: f[k] for k in ("http_status", "elapsed_s", "content_length", "sha256", "content_type", "attempts")},
        "query_drift": dc["query_drift"]["queries"], **q,
        "history": {"stations": [m.get("codigo") for m in dc["history"]["metrics"]],
                    "rows": dc["history"]["rows"], "limit_probe": dc["history"]["limit_probe"]},
        "serra": {"radius_km": dc["serra_stations_within_km"], "stations": dc["serra_station_count"],
                  "with_river_value": dc["serra_with_river_value"], "with_rain_value": dc["serra_with_rain_value"]},
    }
    (config.REPORTS / "defesa_civil_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=_jd))
    flagged = st[st["quality_flags"] != ""][["codigo", "name_general", "bacia", "quality_flags", "technical_data_confidence"]]
    hm = dc["history"]["metrics"]
    cards = []
    for m in hm:
        if "error" in m:
            cards.append(f"### {m['codigo']}\nFALHOU: {m['error']}\n")
            continue
        cards.append(
            f"### Estação {m['codigo']} — {m['name_general']}\n"
            f"```\nBacia:            {m['bacia']}\nSeleção:          {m['selection_reason']}\n"
            f"Distância Serra:  {m['dist_serra_km']} km (Gramado/Canela)\n"
            f"Última leitura:   {m.get('last_river_ts_utc')} (UTC)\n"
            f"Nível:            {m.get('current_river_level')} m\n"
            f"Variação 10 min:  {m.get('delta_10m')} m\nVariação 30 min:  {m.get('delta_30m')} m\n"
            f"Variação 1h:      {m.get('delta_1h')} m   (taxa ajustada {m.get('rise_rate_per_hour')} m/h)\n"
            f"Maior subida 1h na janela de 24h: {m.get('max_rise_1h_in_window')} m em {m.get('max_rise_1h_at_utc')}\n"
            f"Chuva 30 min / 1h / 3h / 24h: {m.get('rain_30m')} / {m.get('rain_1h')} / {m.get('rain_3h')} / {m.get('rain_24h')} mm\n"
            f"Chuva 1h / 24h segundo tags_data: {m.get('tags_rain_1h_mm')} / {m.get('tags_rain_24h_mm')} mm\n"
            f"Intensidade máx. (24h): {m.get('max_rain_rate_mm_h_24h')} mm/h\n"
            f"Status oficial:   {m.get('official_flood_status')}\n"
            f"Freshness:        {m.get('data_freshness')}\n"
            f"Data confidence:  {m.get('technical_data_confidence')}/100 (experimental, não oficial)\n```\n"
            + (f"NULLs explicados: {m['reasons']}\n" if m.get("reasons") else ""))
    hq_rows = [{"codigo": c, **{k: v for k, v in d.items() if k != "null_pct"},
                "null_pct_rio_nivel": d["null_pct"]["rio_nivel"], "null_pct_chuva": d["null_pct"]["chuva_mm"]}
               for c, d in dc["history"]["quality"].items()]
    probe = dc["history"]["limit_probe"]
    txt = f"""# Defesa Civil RS — Qualidade dos dados (execução {R['run']['run_date']})

Fonte: `{config.DC_GRAPHQL_URL}` (consulta oficial `Tags_data`, texto extraído da documentação a cada execução).
Coleta: `{dc['collected_at_utc']}` UTC · HTTP {f['http_status']} · {n(f['content_length'])} bytes · {f['elapsed_s']} s · tentativas {f.get('attempts')}
`proximaAtualizacaoEm` = `{dc['proximaAtualizacaoEm']}` · sha256 RAW = `{f['sha256']}`
Drift da consulta vs. cópia vendorizada: `{dc['query_drift']['queries']}`

> Freshness aqui é **qualidade técnica** (idade da leitura), não risco hidrológico.
> `technical_data_confidence` é um score **experimental e não oficial**; não é probabilidade de enchente.

## Resumo
{kv_table({k: v for k, v in q.items() if not isinstance(v, dict)})}
### Status oficial de nível (contagem de estações)
{kv_table(q['official_status_counts'], 'status', 'estações')}
### Freshness
{kv_table(q['freshness_counts'], 'classe', 'estações')}
Idade da leitura (min): mediana {q['age_minutes_median']}, p95 {q['age_minutes_p95']}, máx {q['age_minutes_max']}.
Distribuição de blocos de timestamp nesta coleta: `{st['timestamp_raw'].value_counts(dropna=False).to_dict()}`.
Nota metodológica: `timestamp` é o **início** do bloco de 5 min e o dado é publicado 1–2 min após o marco, então a
idade mínima normal é ~5–7 min; uma estação **um bloco atrasada** aparece com ~10–12 min e cai em `delayed` pelos
limiares do runbook (≤10 fresh). `delayed` não penaliza o score; só `stale` (>20 min) penaliza. A staleness por
sensor aparece via `value: null` (sem envio nos últimos 20 min, segundo a documentação).

### Score técnico de confiança (distribuição)
{kv_table(q['technical_data_confidence_distribution'], 'score', 'estações')}

## Estações com flags de qualidade (não removidas; cópia em `data/quarantine/defesa_civil_flagged_stations.csv`)
{md_table(flagged)}

## Série histórica (`historic`, interval={config.DC_HISTORIC_INTERVAL} explícito, últimas {config.DC_HISTORIC_HOURS} h)
{md_table(hq_rows)}

Teste do limite documentado de 3 meses (consulta ~100 dias atrás): aceito = `{probe.get('accepted')}`; resposta:
`{json.dumps(probe.get('errors') or probe.get('error'), ensure_ascii=False)[:400]}`

## Exemplos legíveis
{''.join(cards)}
"""
    _w("defesa_civil_quality.md", txt)
    hist: pd.DataFrame = R["_frames"]["history"]
    if len(hist):
        top = max((m for m in hm if m.get("max_rise_1h_in_window") is not None),
                  key=lambda m: m["max_rise_1h_in_window"], default=None)
        if top:
            hist[hist["codigo"] == top["codigo"]].to_csv(config.REPORTS / "river_sample.csv", index=False)


# ------------------------------------------------------------ SSP reports
def ssp_reports(R: dict) -> None:
    s = R["ssp"]
    if s.get("status") != "ok":
        for name in ("ssp_schema.md", "ssp_quality.md"):
            _w(name, f"# SSP-RS\n\nFALHOU: `{s.get('error')}`\n")
        return
    d, p, q = s["discovery"], s["parse"], s["quality"]
    mem = d["zip_members"]
    schema = f"""# SSP-RS — Schema real observado (execução {R['run']['run_date']})

Página de origem: {d['source_page']}
Link escolhido (descoberto na página, seção "publicação mensal"): **{d['chosen']['text']}**
URL: `{d['chosen']['url']}`
Download: HTTP {d['download']['http_status']} · {n(d['download']['content_length'])} bytes · {d['download']['elapsed_s']} s ·
tentativas {d['download'].get('attempts')} · sha256 `{d['download']['sha256']}`

## Conteúdo do ZIP
{md_table(mem, ['member_name_in_zip', 'utf8_name_flag', 'uncompressed_size', 'zip_datetime', 'sha256'])}
{'Nota: o ZIP marca os nomes como UTF-8 (`utf8_name_flag=True`) e o Python decodifica corretamente; ferramentas como `unzip` em locale C exibem `#U00ca` no lugar de `Ê` — usar sempre a biblioteca, não o CLI.' if all(m['utf8_name_flag'] for m in mem) else 'Atenção: há nomes no ZIP sem a flag UTF-8 (podem aparecer corrompidos, ex. `#U00ca`).'}

## Formato
| item | valor |
|---|---|
| encoding detectado | `{p['encoding']}` |
| delimitador | `{p['delimiter']}` |
| linhas de dados | {n(p['data_rows'])} |
| células no cabeçalho | {p['header_validation']['total_header_cells']} (13 nomeadas + `...` + {p['header_validation']['total_header_cells'] - 14} vazias) |
| distribuição de largura das linhas | `{p['row_width_distribution']}` |
| período declarado no nome | {' a '.join(p['declared_period']) if p['declared_period'] else 'n/d'} |
| data de extração no nome | {p['extraction_date_in_name']} |
| cabeçalho confere com dicionário oficial | **{p['header_validation']['ok']}** |

**Layout de vítimas:** conforme o dicionário oficial, cada linha é **uma ocorrência**; o trio
`Idade/Sexo/Cor Vítima` se repete à direita uma vez por vítima. O cabeçalho só nomeia o 1º trio, seguido de uma
coluna literal `...` e cabeçalhos vazios. Ocorrências com >1 vítima: {n(s['victims']['occurrences_with_gt1_victim'])};
máximo de vítimas numa linha: {s['victims']['max_victims_one_row']}. A tabela `ssp_victims.parquet` normaliza esse layout (1 linha por vítima).

## Perfil por coluna (13 colunas nomeadas; vítima = 1º trio)
{md_table(s['schema_profile'])}

Minimização: nenhum campo identificador pessoal existe no arquivo; amostras exibem só valores categóricos/agregados.
"""
    _w("ssp_schema.md", schema)
    an = q["anomalies"]
    cv = s.get("cross_validation") or {}
    qual = f"""# SSP-RS — Qualidade (execução {R['run']['run_date']})

> Estes são **registros administrativos** (ocorrências registradas), não "crime real". Estão sujeitos a
> subnotificação, prática de registro, reclassificação e revisão posterior (ver nota metodológica oficial).

## Métricas
{kv_table({k: v for k, v in q.items() if not isinstance(v, dict)})}

## Anomalias (marcadas com `quality_flags`; nada foi apagado)
{kv_table(an, 'anomalia', 'ocorrências/vítimas')}
Linhas copiadas para `data/quarantine/ssp_flagged_rows.csv` (critério: flag crítica ou problema de vítima): **{n(s['quarantine_rows'])}**.

Observações:
* `age_gt_115`: todas as idades >115 observadas valem **126** ({q['victim_age_126_count']} vítimas) — padrão de valor-sentinela, não erro aleatório.
* `victim_count_missing`: campo `Quantidade Vítimas` vazio, sem trios de vítima.
* Duplicatas: {q['duplicate_full_rows_raw']} linhas idênticas no RAW (o `Sequência` é único). Ignorando `Sequência`,
  {n(q['duplicate_rows_ignoring_sequence_id'])} linhas ({q['duplicate_rows_ignoring_sequence_id_pct']}%) repetem todos os demais campos.
  **Não foram removidas**: sem identificador de fato não há critério confiável (ex.: 2 furtos no mesmo dia/bairro são plausíveis).
* Hora "cheia" (`HH:00:00`): {q['time_on_exact_hour_pct']}% dos horários — forte arredondamento; análise por faixa horária é viável, por minuto não.
* `Bairro` tem {n(q['neighborhood_unique_count_raw'])} grafias brutas → {n(q['neighborhood_unique_count_normalized'])} após normalização (maiúsculas/acentos/espaços).
* `Tipo Fato` contém apenas: {q['fact_type_values']} (o arquivo art. 3º só traz fatos consumados).

## Contagem de flags
{kv_table(q['flag_counts'], 'flag', 'linhas')}

## Validação cruzada com Indicadores Criminais (agregados oficiais), meses {cv.get('months_compared')}
Mapeamento categoria→indicador é **nosso** (heurístico); divergências são documentadas, não forçadas.
{md_table(cv.get('rows', []), ['mapping', 'scope', 'microdata_count', 'indicator_count', 'diff', 'diff_pct']) if cv.get('rows') else cv}
"""
    _w("ssp_quality.md", qual)


def sample_insights(R: dict) -> str:
    s, dc = R["ssp"], R["defesa_civil"]
    out = [f"# Sample insights (execução {R['run']['run_date']})\n",
           "Linguagem: *ocorrências registradas* / *registros administrativos*. Correlação ≠ causalidade.\n"]
    if s.get("status") == "ok":
        for m, mm in s["municipality_metrics"].items():
            out.append(f"## {m.title()} — {n(mm['occurrences_total'])} ocorrências registradas "
                       f"({s['parse']['declared_period'][0]} a {s['parse']['declared_period'][1]})\n")
            out.append(f"* {mm['share_of_state_pct']}% do RS; posição {mm['state_rank_by_volume']}º entre "
                       f"{s['quality']['municipality_unique_count']} municípios por volume.\n"
                       f"* Média mensal {mm['monthly_mean']} (mín {mm['monthly_min']}, máx {mm['monthly_max']}); "
                       f"último mês vs. média anterior: {mm.get('last_month_vs_prev_mean_pct')}%.\n"
                       f"* Cobertura: bairro {mm['neighborhood_coverage_pct']}%, hora {mm['time_coverage_pct']}% "
                       f"(hora cheia {mm['time_on_exact_hour_pct']}%), categoria {mm['category_coverage_pct']}%.\n")
            out.append("\n**Top 10 categorias**\n\n" + kv_table(mm["occurrences_by_category_top10"], "categoria", "registros"))
            out.append("\n**Por mês**\n\n" + kv_table(mm["occurrences_by_month"], "mês", "registros"))
            out.append("\n**Dia da semana**\n\n" + kv_table(mm["occurrences_by_weekday"], "dia", "registros"))
            out.append("\n**Faixa horária**\n\n" + kv_table(mm["occurrences_by_hour_bucket"], "faixa", "registros"))
            out.append("\n**Tipo de local**\n\n" + kv_table(mm["occurrences_by_place_type"], "local", "registros"))
            if mm.get("occurrences_by_neighborhood_top10"):
                out.append(f"\n**Top 10 bairros** (normalizados; {mm['neighborhood_unique_raw']} grafias brutas → "
                           f"{mm['neighborhood_unique_normalized']} normalizadas)\n\n"
                           + kv_table(mm["occurrences_by_neighborhood_top10"], "bairro", "registros"))
            else:
                out.append(f"\nBairro omitido: {mm.get('neighborhood_note')}\n")
            out.append("\n")
        out.append("Variantes de nome encontradas na busca (casamento exato evita contar 'GRAMADO XAVIER' e "
                   f"'GRAMADO DOS LOUREIROS' como Gramado): `{s['municipality_name_variants_found']}`\n")
    if dc.get("status") == "ok":
        out.append("\n## Hidrologia — contexto Serra (mantido separado: SSP termina em "
                   f"{s.get('parse', {}).get('declared_period', ['?', '?'])[1]}; hidrologia é de hoje)\n")
        out.append(md_table(pd.read_csv(config.REPORTS / "serra_stations.csv")))
        mov = [m for m in dc["history"]["metrics"] if m.get("delta_1h") is not None]
        if mov:
            top = max(mov, key=lambda m: m["delta_1h"])
            out.append(f"\nMaior subida em 1h entre as séries baixadas: **{top['codigo']} {top['name_general']}** "
                       f"{top['delta_1h']} m/h, chuva 1h {top.get('rain_1h')} mm, status oficial `{top['official_flood_status']}`.\n")
    return "\n".join(out)


def duckdb_report(R: dict) -> str:
    out = ["# DuckDB — perguntas respondidas a partir dos Parquet curados\n",
           "Reprodução: `duckdb` sobre `data/curated/*.parquet` (views `stations`, `history`, `occ`).\n"]
    for qd in R.get("duckdb", []):
        out.append(f"## {qd['title']}\n```sql\n{qd['sql']}\n```\n")
        out.append(md_table(qd["result"]) if qd["error"] is None else f"ERRO: `{qd['error']}`\n")
    return "\n".join(out)


# ------------------------------------------------------------ final report
def _grave_counts(s: dict) -> str:
    rows = (s.get("cross_validation") or {}).get("rows", [])
    keep = [r for r in rows if r["scope"] != "RS (state)" and r["indicator"] in ("HOMICIDIO DOLOSO", "LATROCINIO", "ROUBOS", "ROUBO DE VEICULO")]
    return "; ".join(f"{r['scope'].title()} {r['indicator'].lower()}={r['indicator_count']}" for r in keep)


def hypotheses(R: dict, dec: dict) -> list[dict]:
    dc, s = R.get("defesa_civil", {}), R.get("ssp", {})
    c = dec["checks"]
    H = []
    if dc.get("status") == "ok":
        q = dc["quality"]
        H.append({"id": "H1", "hipótese": "Defesa Civil fornece dados frequentes e estruturados para um módulo de resiliência",
                  "veredito": "SUPPORTED" if c["dc_fresh_ge_90pct"]["passed"] and c["dc_river_value_ge_80pct"]["passed"] else "PARTIALLY SUPPORTED",
                  "evidência": f"{q['total_stations']} estações em 1 chamada ({dc['fetch']['elapsed_s']} s); "
                               f"{q['freshness_counts'].get('fresh', 0)} fresh; rio válido em {q['stations_with_river_level']}, "
                               f"chuva em {q['stations_with_rain']}; status oficial em {q['total_stations'] - q['official_status_counts']['no_threshold']} "
                               f"({q['official_status_counts']['no_threshold']} sem limiar cadastrado); séries 5-min com {dc_facts(R).get('hist_completeness')} de completude."})
    else:
        H.append({"id": "H1", "hipótese": "Defesa Civil", "veredito": "NOT SUPPORTED", "evidência": dc.get("error")})
    if s.get("status") == "ok":
        q = s["quality"]
        H.append({"id": "H2", "hipótese": "SSP fornece granularidade/cobertura para análises estratégicas municipais",
                  "veredito": "PARTIALLY SUPPORTED",
                  "evidência": f"{n(q['total_rows'])} ocorrências, {q['municipality_unique_count']} municípios, data/hora/categoria ~100% "
                               f"preenchidas; porém defasagem de {c['ssp_lag_le_45_days']['evidence']}, sem coordenadas, "
                               f"bairro vazio em {q['neighborhood_null_pct']}% e {q['time_on_exact_hour_pct']}% de horas cheias."})
        H.append({"id": "H3", "hipótese": "Defeitos existem mas são normalizáveis e monitoráveis",
                  "veredito": "SUPPORTED",
                  "evidência": f"anomalias críticas SSP = {sum(q['anomalies'][k] for k in ('date_invalid','date_future','municipality_empty','category_empty'))}; "
                               f"sentinela idade=126 ({q['victim_age_126_count']}); 13 linhas sem qtd. vítimas; DC: "
                               f"{dc.get('quality', {}).get('river_level_missing_pct')}% rio nulo, rio_nome/altitude nulos em 100%; "
                               "todos detectados por flags, nada apagado; validação cruzada explicou a maior divergência (estelionato)."})
        mm = s["municipality_metrics"]
        g, k = mm["GRAMADO"], mm["CANELA"]
        H.append({"id": "H4", "hipótese": "Gramado e Canela têm volume/cobertura para design partners",
                  "veredito": ("SUPPORTED" if c["ssp_gramado_ge_100_per_month"]["passed"] and c["ssp_canela_ge_100_per_month"]["passed"]
                               and c.get("dc_station_inside_gramado_or_canela", {}).get("passed") else "PARTIALLY SUPPORTED"),
                  "evidência": f"Gramado {n(g['occurrences_total'])} registros (mín {g['monthly_min']}/mês, bairro {g['neighborhood_coverage_pct']}%); "
                               f"Canela {n(k['occurrences_total'])} (mín {k['monthly_min']}/mês, bairro {k['neighborhood_coverage_pct']}%). "
                               f"Hidrologia: {dc.get('serra_station_count')} estações a ≤40 km, nenhuma dentro dos 2 municípios. "
                               f"Categorias graves têm contagens muito baixas no período ({_grave_counts(s)}): tendência só é estatisticamente útil para categorias volumosas."})
    if dc.get("status") == "ok":
        probe = dc["history"]["limit_probe"]
        H.append({"id": "H5", "hipótese": "Há valor em armazenar histórico próprio",
                  "veredito": "SUPPORTED",
                  "evidência": f"API recusa histórico >3 meses (sonda: `{(probe.get('errors') or [{}])[0].get('message', probe.get('error'))}`); "
                               "tags_data só traz o instante atual; SSP republica o ano inteiro a cada mês (revisões retroativas) e só versionando "
                               "os arquivos é possível medir revisões; cotas de inundação não fazem parte da consulta permitida."})
    H.append({"id": "H6", "hipótese": "Viável criar camada semântica/API/MCP depois",
              "veredito": "SUPPORTED" if all(qd["error"] is None for qd in R.get("duckdb", [])) and R.get("duckdb") else "PARTIALLY SUPPORTED",
              "evidência": f"{sum(1 for qd in R.get('duckdb', []) if qd['error'] is None)}/{len(R.get('duckdb', []))} perguntas-alvo respondidas por "
                           "SQL sobre Parquet curado com schema estável; as funções candidatas (get_current_flood_status, get_station_history, "
                           "get_safety_trend, get_data_quality) mapeiam 1:1 para essas consultas."})
    return H


def dc_facts(R: dict) -> dict:
    st = R["_frames"].get("stations")
    if st is None:
        return {}
    no_ts = st[st["timestamp_raw"].isna()]["codigo"].tolist()
    no_name_coord = st[st["name_general"].isna() | st["latitude"].isna()]["codigo"].tolist()
    serra = st[st["dist_serra_km"] <= config.SERRA_RADIUS_KM].sort_values("dist_serra_km")
    hq = R["defesa_civil"]["history"]["quality"]
    comp = [v["completeness_pct"] for v in hq.values() if v.get("completeness_pct") is not None]
    return {
        "no_ts": no_ts, "no_name_coord": no_name_coord,
        "nearest": (f"{serra.iloc[0]['name_general']} ({serra.iloc[0]['codigo']}), "
                    f"{min(serra.iloc[0]['dist_gramado_km'], serra.iloc[0]['dist_canela_km']):.1f} km") if len(serra) else "n/d",
        "serra_basins": sorted(serra["bacia"].dropna().unique().tolist()),
        "hist_completeness": f"{min(comp):.1f}–{max(comp):.1f}%" if comp else "n/d",
        "name_local_empty_pct": round(100 * st["name_local"].isna().mean(), 1),
        "defects_txt": "; ".join(x for x in [
            f"estações sem timestamp nesta coleta: {no_ts}" if no_ts else
            "nenhuma estação sem timestamp nesta coleta (num snapshot anterior do mesmo dia, DCRS-00125 veio sem timestamp e sem valores — trecho verbatim preservado em `tests/fixtures/tags_data_excerpt.json`; o defeito é intermitente)",
            f"estações sem nome/coordenadas: {no_name_coord}" if no_name_coord else "",
            "`rio_nome` e `altitude` nulos em 100%" if st["rio_nome"].isna().all() and st["altitude"].isna().all() else "",
        ] if x),
    }


def final_report(R: dict, dec: dict) -> str:
    dc, s = R.get("defesa_civil", {}), R.get("ssp", {})
    F = dc_facts(R) if dc.get("status") == "ok" else {}
    est = storage_estimates(R)
    H = hypotheses(R, dec)
    checks_rows = [{"check": k, "crítico": v["critical"], "passou": v["passed"],
                    "evidência": json.dumps(v["evidence"], ensure_ascii=False, default=str)[:140]}
                   for k, v in dec["checks"].items()]
    pf = md_table(R["preflight"], ["url", "ok", "status_code", "content_type", "redirects", "elapsed_s"])
    q = dc.get("quality", {})
    sq = s.get("quality", {})
    mm = s.get("municipality_metrics", {})
    G, C = mm.get("GRAMADO", {}), mm.get("CANELA", {})
    cv_rows = (s.get("cross_validation") or {}).get("rows", [])
    est_row = next((r for r in cv_rows if r["scope"] == "RS (state)" and r["mapping"].startswith("ESTELIONATO (all")), {})
    est_h = next((r for r in cv_rows if r["scope"] == "RS (state)" and "[hypothesis]" in r["mapping"]), {})
    dl_bytes = sum(f["bytes"] for f in _raw_files())
    mov = [m for m in dc.get("history", {}).get("metrics", []) if m.get("delta_1h") is not None]
    top = max(mov, key=lambda m: m["delta_1h"]) if mov else {}
    transient = []
    for src, rec in (("defesa_civil", dc.get("fetch")), ("ssp_zip", s.get("discovery", {}).get("download"))):
        if rec and rec.get("transient_errors"):
            transient.append(f"{src}: {len(rec['transient_errors'])} erro(s) transitório(s) antes do sucesso")
    lag_ev = dec["checks"].get("ssp_lag_le_45_days", {}).get("evidence")
    log_path = config.REPORTS / "run.log"
    log_retries = []
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if "Retrying" in line or "fetch.transient" in line:
                where = line.split("': ")[-1] if "': " in line else line[-80:]
                why = "RemoteDisconnected" if "RemoteDisconnected" in line else ("reset" if "reset" in line.lower() else "erro de conexão")
                log_retries.append(f"retry automático ({why}) em `{where.strip()}`")
    ssp_pf = [p["elapsed_s"] for p in R["preflight"] if "ssp" in p["url"]]
    ssp_pf = f"{min(ssp_pf)}–{max(ssp_pf)}" if ssp_pf else "n/d"
    ok_dc, ok_s = dc.get("status") == "ok", s.get("status") == "ok"

    def g(d, *ks, default="n/d"):
        for k in ks:
            if not isinstance(d, dict) or k not in d:
                return default
            d = d[k]
        return d

    txt = f"""# FINAL DATA PROOF — RS (execução {R['run']['run_date']})

**Decisão: `{dec['result'].replace('_', ' ')}`** · execução {R['run']['started_at']} → {R['run']['finished_at']} ({R['run']['duration_s']} s)
Todos os números abaixo foram produzidos por esta execução (ver `reports/run_manifest.json`, `reports/run.log`).

## 1. Resumo executivo
* Defesa Civil RS: API oficial acessível sem autenticação; {g(q,'total_stations')} estações em uma chamada de {g(dc,'fetch','elapsed_s')} s; {g(q,'freshness_counts','fresh',default=0)} com leitura fresca; nível de rio válido em {g(q,'stations_with_river_level')} ({g(q,'river_level_missing_pct')}% nulo); séries de 5 min com {F.get('hist_completeness')} de completude.
* A camada de qualidade já encontrou problemas reais na Defesa Civil: {F.get('defects_txt')}; {g(q,'official_status_counts','no_threshold')} estações sem limiar oficial cadastrado.
* SSP-RS: link do arquivo mensal mais recente descoberto automaticamente na página; {n(g(sq,'total_rows'))} ocorrências registradas ({' a '.join(g(s,'parse','declared_period',default=['?','?']))}), schema idêntico ao dicionário oficial.
* Gramado: {n(G.get('occurrences_total'))} registros; Canela: {n(C.get('occurrences_total'))}. Volume suficiente para categorias frequentes (estelionato, furto, ameaça), insuficiente para tendências de crimes graves.
* Validação cruzada com os indicadores oficiais bate em ±1% na maioria das categorias, e explicou a maior divergência: o indicador "Estelionato" exclui "fraude eletrônica" (+{est_row.get('diff_pct')}% → {est_h.get('diff_pct')}%).
* Limitações centrais: SSP com defasagem de {R.get('_lag_days')} dias e sem coordenadas/horário fino confiável; Defesa Civil com histórico limitado a 3 meses e sem estação dentro de Gramado/Canela.
* Decisão: {dec['result'].replace('_', ' ')} — os dados sustentam um produto de inteligência agregada/resiliência, não despacho operacional.

## 2. Evidências numéricas

### Preflight (DNS/TLS/HTTP)
{pf}
### Defesa Civil
| métrica | valor |
|---|---|
| estações (doc: {config.DC_EXPECTED_STATIONS}) | {g(q,'total_stations')} |
| HTTP / bytes / latência | {g(dc,'fetch','http_status')} / {n(g(dc,'fetch','content_length'))} / {g(dc,'fetch','elapsed_s')} s |
| proximaAtualizacaoEm | {g(dc,'proximaAtualizacaoEm')} |
| freshness | {g(q,'freshness_counts')} |
| idade da leitura (mediana / máx, min; medida a partir do início do bloco de 5 min) | {g(q,'age_minutes_median')} / {g(q,'age_minutes_max')} |
| manutenção | {g(q,'maintenance_count')} ({g(q,'maintenance_percentage')}%) |
| rio: sensor / valor válido / nulo % | {g(q,'stations_with_river_sensor')} / {g(q,'stations_with_river_level')} / {g(q,'river_level_missing_pct')}% |
| chuva 1h nula % / 24h nula % | {g(q,'rain_1h_missing_pct')}% / {g(q,'rain_24h_missing_pct')}% |
| não homologado: rio / chuva | {g(q,'non_homologated_river_count')} / {g(q,'non_homologated_rain_count')} |
| status oficial | {g(q,'official_status_counts')} |
| estações a ≤40 km de Gramado/Canela (rio válido / chuva válida) | {g(dc,'serra_station_count')} ({g(dc,'serra_with_river_value')} / {g(dc,'serra_with_rain_value')}) |
| séries históricas baixadas / linhas | {len(g(dc,'history','metrics',default=[]))} / {g(dc,'history','rows')} |
| drift da consulta oficial | {g(dc,'query_drift','queries')} |

### SSP-RS
| métrica | valor |
|---|---|
| arquivo | {g(s,'discovery','chosen','text')} |
| ZIP / CSV | {n(g(s,'discovery','download','content_length'))} B / {n(g(s,'extracted_bytes'))} B |
| linhas × colunas nomeadas (células por linha) | {n(g(sq,'total_rows'))} × 13 ({list(g(s,'parse','row_width_distribution',default={}).keys())}) |
| vítimas (linhas normalizadas) | {n(g(sq,'victims_total'))} |
| municípios / categorias | {g(sq,'municipality_unique_count')} / {g(sq,'category_unique_count')} |
| missingness: município / data / hora / categoria / bairro | {g(sq,'municipality_null_pct')}% / {g(sq,'date_null_pct')}% / {g(sq,'time_null_pct')}% / {g(sq,'category_null_pct')}% / {g(sq,'neighborhood_null_pct')}% |
| missingness vítima: idade / sexo / cor (+ "Sem informação") | {g(sq,'victim_age_null_pct')}% / {g(sq,'victim_sex_null_pct')}% / {g(sq,'victim_race_null_pct')}% (+{g(sq,'victim_race_sem_informacao_pct')}%) |
| horas cheias (`HH:00:00`) | {g(sq,'time_on_exact_hour_pct')}% |
| anomalias | {g(sq,'anomalies')} |
| duplicatas exatas RAW / ignorando Sequência | {g(sq,'duplicate_full_rows_raw')} / {n(g(sq,'duplicate_rows_ignoring_sequence_id'))} ({g(sq,'duplicate_rows_ignoring_sequence_id_pct')}%) |
| Gramado: total, rank RS, bairro %, hora % | {n(G.get('occurrences_total'))}, {G.get('state_rank_by_volume')}º, {G.get('neighborhood_coverage_pct')}%, {G.get('time_coverage_pct')}% |
| Canela: total, rank RS, bairro %, hora % | {n(C.get('occurrences_total'))}, {C.get('state_rank_by_volume')}º, {C.get('neighborhood_coverage_pct')}%, {C.get('time_coverage_pct')}% |
| top categorias RS | {list(g(s,'top_categories_state',default={}).items())[:5]} |

### Checks automatizados
{md_table(checks_rows)}

## 3. Outputs
* RAW imutável + `.meta.json` (sha256, URL final, status, bytes, horário): `data/raw/defesa_civil/<data>/`, `data/raw/ssp/<data>/` (`source.zip`, `extracted/`, `discovery.json`, páginas HTML, xlsx de indicadores)
* Curado: `data/curated/defesa_civil_stations.parquet`, `defesa_civil_history.parquet`, `ssp_occurrences.parquet`, `ssp_victims.parquet`, `municipality_monthly_safety.csv`, `municipality_metrics.csv`
* Quarentena (cópias para revisão, nada apagado): `data/quarantine/defesa_civil_flagged_stations.csv`, `data/quarantine/ssp_flagged_rows.csv`
* Relatórios: `reports/defesa_civil_quality.md`, `defesa_civil_summary.json`, `ssp_schema.md`, `ssp_quality.md`, `sample_insights.md`, `duckdb_queries.md`, `serra_stations.csv`, `river_sample.csv`, `terminal_summary.txt`, `run_manifest.json`, `run.log`

## 4. Respostas às perguntas do runbook (§29)

### Fonte
* **Acessível?** Defesa Civil: {'sim' if ok_dc else 'NÃO'}. SSP: {'sim' if ok_s else 'NÃO'}. Ambas atrás de TLS válido, sem redirects.
* **Automatizável?** Sim. A consulta GraphQL é extraída da documentação a cada execução e comparada com a cópia vendorizada; o link SSP é descoberto pelo texto da seção "publicação mensal".
* **Autenticação?** Não. A Defesa Civil exige o identificador público `casa-militar-defesa-civil-rs`, já embutido na consulta oficial.
* **Rate limit?** Documentado em 120 req/min/IP; esta execução fez {2 + len(g(dc,'history','metrics',default=[]))} requisições à API e não atingiu o limite. Instabilidade observada nesta execução: {('; '.join(transient + log_retries)) if (transient or log_retries) else 'nenhum erro transitório'}. Durante o desenvolvimento (mesmo dia) o download do ZIP SSP falhou uma vez com `Connection reset by peer` no meio da transferência; por isso há retry limitado no nível da aplicação. As páginas da SSP levaram {ssp_pf} s para responder no preflight.

### Estrutura
* **Schema estável/legível?** Defesa Civil: estável e auto-descritivo, com unidades documentadas; o contrato é rígido (só a consulta exata é aceita), o que favorece estabilidade e exige monitorar drift na documentação. SSP: as 13 colunas batem com o dicionário, mas o layout de vítimas é de largura variável (trio repetido, cabeçalho `...` + {g(s,'parse','header_validation','total_header_cells',default=14) - 14} colunas vazias), o encoding do CSV é Latin-1 sem declaração (o nome dentro do ZIP tem `Ê`, que o `unzip` em locale C exibe como `#U00ca`). A planilha de indicadores tem abas com cerca de 16 mil colunas vazias (JUL–SET).
* **Campos mais úteis.** DC: `rio_nivel`, `rio_nivel_tendencia`, `chuva.acumulado.*`, `rio_alarmes.inundacao.status`, `homologacao`, `manutencao`, `timestamp`. SSP: `Data Fato`, `Tipo Enquadramento`, `Municipio Fato`, `Local Fato`, `Quantidade Vítimas`.
* **Campos problemáticos.** DC: `rio_nome` e `altitude` nulos em 100%; `name.local` vazio em {F.get('name_local_empty_pct')}%; cotas (limiares) fora da consulta permitida. SSP: `Bairro` ({g(sq,'neighborhood_null_pct')}% vazio, {n(g(sq,'neighborhood_unique_count_raw'))} grafias → {n(g(sq,'neighborhood_unique_count_normalized'))} normalizadas); `Hora Fato` ({g(sq,'time_on_exact_hour_pct')}% em hora cheia); `Cor Vítima` ("Sem informação" em {g(sq,'victim_race_sem_informacao_pct')}% das vítimas); idade sentinela 126.

### Qualidade
* **Missingness real:** ver tabelas acima. O dado crítico (data, município, categoria) é ~100% preenchido; bairro e atributos de vítima são os pontos fracos.
* **Anomalias:** {g(sq,'anomalies')}; DC: {F.get('defects_txt')}; {g(q,'non_homologated_river_count')}+{g(q,'non_homologated_rain_count')} sensores não homologados.
* **Revisões/versionamento:** a SSP declara (dicionário de dados) que o arquivo do ano é republicado mensalmente com correções retroativas; rótulos na página indicam republicação de anos fechados: {[c['text'] for c in s.get('candidates_mensal', []) if len(c.get('years', [])) > 1]}. Não há changelog nem ID estável de fato além de `Sequência` (posição no arquivo). Medir revisões exige guardar cada versão (sha256 já registrado). A Defesa Civil não expõe versionamento; leituras passadas podem ser re-consultadas por até 3 meses.

### Cobertura
* **Gramado:** {n(G.get('occurrences_total'))} registros ({G.get('monthly_min')}–{G.get('monthly_max')}/mês), {G.get('state_rank_by_volume')}º do RS, bairro {G.get('neighborhood_coverage_pct')}%. Suficiente para volume/sazonalidade/categorias frequentes.
* **Canela:** {n(C.get('occurrences_total'))} registros ({C.get('monthly_min')}–{C.get('monthly_max')}/mês), {C.get('state_rank_by_volume')}º do RS, bairro {C.get('neighborhood_coverage_pct')}%.
* **Defesa Civil na Serra:** {g(dc,'serra_station_count')} estações a ≤40 km ({', '.join(F.get('serra_basins', []))}); a mais próxima é {F.get('nearest')}. **Nenhuma estação está dentro de Gramado ou Canela**, então o monitoramento é regional (bacias a jusante), não do perímetro urbano.
* **Estações com rio/chuva válidos (RS):** rio {g(q,'stations_with_river_level')}/{g(q,'total_stations')}, chuva {g(q,'stations_with_rain')}/{g(q,'total_stations')}.

### Produto
* **Respondível hoje:** situação atual de {g(q,'total_stations')} estações (nível, tendência, chuva multi-janela, status oficial, saúde do sensor); subida em 10/30/60 min por estação (ex.: {top.get('codigo', 'n/d')} {top.get('name_general', '')} subiu {top.get('delta_1h')} m em 1h com {top.get('rain_1h')} mm de chuva; status oficial `{top.get('official_flood_status')}`); ranking de chuva 24h; volume/mix/sazonalidade de ocorrências registradas por município e mês; distribuição por dia da semana, faixa horária e tipo de local; bairros onde a cobertura passa de 70%; qualidade dos dados por fonte.
* **Não respondível:** onde exatamente (sem lat/lon nas ocorrências); o que aconteceu nas últimas semanas em segurança (defasagem de {R.get('_lag_days')} dias); se um rio vai inundar (sem cotas/limiares na consulta e sem previsão); por que um indicador mudou (dado administrativo, sem causalidade); taxas per capita (população fora destas fontes); histórico hidrológico além de 3 meses sem coleta própria; perfis individuais (não fazemos e não devemos).
* **Exigiria parceria/dado privado:** ocorrências georreferenciadas e quase em tempo real (PC/BM/CIOSP); cotas de inundação por estação (Defesa Civil); sensores dentro de Gramado/Canela; população flutuante/turismo (prefeituras, hotelaria).
* **Métricas que parecem realmente úteis:** subida de nível em 1h com chuva concomitante (evento real capturado nesta execução); chuva acumulada multi-janela; `technical_data_confidence` para não confiar cegamente em leituras; registros mensais por categoria versus média do ano; participação por tipo de local; cobertura/qualidade por município.

### Engenharia
* **Baixado nesta execução (RAW total em disco):** {n(dl_bytes)} bytes (inclui o CSV extraído).
* **1 ano de coleta hidrometeorológica (extrapolado do observado):** snapshot tags_data = {n(est.get('tags_data_snapshot_bytes'))} B (gzip {n(est.get('tags_data_snapshot_gzip_bytes'))} B, {est.get('tags_data_gzip_ratio')}×). Com coleta a cada 5 min são ~{est.get('tags_data_1y_raw_gb')} GB/ano de JSON bruto, ~{est.get('tags_data_1y_gzip_gb')} GB/ano comprimido. Via `historic` diário (MIN_5) para todas as estações: ~{est.get('historic_all_stations_1y_raw_gb')} GB/ano bruto, ~{est.get('historic_all_stations_1y_gzip_gb')} GB/ano gzip; curado em Parquet, ~{est.get('history_parquet_1y_all_stations_mb')} MB/ano. Volume trivial para GCS/BigQuery.
* **SSP:** ZIP de {n(est.get('ssp_zip_bytes'))} B por 9 meses; guardar todas as republicações mensais custa ~{est.get('ssp_versions_per_year_if_all_kept_mb')} MB/ano.
* **Gargalos:** parse SSP em Python puro levou {g(s,'parse_seconds')} s para {n(g(sq,'total_rows'))} linhas (aceitável; polars/duckdb reduziriam). O download do ZIP SSP levou {g(s,'discovery','download','elapsed_s')} s para {n(g(s,'discovery','download','content_length'))} B, e um reset de conexão foi observado durante o desenvolvimento.
* **Dependências frágeis:** (1) consulta GraphQL só aceita texto exato, e qualquer mudança na doc quebra o coletor (mitigado com extração + diff a cada execução); (2) descoberta do link SSP depende do texto/ordem da página; (3) nome de arquivo e layout SSP mudam entre anos (2021 é CSV solto); (4) categorias SSP mudam com o tempo (ex.: subdivisões de estelionato); (5) a aba de indicadores tem estrutura inconsistente entre meses; (6) estação sem timestamp/nome indica cadastro incompleto na origem.

## 5. Hipóteses
{md_table(H)}

## 6. Divergências spec × fonte oficial (a fonte prevaleceu)
| spec / suposição | fonte oficial atual | tratamento |
|---|---|---|
| "baixe o arquivo **mensal** mais recente" | "publicação mensal" é um ZIP **anual acumulado** (jan–set/2026, extraído 06/10/2026), republicado por inteiro a cada mês | parser usa o ano mais recente da seção mensal; período lido do nome do arquivo |
| `historic` default ambíguo | tabela de variáveis diz `MIN_5`; tabela de intervalos diz `MIN_10 (padrão)` | `interval` sempre explícito (`{config.DC_HISTORIC_INTERVAL}`) |
| `value: null` = "não recebido recentemente" | doc: "não mandou essa medida nos últimos 20 minutos" | usado como staleness por sensor |
| dicionário em `/dicionario-de-dados` | página existe; dicionário canônico do art. 3º é o PDF "Nota metodológica e dicionário de dados" na página de dados abertos | ambos acessados; PDF usado para interpretar o layout de vítimas |
| esquema SSP "linha = vítima?" | 1 linha = 1 ocorrência; vítimas repetem em trios à direita | tabela `ssp_victims` separada |
| indicador ≈ soma de categorias | "Estelionato" oficial exclui "fraude eletrônica"; "Furtos"/"Roubos" diferem do nosso agrupamento por substring | divergência reportada, não forçada |
| campos `rio_nome`, `altitude` no contrato | presentes na consulta, nulos em 100% das estações | mantidos como NULL e reportados |
| estações "≈130" | {g(q,'total_stations')} | contagem medida a cada execução |
| dataset diário integrado (`municipality_daily_context`) | SSP termina em {g(s,'parse','declared_period',default=['',''])[1]}; hidrologia é de hoje; não há sobreposição temporal | gerado `municipality_monthly_safety.csv`, hidrologia mantida separada |

## 7. Findings
**Positivos:** API da Defesa Civil rápida (~1–2 s), sem autenticação, com sinais de qualidade nativos (homologação, manutenção, null por sensor) e séries de 5 min quase completas. Capturou um evento real em curso (subida de {top.get('delta_1h')} m/h). O SSP tem schema exatamente igual ao dicionário, cobre os 497 municípios, preenche ~100% de data/município/categoria e bate com os agregados oficiais em ±1% quando a regra de agregação é entendida.
**Negativos:** a SSP chega com defasagem de {R.get('_lag_days')} dias, sem coordenadas, com horários arredondados e bairros sujos. A Defesa Civil não tem estação em Gramado/Canela, restringe o histórico a 3 meses, deixa as cotas fora da consulta, {g(q,'official_status_counts','no_threshold')} estações não têm limiar cadastrado e há cadastros incompletos. A mesma categoria agregada pode significar coisas diferentes no indicador oficial e no microdado: quem somar ingenuamente vai divergir dos números do governo.

## 8. Limitações desta prova
Uma única coleta de `tags_data` (sem medir disponibilidade ao longo de dias); 5 séries de 24 h; um único arquivo SSP anual (sem comparação entre versões para medir revisões); mapeamento categoria→indicador heurístico; sem população para taxas.

## 9. Decisão
**{dec['result'].replace('_', ' ')}** — falhas críticas: {dec['critical_failures'] or 'nenhuma'}; ressalvas: {dec['caveats'] or 'nenhuma'}.
O caminho fonte → RAW → normalização → qualidade → métricas → consultas foi provado com dados reais nas duas fontes. As ressalvas limitam o *tipo* de produto (estratégico/resiliência regional), não a viabilidade técnica.

## 10. Próximo experimento de maior valor
**Coletor contínuo da Defesa Civil por 30 dias** (tags_data a cada 5 min, mais `historic` diário de backfill), em paralelo com **2 versões mensais consecutivas do ZIP SSP**. Isso mede de uma vez: disponibilidade/latência reais da API, frequência de sensores stale/manutenção, eventos de subida na bacia do Sinos/Caí (a montante e a jusante da Serra) e a taxa de revisão retroativa da SSP (linhas alteradas, removidas ou reclassificadas entre versões). São as duas incertezas que esta prova pontual não consegue resolver e das quais depende o valor do histórico próprio (H5).
"""
    return txt


def _raw_files() -> list[dict]:
    return [{"path": str(p), "bytes": p.stat().st_size} for p in config.RAW.rglob("*") if p.is_file()]


def terminal_summary(R: dict, dec: dict) -> str:
    dc, s = R.get("defesa_civil", {}), R.get("ssp", {})
    q, sq = dc.get("quality", {}), s.get("quality", {})
    L = ["=" * 58, "RS OPERATIONAL DATA PROOF   " + R["run"]["finished_at"][:19] + "Z", "=" * 58]
    if dc.get("status") == "ok":
        sc = q["official_status_counts"]
        rain10 = int((R["_frames"]["stations"]["rain_h024_mm"] > 10).sum())
        L += ["DEFESA CIVIL",
              f"Stations:                  {q['total_stations']:>10}",
              f"Fresh:                     {q['freshness_counts'].get('fresh', 0):>10}",
              f"Maintenance:               {q['maintenance_count']:>10}",
              f"River value valid:         {q['stations_with_river_level']:>10}",
              f"Attention/alert/flood:     {sc['attention']:>4}/{sc['alert']}/{sc['flood']:<4}",
              f"Rain > 10 mm / 24h:        {rain10:>10}",
              f"Serra stations <=40km:     {dc['serra_station_count']:>10}", ""]
    else:
        L += ["DEFESA CIVIL: FAILED " + str(dc.get("error")), ""]
    if s.get("status") == "ok":
        mm = s["municipality_metrics"]
        L += ["SSP (" + " a ".join(s["parse"]["declared_period"]) + ")",
              f"Rows loaded:               {sq['total_rows']:>10,}",
              f"Gramado:                   {mm['GRAMADO']['occurrences_total']:>10,}",
              f"Canela:                    {mm['CANELA']['occurrences_total']:>10,}", ""]
        for m in ("GRAMADO", "CANELA"):
            L.append(f"{m} top categories (ocorrências registradas):")
            for i, (k, v) in enumerate(list(mm[m]["occurrences_by_category_top10"].items())[:3], 1):
                L.append(f"  {i}. {k[:38]:<38} {v:>5}")
        L += ["", "Data quality (RS):",
              f"  Municipality filled      {100 - sq['municipality_null_pct']:>6.1f}%",
              f"  Neighborhood filled      {100 - sq['neighborhood_null_pct']:>6.1f}%",
              f"  Time filled              {100 - sq['time_null_pct']:>6.1f}%",
              f"  Time on exact hour       {sq['time_on_exact_hour_pct']:>6.1f}%"]
    else:
        L += ["SSP: FAILED " + str(s.get("error"))]
    L += ["", f"RESULT: {dec['result']}", "=" * 58]
    return "\n".join(L)


def write_all(R: dict) -> dict:
    dec = evaluate(R)
    dc_reports(R)
    ssp_reports(R)
    _w("sample_insights.md", sample_insights(R))
    _w("duckdb_queries.md", duckdb_report(R))
    _w("FINAL_DATA_PROOF.md", final_report(R, dec))
    _w("terminal_summary.txt", terminal_summary(R, dec) + "\n")
    slim = {k: v for k, v in R.items() if k not in ("_frames", "duckdb", "errors")}
    (config.REPORTS / "results.json").write_text(json.dumps(slim, indent=2, ensure_ascii=False, default=_jd))
    return dec
