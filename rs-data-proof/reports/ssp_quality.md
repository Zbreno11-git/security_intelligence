# SSP-RS — Qualidade (execução 2026-11-12)

> Estes são **registros administrativos** (ocorrências registradas), não "crime real". Estão sujeitos a
> subnotificação, prática de registro, reclassificação e revisão posterior (ver nota metodológica oficial).

## Métricas
| métrica | valor |
|---|---|
| total_rows | 567,659 |
| duplicate_full_rows_raw | 0 |
| duplicate_rows_ignoring_sequence_id | 1,729 |
| duplicate_rows_ignoring_sequence_id_pct | 0.3 |
| municipality_null_pct | 0 |
| date_null_pct | 0 |
| time_null_pct | 0 |
| category_null_pct | 0 |
| neighborhood_null_pct | 19.47 |
| victim_count_zero_pct | 18.9 |
| victims_total | 502,366 |
| victim_age_null_pct | 0.06 |
| victim_sex_null_pct | 0.12 |
| victim_race_null_pct | 0 |
| victim_race_sem_informacao_pct | 27.43 |
| victim_age_126_count | 4 |
| municipality_unique_count | 497 |
| category_unique_count | 287 |
| category_raw_unique_count | 287 |
| neighborhood_unique_count_raw | 17,271 |
| neighborhood_unique_count_normalized | 11,645 |
| time_on_exact_hour_pct | 38.45 |
| time_midnight_0000_or_0001_pct | 0.54 |
| date_min | 2026-01-01 |
| date_max | 2026-09-30 |


## Anomalias (marcadas com `quality_flags`; nada foi apagado)
| anomalia | ocorrências/vítimas |
|---|---|
| age_negative | 0 |
| age_gt_115 | 4 |
| age_non_numeric | 0 |
| date_future | 0 |
| date_invalid | 0 |
| date_outside_declared_period | 0 |
| time_invalid | 0 |
| municipality_empty | 0 |
| category_empty | 0 |
| victim_count_missing | 13 |
| victim_count_mismatch | 0 |

Linhas copiadas para `data/quarantine/ssp_flagged_rows.csv` (critério: flag crítica ou problema de vítima): **16**.

Observações:
* `age_gt_115`: todas as idades >115 observadas valem **126** (4 vítimas) — padrão de valor-sentinela, não erro aleatório.
* `victim_count_missing`: campo `Quantidade Vítimas` vazio, sem trios de vítima.
* Duplicatas: 0 linhas idênticas no RAW (o `Sequência` é único). Ignorando `Sequência`,
  1,729 linhas (0.3%) repetem todos os demais campos.
  **Não foram removidas**: sem identificador de fato não há critério confiável (ex.: 2 furtos no mesmo dia/bairro são plausíveis).
* Hora "cheia" (`HH:00:00`): 38.45% dos horários — forte arredondamento; análise por faixa horária é viável, por minuto não.
* `Bairro` tem 17,271 grafias brutas → 11,645 após normalização (maiúsculas/acentos/espaços).
* `Tipo Fato` contém apenas: {'Consumado': 567659} (o arquivo art. 3º só traz fatos consumados).

## Contagem de flags
| flag | linhas |
|---|---|
| neighborhood_empty | 110,539 |
| victim_count_missing | 13 |
| age_gt_115 | 3 |


## Validação cruzada com Indicadores Criminais (agregados oficiais), meses 9
Mapeamento categoria→indicador é **nosso** (heurístico); divergências são documentadas, não forçadas.
| mapping | scope | microdata_count | indicator_count | diff | diff_pct |
|---|---|---|---|---|---|
| HOMICIDIO DOLOSO | RS (state) | 663 | 659 | 4 | 0.6 |
| HOMICIDIO DOLOSO | GRAMADO | 0 | 1 | -1 | -100 |
| HOMICIDIO DOLOSO | CANELA | 4 | 4 | 0 | 0 |
| LATROCINIO | RS (state) | 27 | 27 | 0 | 0 |
| LATROCINIO | GRAMADO | 0 | 0 | 0 | NULL |
| LATROCINIO | CANELA | 0 | 0 | 0 | NULL |
| FURTOS (any category containing FURTO) | RS (state) | 79,519 | 75,764 | 3,755 | 5 |
| FURTOS (any category containing FURTO) | GRAMADO | 290 | 286 | 4 | 1.4 |
| FURTOS (any category containing FURTO) | CANELA | 360 | 354 | 6 | 1.7 |
| ABIGEATO | RS (state) | 2,659 | 2,686 | -27 | -1 |
| ABIGEATO | GRAMADO | 0 | 0 | 0 | NULL |
| ABIGEATO | CANELA | 2 | 2 | 0 | 0 |
| FURTO DE VEICULO | RS (state) | 4,172 | 4,174 | -2 | -0 |
| FURTO DE VEICULO | GRAMADO | 5 | 5 | 0 | 0 |
| FURTO DE VEICULO | CANELA | 8 | 8 | 0 | 0 |
| ROUBOS (any category containing ROUBO) | RS (state) | 12,086 | 11,023 | 1,063 | 9.6 |
| ROUBOS (any category containing ROUBO) | GRAMADO | 4 | 5 | -1 | -20 |
| ROUBOS (any category containing ROUBO) | CANELA | 6 | 4 | 2 | 50 |
| ROUBO DE VEICULO | RS (state) | 1,101 | 1,101 | 0 | 0 |
| ROUBO DE VEICULO | GRAMADO | 0 | 0 | 0 | NULL |
| ROUBO DE VEICULO | CANELA | 0 | 0 | 0 | NULL |
| ESTELIONATO (all ESTELIONATO*) | RS (state) | 79,774 | 61,275 | 18,499 | 30.2 |
| ESTELIONATO (all ESTELIONATO*) | GRAMADO | 279 | 154 | 125 | 81.2 |
| ESTELIONATO (all ESTELIONATO*) | CANELA | 446 | 365 | 81 | 22.2 |
| ESTELIONATO (excl. FRAUDE ELETRONICA) [hypothesis] | RS (state) | 61,923 | 61,275 | 648 | 1.1 |
| ESTELIONATO (excl. FRAUDE ELETRONICA) [hypothesis] | GRAMADO | 154 | 154 | 0 | 0 |
| ESTELIONATO (excl. FRAUDE ELETRONICA) [hypothesis] | CANELA | 366 | 365 | 1 | 0.3 |
| ENTORPECENTES - POSSE | RS (state) | 4,459 | 4,503 | -44 | -1 |
| ENTORPECENTES - POSSE | GRAMADO | 24 | 24 | 0 | 0 |
| ENTORPECENTES - POSSE | CANELA | 37 | 37 | 0 | 0 |
| ENTORPECENTES - TRAFICO | RS (state) | 12,887 | 12,912 | -25 | -0.2 |
| ENTORPECENTES - TRAFICO | GRAMADO | 53 | 53 | 0 | 0 |
| ENTORPECENTES - TRAFICO | CANELA | 48 | 48 | 0 | 0 |

