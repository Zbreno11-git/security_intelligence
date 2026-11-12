# Defesa Civil RS — Qualidade dos dados (execução 2026-11-12)

Fonte: `https://redehidrometeorologica.defesacivil.rs.gov.br/graphql` (consulta oficial `Tags_data`, texto extraído da documentação a cada execução).
Coleta: `2026-11-12T21:09:34.346759+00:00` UTC · HTTP 200 · 318,209 bytes · 1.759 s · tentativas 1
`proximaAtualizacaoEm` = `2026-11-12T21:12:50.000Z` · sha256 RAW = `4eb90df005bf69d19e86a96c41677dd26ae71681f9f43ed0acfc74365129d6e6`
Drift da consulta vs. cópia vendorizada: `{'tags_data': 'identical', 'historic': 'identical'}`

> Freshness aqui é **qualidade técnica** (idade da leitura), não risco hidrológico.
> `technical_data_confidence` é um score **experimental e não oficial**; não é probabilidade de enchente.

## Resumo
| métrica | valor |
|---|---|
| total_stations | 130 |
| stations_with_river_sensor | 130 |
| stations_with_river_level | 122 |
| stations_with_rain_sensor | 130 |
| stations_with_rain | 129 |
| stations_with_lat_lon | 129 |
| maintenance_count | 0 |
| maintenance_percentage | 0 |
| stale_station_count | 0 |
| stale_station_percentage | 0 |
| age_minutes_median | 4.57 |
| age_minutes_p95 | 4.57 |
| age_minutes_max | 14.57 |
| river_level_missing_pct | 6.15 |
| rain_1h_missing_pct | 0.77 |
| rain_24h_missing_pct | 0.77 |
| temperature_missing_pct | 0 |
| non_homologated_river_count | 3 |
| non_homologated_rain_count | 3 |
| non_homologated_temp_count | 0 |
| duplicate_station_codes | 0 |
| rain_negative_values | 0 |
| rain_window_monotonic_violations | 0 |
| missing_rio_nome | 130 |
| missing_altitude | 130 |

### Status oficial de nível (contagem de estações)
| status | estações |
|---|---|
| normal | 91 |
| attention | 2 |
| alert | 0 |
| flood | 0 |
| unavailable | 3 |
| no_threshold | 34 |
| no_river_alarm_data | 0 |

### Freshness
| classe | estações |
|---|---|
| fresh | 125 |
| delayed | 5 |

Idade da leitura (min): mediana 4.57, p95 4.57, máx 14.57.
Distribuição de blocos de timestamp nesta coleta: `{'2026-11-12T18:05:00.000': 125, '2026-11-12T17:55:00.000': 5}`.
Nota metodológica: `timestamp` é o **início** do bloco de 5 min e o dado é publicado 1–2 min após o marco, então a
idade mínima normal é ~5–7 min; uma estação **um bloco atrasada** aparece com ~10–12 min e cai em `delayed` pelos
limiares do runbook (≤10 fresh). `delayed` não penaliza o score; só `stale` (>20 min) penaliza. A staleness por
sensor aparece via `value: null` (sem envio nos últimos 20 min, segundo a documentação).

### Score técnico de confiança (distribuição)
| score | estações |
|---|---|
| 100 | 119 |
| 85 | 8 |
| 80 | 3 |


