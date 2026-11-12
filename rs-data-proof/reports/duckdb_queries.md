# DuckDB — perguntas respondidas a partir dos Parquet curados

Reprodução: `duckdb` sobre `data/curated/*.parquet` (views `stations`, `history`, `occ`).

## DC — estações em atenção/alerta/inundação
```sql
SELECT codigo, name_general, bacia, official_status, rio_nivel_m, freshness
FROM stations WHERE official_status IN ('attention','alert','flood') ORDER BY official_status_code DESC
```

| codigo | name_general | bacia | official_status | rio_nivel_m | freshness |
|---|---|---|---|---|---|
| DCRS-00110 | Muitos Capões/Lagoa Vermelha | RS - Rio Taquari-Antas | attention | 743.45 | fresh |
| DCRS-00111 | Arroio Grande - Santa Isabel do Sul | RS - Lagoa Mirim e do Canal São Gonçalo | attention | 1.99 | fresh |

## DC — estações stale, sem leitura recente ou em manutenção
```sql
SELECT codigo, name_general, freshness, age_minutes, maintenance, quality_flags
FROM stations WHERE freshness <> 'fresh' OR maintenance ORDER BY age_minutes DESC NULLS LAST LIMIT 20
```

| codigo | name_general | freshness | age_minutes | maintenance | quality_flags |
|---|---|---|---|---|---|
| DCRS-00025 | Caraá | delayed | 14.57 | False | freshness_delayed |
| DCRS-00042 | Piratini - Cerrito | delayed | 14.57 | False | freshness_delayed |
| DCRS-00064 | São Gabriel | delayed | 14.57 | False | freshness_delayed |
| DCRS-00108 | Santa Cruz do Sul | delayed | 14.57 | False | freshness_delayed |
| DCRS-00121 | Guaporé / Anta Gorda | delayed | 14.57 | False | freshness_delayed |

## DC — maior subida (máx. variação em 1h) nas séries históricas coletadas
```sql
WITH h AS (SELECT codigo, ts_utc, rio_nivel,
rio_nivel - LAG(rio_nivel, 12) OVER  -- 12 blocos de 5 min = 1h (assume série sem lacunas)
(PARTITION BY codigo ORDER BY ts_utc) AS d1h
FROM history WHERE rio_nivel IS NOT NULL)
SELECT codigo, MAX(d1h) AS max_rise_1h_m, MIN(rio_nivel) AS min_m, MAX(rio_nivel) AS max_m
FROM h GROUP BY codigo ORDER BY max_rise_1h_m DESC NULLS LAST
```

| codigo | max_rise_1h_m | min_m | max_m |
|---|---|---|---|
| DCRS-00022 | 0.8 | 236.85 | 237.65 |
| DCRS-00004 | 0.01 | 68.9 | 68.94 |
| DCRS-00001 | 0.01 | 27.23 | 27.27 |
| DCRS-00002 | 0.01 | 20.64 | 20.66 |
| DCRS-00110 | 0.01 | 743.45 | 743.51 |

## DC — maior subida de nível (tendência atual, todas as estações)
```sql
SELECT codigo, name_general, rio_nivel_m, rio_nivel_tendencia_m, official_status
FROM stations WHERE rio_nivel_tendencia_m IS NOT NULL ORDER BY rio_nivel_tendencia_m DESC LIMIT 5
```

| codigo | name_general | rio_nivel_m | rio_nivel_tendencia_m | official_status |
|---|---|---|---|---|
| DCRS-00016 | Passo Fundo | 646.88 | 326.41 | normal |
| DCRS-00107 | Tucunduva/Horizontina (H) | 195.39 | 0.05 | normal |
| DCRS-00058 | Toropi/São Pedro do Sul | 101.96 | 0.04 | normal |
| DCRS-00094 | Tuparendi/Tucunduva  | 131.21 | 0.01 | no_threshold |
| DCRS-00055 | Santa Cruz do Sul / Venâncio Aires | 49.17 | 0.01 | normal |

## DC — mais chuva nas últimas 24h
```sql
SELECT codigo, name_general, regiao, rain_h024_mm, rain_h001_mm, rain_homologated
FROM stations WHERE rain_h024_mm IS NOT NULL ORDER BY rain_h024_mm DESC LIMIT 10
```

| codigo | name_general | regiao | rain_h024_mm | rain_h001_mm | rain_homologated |
|---|---|---|---|---|---|
| DCRS-00022 | Santa Rosa - Pessegueirinho | Noroeste Rio-grandense | 34.6 | 24.8 | True |
| DCRS-00059 | Santa Rosa - Pessegueiro | Noroeste Rio-grandense | 30.8 | 20.8 | True |
| DCRS-00130 | Ijuí | Noroeste Rio-grandense | 17.2 | 0.4 | True |
| DCRS-00074 | Barra do Rio Azul - Rio Azul | Noroeste Rio-grandense | 14.2 | 0.4 | True |
| DCRS-00060 | Barra do Rio Azul - Rio Palomas | Noroeste Rio-grandense | 13.8 | 0.6 | True |
| DCRS-00080 | São Pedro do Sul/Santa Maria | Centro Ocidental Rio-grandense | 13.8 | 0 | False |
| DCRS-00019 | Sarandi | Noroeste Rio-grandense | 10 | 0 | True |
| DCRS-00106 | Guarani das Missões (H) | Noroeste Rio-grandense | 9.8 | 0.2 | True |
| DCRS-00071 | Aratiba | Noroeste Rio-grandense | 7.6 | 0 | True |
| DCRS-00061 | Cacique Doble | Noroeste Rio-grandense | 6 | 0 | True |

## DC — estações a até 40 km de Gramado/Canela
```sql
SELECT codigo, name_general, bacia, dist_serra_km, has_river_value, has_rain_value,
official_status, freshness, technical_data_confidence
FROM stations WHERE dist_serra_km <= 40 ORDER BY dist_serra_km
```

| codigo | name_general | bacia | dist_serra_km | has_river_value | has_rain_value | official_status | freshness | technical_data_confidence |
|---|---|---|---|---|---|---|---|---|
| DCRS-00004 | Três Coroas | RS - Sinos | 12.82 | True | True | normal | fresh | 100 |
| DCRS-00001 | Igrejinha | RS - Sinos | 23.01 | True | True | normal | fresh | 100 |
| DCRS-00002 | Nova Hartz | RS - Sinos | 24.01 | True | True | normal | fresh | 100 |
| DCRS-00046 | Picada Café | RS - Rio Caí | 27.39 | True | True | normal | fresh | 100 |
| DCRS-00075 | Nova Petrópolis/Caxias do Sul | RS - Rio Caí | 28.55 | True | True | normal | fresh | 100 |
| DCRS-00085 | Dois Irmãos | RS - Rio Caí | 31.98 | True | True | normal | fresh | 100 |
| DCRS-00003 | Araricá / Sapiranga / Taquara | RS - Sinos | 35.33 | True | False | normal | fresh | 100 |

## SSP — ocorrências registradas em Gramado e Canela no período
```sql
SELECT municipality, COUNT(*) AS ocorrencias_registradas, MIN(occurrence_date) AS de, MAX(occurrence_date) AS ate
FROM occ WHERE municipality IN ('GRAMADO','CANELA') GROUP BY 1 ORDER BY 1
```

| municipality | ocorrencias_registradas | de | ate |
|---|---|---|---|
| CANELA | 3,355 | 2026-01-01 00:00:00 | 2026-09-30 00:00:00 |
| GRAMADO | 2,825 | 2026-01-01 00:00:00 | 2026-09-30 00:00:00 |

## SSP — 10 categorias mais frequentes em Gramado
```sql
SELECT category, COUNT(*) AS n FROM occ WHERE municipality = 'GRAMADO'
GROUP BY 1 ORDER BY n DESC LIMIT 10
```