## Estações com flags de qualidade (não removidas; cópia em `data/quarantine/defesa_civil_flagged_stations.csv`)
| codigo | name_general | bacia | quality_flags | technical_data_confidence |
|---|---|---|---|---|
| DCRS-00003 | Araricá / Sapiranga / Taquara | RS - Sinos | rain_value_null | 100 |
| DCRS-00025 | Caraá | RS - Sinos | freshness_delayed | 100 |
| DCRS-00027 | Santa Maria - Arroio Cadena | RS - Rios Vacacaí - Vacacaí Mirim | rain_not_homologated | 100 |
| DCRS-00028 | Rio Pardo - Rio Jacuí | RS - Baixo Jacuí | river_value_null | 85 |
| DCRS-00033 | Porto Alegre - Ipanema | RS - Lago Guaíba | river_value_null | 85 |
| DCRS-00042 | Piratini - Cerrito | RS - Lagoa Mirim e do Canal São Gonçalo | freshness_delayed | 100 |
| DCRS-00043 | Três Forquilhas - Rio Pedras Brancas | RS - Rio Tramandaí | river_value_null | 85 |
| DCRS-00062 | Pelotas - Arroio Pelotas | RS - Lagoa Mirim e do Canal São Gonçalo | river_not_homologated | 80 |
| DCRS-00064 | São Gabriel | RS - Rios Vacacaí - Vacacaí Mirim | freshness_delayed | 100 |
| DCRS-00071 | Aratiba | RS - Rios Apuaê – Inhandava | river_not_homologated | 80 |
| DCRS-00080 | São Pedro do Sul/Santa Maria | RS - Rio Ibicuí | rain_not_homologated | 100 |
| DCRS-00098 | Porto Lucena/Porto Xavier | RS - Rios Turvo – Santa Rosa – Santo Cristo | river_value_null | 85 |
| DCRS-00099 | Iraí - Rio Uruguai | RS - Rio da Várzea | river_value_null | 85 |
| DCRS-00103 | Manoel Viana (H) | RS - Rio Ibicuí | rain_not_homologated | 100 |
| DCRS-00104 | Arroio do Meio/Lajeado (H) | RS - Rio Taquari-Antas | river_value_null | 85 |
| DCRS-00108 | Santa Cruz do Sul | RS - Rio Pardo | freshness_delayed | 100 |
| DCRS-00121 | Guaporé / Anta Gorda | RS - Rio Taquari-Antas | freshness_delayed | 100 |
| DCRS-00122 | Porto Alegre - Cristal | RS - Lago Guaíba | river_value_null | 85 |
| DCRS-00123 | Arroio do Meio - Rio Taquari | RS - Rio Taquari-Antas | river_value_null | 85 |
| DCRS-00129 | NULL | NULL | river_not_homologated\|no_coordinates | 80 |


## Série histórica (`historic`, interval=MIN_5 explícito, últimas 24 h)
| codigo | rows | expected_blocks_approx | completeness_pct | first_ts_utc | last_ts_utc | gaps_over_1_5_interval | duplicate_ts | rio_nivel_max_identical_run_blocks | rio_nivel_max_identical_run_hours | rio_nivel_jumps_gt_0_5m_per_block | negative_rain_blocks | null_pct_rio_nivel | null_pct_chuva |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DCRS-00004 | 288 | 288 | 100 | 2026-11-11 21:10:00+00:00 | 2026-11-12 21:05:00+00:00 | 0 | 0 | 25 | 2.08 | 0 | 0 | 0 | 0 |
| DCRS-00001 | 288 | 288 | 100 | 2026-11-11 21:10:00+00:00 | 2026-11-12 21:05:00+00:00 | 0 | 0 | 63 | 5.25 | 0 | 0 | 0 | 0 |
| DCRS-00002 | 288 | 288 | 100 | 2026-11-11 21:10:00+00:00 | 2026-11-12 21:05:00+00:00 | 0 | 0 | 56 | 4.67 | 0 | 0 | 0 | 0 |
| DCRS-00110 | 288 | 288 | 100 | 2026-11-11 21:10:00+00:00 | 2026-11-12 21:05:00+00:00 | 0 | 0 | 76 | 6.33 | 0 | 0 | 0 | 0 |
| DCRS-00022 | 288 | 288 | 100 | 2026-11-11 21:10:00+00:00 | 2026-11-12 21:05:00+00:00 | 0 | 0 | 62 | 5.17 | 0 | 0 | 0 | 0 |


Teste do limite documentado de 3 meses (consulta ~100 dias atrás): aceito = `False`; resposta:
`[{"message": "Não é possível consultar dados anteriores a 2026-08-12 18:09:49. Consulte no máximo os últimos 3 meses.", "locations": [{"line": 2, "column": 3}], "path": ["historic"], "extensions": {"code": "BAD_REQUEST"}}]`