| category | n |
|---|---|
| AMEACA | 369 |
| OUTROS CRIMES | 329 |
| OUTRAS FRAUDES | 191 |
| ESTELIONATO | 150 |
| LESAO CORPORAL | 133 |
| ESTELIONATO FRAUDE ELETRONICA | 125 |
| FUGA DE LOCAL DE ACIDENTE - ART. 305 | 112 |
| LESAO CORPORAL CULPOSA DIRECAO VEIC AUTOMOTOR | 106 |
| PERTURBACAO DO TRABALHO OU DO SOSSEGO ALHEIOS | 86 |
| DANO | 76 |

## SSP — distribuição mensal (Gramado e Canela)
```sql
SELECT strftime(occurrence_date, '%Y-%m') AS mes,
SUM(CASE WHEN municipality='GRAMADO' THEN 1 ELSE 0 END) AS gramado,
SUM(CASE WHEN municipality='CANELA' THEN 1 ELSE 0 END) AS canela
FROM occ WHERE municipality IN ('GRAMADO','CANELA') GROUP BY 1 ORDER BY 1
```

| mes | gramado | canela |
|---|---|---|
| 2026-01 | 303 | 367 |
| 2026-02 | 281 | 374 |
| 2026-03 | 329 | 450 |
| 2026-04 | 327 | 380 |
| 2026-05 | 323 | 339 |
| 2026-06 | 273 | 351 |
| 2026-07 | 329 | 384 |
| 2026-08 | 327 | 385 |
| 2026-09 | 333 | 325 |

## SSP — cobertura de bairro e horário (Gramado, Canela, demais municípios)
```sql
SELECT COALESCE(CASE WHEN municipality IN ('GRAMADO','CANELA') THEN municipality END, 'DEMAIS MUNICÍPIOS') AS escopo,
ROUND(100.0*AVG(CASE WHEN neighborhood IS NOT NULL THEN 1 ELSE 0 END),2) AS bairro_pct,
ROUND(100.0*AVG(CASE WHEN occurrence_time IS NOT NULL THEN 1 ELSE 0 END),2) AS hora_pct,
ROUND(100.0*AVG(CASE WHEN occurrence_time LIKE '%:00:00' THEN 1 ELSE 0 END),2) AS hora_cheia_pct
FROM occ GROUP BY ROLLUP(1) HAVING escopo IS NOT NULL ORDER BY 1
```

| escopo | bairro_pct | hora_pct | hora_cheia_pct |
|---|---|---|---|
| CANELA | 83.82 | 100 | 36.24 |
| DEMAIS MUNICÍPIOS | 80.49 | 100 | 38.47 |
| GRAMADO | 84.25 | 100 | 35.93 |

## SSP — bairros com maior volume de registros (Gramado)
```sql
SELECT neighborhood, COUNT(*) AS n FROM occ WHERE municipality='GRAMADO' AND neighborhood IS NOT NULL
GROUP BY 1 ORDER BY n DESC LIMIT 10
```

| neighborhood | n |
|---|---|
| CENTRO | 509 |
| VARZEA GRANDE | 192 |
| VILA SUICA | 181 |
| CARNIEL | 146 |
| PLANALTO | 140 |
| FLORESTA | 109 |
| DUTRA | 89 |
| LOTEAMENTO BELVEDERE | 80 |
| VILA DO SOL | 69 |
| BAIRRO BELVEREDE | 67 |

## SSP — bairros com maior volume de registros (Canela)
```sql
SELECT neighborhood, COUNT(*) AS n FROM occ WHERE municipality='CANELA' AND neighborhood IS NOT NULL
GROUP BY 1 ORDER BY n DESC LIMIT 10
```

| neighborhood | n |
|---|---|
| CENTRO | 980 |
| EUGENIO FERREIRA | 178 |
| SAO JOSE | 139 |
| SAO RAFAEL | 130 |
| SAO LUCAS | 104 |
| DISTRITO INDUSTRIAL | 103 |
| VILA MAGGI | 101 |
| BECO DA ALEGRIA | 95 |
| VILA LUIZA | 89 |
| CANELINHA | 78 |