## Exemplos legíveis
### Estação DCRS-00004 — Três Coroas
```
Bacia:            RS - Sinos
Seleção:          nearest_to_gramado_canela
Distância Serra:  12.82 km (Gramado/Canela)
Última leitura:   2026-11-12 21:05:00+00:00 (UTC)
Nível:            68.91 m
Variação 10 min:  0.01 m
Variação 30 min:  0.0 m
Variação 1h:      0.0 m   (taxa ajustada -0.0038 m/h)
Maior subida 1h na janela de 24h: 0.01 m em 2026-11-12 11:35:00+00:00
Chuva 30 min / 1h / 3h / 24h: 0.0 / 0.0 / 0.0 / 0.0 mm
Chuva 1h / 24h segundo tags_data: 0.0 / 0.0 mm
Intensidade máx. (24h): 0.0 mm/h
Status oficial:   normal
Freshness:        fresh
Data confidence:  100/100 (experimental, não oficial)
```
### Estação DCRS-00001 — Igrejinha
```
Bacia:            RS - Sinos
Seleção:          nearest_to_gramado_canela
Distância Serra:  23.01 km (Gramado/Canela)
Última leitura:   2026-11-12 21:05:00+00:00 (UTC)
Nível:            27.23 m
Variação 10 min:  0.0 m
Variação 30 min:  -0.01 m
Variação 1h:      -0.01 m   (taxa ajustada -0.013 m/h)
Maior subida 1h na janela de 24h: 0.01 m em 2026-11-12 02:25:00+00:00
Chuva 30 min / 1h / 3h / 24h: 0.0 / 0.0 / 0.0 / 0.0 mm
Chuva 1h / 24h segundo tags_data: 0.0 / 0.0 mm
Intensidade máx. (24h): 0.0 mm/h
Status oficial:   normal
Freshness:        fresh
Data confidence:  100/100 (experimental, não oficial)
```
### Estação DCRS-00002 — Nova Hartz
```
Bacia:            RS - Sinos
Seleção:          nearest_to_gramado_canela
Distância Serra:  24.01 km (Gramado/Canela)
Última leitura:   2026-11-12 21:05:00+00:00 (UTC)
Nível:            20.64 m
Variação 10 min:  0.0 m
Variação 30 min:  0.0 m
Variação 1h:      0.0 m   (taxa ajustada -0.0 m/h)
Maior subida 1h na janela de 24h: 0.01 m em 2026-11-12 00:15:00+00:00
Chuva 30 min / 1h / 3h / 24h: 0.0 / 0.0 / 0.0 / 0.0 mm
Chuva 1h / 24h segundo tags_data: 0.0 / 0.0 mm
Intensidade máx. (24h): 0.0 mm/h
Status oficial:   normal
Freshness:        fresh
Data confidence:  100/100 (experimental, não oficial)
```
### Estação DCRS-00110 — Muitos Capões/Lagoa Vermelha
```
Bacia:            RS - Rio Taquari-Antas
Seleção:          highest_official_status_or_rising_trend
Distância Serra:  125.73 km (Gramado/Canela)
Última leitura:   2026-11-12 21:05:00+00:00 (UTC)
Nível:            743.45 m
Variação 10 min:  0.0 m
Variação 30 min:  0.0 m
Variação 1h:      0.0 m   (taxa ajustada -0.0038 m/h)
Maior subida 1h na janela de 24h: 0.01 m em 2026-11-11 22:30:00+00:00
Chuva 30 min / 1h / 3h / 24h: 0.0 / 0.0 / 0.0 / 0.0 mm
Chuva 1h / 24h segundo tags_data: 0.0 / 0.0 mm
Intensidade máx. (24h): 0.0 mm/h
Status oficial:   attention
Freshness:        fresh
Data confidence:  100/100 (experimental, não oficial)
```
### Estação DCRS-00022 — Santa Rosa - Pessegueirinho
```
Bacia:            RS - Rios Turvo – Santa Rosa – Santo Cristo
Seleção:          highest_rain_24h
Distância Serra:  390.77 km (Gramado/Canela)
Última leitura:   2026-11-12 21:05:00+00:00 (UTC)
Nível:            237.36 m
Variação 10 min:  -0.11 m
Variação 30 min:  -0.09 m
Variação 1h:      0.41 m   (taxa ajustada 0.3961 m/h)
Maior subida 1h na janela de 24h: 0.8 m em 2026-11-12 20:45:00+00:00
Chuva 30 min / 1h / 3h / 24h: 4.6 / 24.8 / 34.2 / 34.6 mm
Chuva 1h / 24h segundo tags_data: 24.8 / 34.6 mm
Intensidade máx. (24h): 129.3 mm/h
Status oficial:   normal
Freshness:        fresh
Data confidence:  100/100 (experimental, não oficial)
```

