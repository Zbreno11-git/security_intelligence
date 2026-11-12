# FINAL DATA PROOF — RS (execução 2026-11-12)

**Decisão: `GO WITH CAVEATS`** · execução 2026-11-12T21:09:20.144888+00:00 → 2026-11-12T21:10:56.060270+00:00 (95.9 s)
Todos os números abaixo foram produzidos por esta execução (ver `reports/run_manifest.json`, `reports/run.log`).

## 1. Resumo executivo
* Defesa Civil RS: API oficial acessível sem autenticação; 130 estações em uma chamada de 1.759 s; 125 com leitura fresca; nível de rio válido em 122 (6.15% nulo); séries de 5 min com 100.0–100.0% de completude.
* A camada de qualidade já encontrou problemas reais na Defesa Civil: nenhuma estação sem timestamp nesta coleta (num snapshot anterior do mesmo dia, DCRS-00125 veio sem timestamp e sem valores — trecho verbatim preservado em `tests/fixtures/tags_data_excerpt.json`; o defeito é intermitente); estações sem nome/coordenadas: ['DCRS-00129']; `rio_nome` e `altitude` nulos em 100%; 34 estações sem limiar oficial cadastrado.
* SSP-RS: link do arquivo mensal mais recente descoberto automaticamente na página; 567,659 ocorrências registradas (2026-01-01 a 2026-09-30), schema idêntico ao dicionário oficial.
* Gramado: 2,825 registros; Canela: 3,355. Volume suficiente para categorias frequentes (estelionato, furto, ameaça), insuficiente para tendências de crimes graves.
* Validação cruzada com os indicadores oficiais bate em ±1% na maioria das categorias, e explicou a maior divergência: o indicador "Estelionato" exclui "fraude eletrônica" (+30.2% → 1.1%).
* Limitações centrais: SSP com defasagem de 43 dias e sem coordenadas/horário fino confiável; Defesa Civil com histórico limitado a 3 meses e sem estação dentro de Gramado/Canela.
* Decisão: GO WITH CAVEATS — os dados sustentam um produto de inteligência agregada/resiliência, não despacho operacional.

## 2. Evidências numéricas

### Preflight (DNS/TLS/HTTP)
| url | ok | status_code | content_type | redirects | elapsed_s |
|---|---|---|---|---|---|
| https://sistemas.defesacivil.rs.gov.br/api-redehidrometeorologica | True | 200 | text/html; charset=UTF-8 | [] | 1.34 |
| https://ssp.rs.gov.br/dados-abertos | True | 200 | text/html; charset=UTF-8 | [] | 1.99 |
| https://www.ssp.rs.gov.br/indicadores-criminais | True | 200 | text/html; charset=UTF-8 | [] | 1.75 |
| https://www.ssp.rs.gov.br/dicionario-de-dados | True | 200 | text/html; charset=UTF-8 | [] | 8.81 |

### Defesa Civil
| métrica | valor |
|---|---|
| estações (doc: 130) | 130 |
| HTTP / bytes / latência | 200 / 318,209 / 1.759 s |
| proximaAtualizacaoEm | 2026-11-12T21:12:50.000Z |
| freshness | {'fresh': 125, 'delayed': 5} |
| idade da leitura (mediana / máx, min; medida a partir do início do bloco de 5 min) | 4.57 / 14.57 |
| manutenção | 0 (0.0%) |
| rio: sensor / valor válido / nulo % | 130 / 122 / 6.15% |
| chuva 1h nula % / 24h nula % | 0.77% / 0.77% |
| não homologado: rio / chuva | 3 / 3 |
| status oficial | {'normal': 91, 'attention': 2, 'alert': 0, 'flood': 0, 'unavailable': 3, 'no_threshold': 34, 'no_river_alarm_data': 0} |
| estações a ≤40 km de Gramado/Canela (rio válido / chuva válida) | 7 (7 / 6) |
| séries históricas baixadas / linhas | 5 / 1440 |
| drift da consulta oficial | {'tags_data': 'identical', 'historic': 'identical'} |

### SSP-RS
| métrica | valor |
|---|---|
| arquivo | 2026 (janeiro a setembro) (.zip 11,94MBytes) |
| ZIP / CSV | 12,524,194 B / 123,388,616 B |
| linhas × colunas nomeadas (células por linha) | 567,659 × 13 ([112]) |
| vítimas (linhas normalizadas) | 502,366 |
| municípios / categorias | 497 / 287 |
| missingness: município / data / hora / categoria / bairro | 0.0% / 0.0% / 0.0% / 0.0% / 19.47% |
| missingness vítima: idade / sexo / cor (+ "Sem informação") | 0.06% / 0.12% / 0.0% (+27.43%) |
| horas cheias (`HH:00:00`) | 38.45% |
| anomalias | {'age_negative': 0, 'age_gt_115': 4, 'age_non_numeric': 0, 'date_future': 0, 'date_invalid': 0, 'date_outside_declared_period': 0, 'time_invalid': 0, 'municipality_empty': 0, 'category_empty': 0, 'victim_count_missing': 13, 'victim_count_mismatch': 0} |
| duplicatas exatas RAW / ignorando Sequência | 0 / 1,729 (0.3%) |
| Gramado: total, rank RS, bairro %, hora % | 2,825, 44º, 84.25%, 100.0% |
| Canela: total, rank RS, bairro %, hora % | 3,355, 39º, 83.82%, 100.0% |
| top categorias RS | [('AMEACA', 79765), ('ESTELIONATO', 60753), ('OUTROS CRIMES', 36264), ('LESAO CORPORAL', 31702), ('LESAO CORPORAL CULPOSA DIRECAO VEIC AUTOMOTOR', 22895)] |

### Checks automatizados
| check | crítico | passou | evidência |
|---|---|---|---|
| dc_api_accessible | True | True | "HTTP 200" |
| dc_raw_preserved_with_sha256 | True | True | "data/raw/defesa_civil/2026-11-12/tags_data.json" |
| dc_official_query_unchanged | False | True | {"tags_data": "identical", "historic": "identical"} |
| dc_station_count_as_documented | False | True | "130 vs 130" |
| dc_fresh_ge_90pct | True | True | "96.2%" |
| dc_river_value_ge_80pct | False | True | "93.8%" |
| dc_history_ge1_station_ge80pct_complete | True | True | "5/5 stations" |
| dc_serra_has_valid_river_station_within_40km | False | True | "7 stations" |
| dc_station_inside_gramado_or_canela | False | False | "nenhuma estação com nome Gramado/Canela" |
| dc_flood_thresholds_in_payload | False | False | "resposta tags_data não contém cotas/limiares (só o status derivado)" |
| ssp_download_ok | True | True | "https://ssp.rs.gov.br/upload/arquivos/202610/16112425-spj-dados-abertos-ocorrencias-jan-set-2026-em-06-10-2026.zip" |
| ssp_schema_matches_dictionary | True | True | ["Sequência", "Data Fato", "Hora Fato", "Grupo Fato", "Tipo Enquadramento", "Tipo Fato", "Municipio Fato", "Local Fato", "Bairro", "Quantida |
| ssp_rows_loaded | True | True | 567659 |
| ssp_gramado_ge_100_per_month | False | True | "total=2825, monthly_min=273" |
| ssp_gramado_neighborhood_cov_ge_70pct | False | True | "84.25%" |
| ssp_canela_ge_100_per_month | False | True | "total=3355, monthly_min=325" |
| ssp_canela_neighborhood_cov_ge_70pct | False | True | "83.82%" |
| ssp_lag_le_45_days | False | True | "43 dias desde o fim do período coberto" |
| ssp_has_coordinates | False | False | "nenhuma coluna de latitude/longitude no arquivo art. 3º" |
| ssp_crossval_state_within_5pct_majority | False | True | "8/10 mappings within ±5%" |
| ssp_no_critical_anomalies_gt_1pct | True | True | {"date_invalid": 0, "date_future": 0, "municipality_empty": 0, "category_empty": 0} |


## 3. Outputs
* RAW imutável + `.meta.json` (sha256, URL final, status, bytes, horário): `data/raw/defesa_civil/<data>/`, `data/raw/ssp/<data>/` (`source.zip`, `extracted/`, `discovery.json`, páginas HTML, xlsx de indicadores)
* Curado: `data/curated/defesa_civil_stations.parquet`, `defesa_civil_history.parquet`, `ssp_occurrences.parquet`, `ssp_victims.parquet`, `municipality_monthly_safety.csv`, `municipality_metrics.csv`
* Quarentena (cópias para revisão, nada apagado): `data/quarantine/defesa_civil_flagged_stations.csv`, `data/quarantine/ssp_flagged_rows.csv`
* Relatórios: `reports/defesa_civil_quality.md`, `defesa_civil_summary.json`, `ssp_schema.md`, `ssp_quality.md`, `sample_insights.md`, `duckdb_queries.md`, `serra_stations.csv`, `river_sample.csv`, `terminal_summary.txt`, `run_manifest.json`, `run.log`

## 4. Respostas às perguntas do runbook (§29)

### Fonte
* **Acessível?** Defesa Civil: sim. SSP: sim. Ambas atrás de TLS válido, sem redirects.
* **Automatizável?** Sim. A consulta GraphQL é extraída da documentação a cada execução e comparada com a cópia vendorizada; o link SSP é descoberto pelo texto da seção "publicação mensal".
* **Autenticação?** Não. A Defesa Civil exige o identificador público `casa-militar-defesa-civil-rs`, já embutido na consulta oficial.
* **Rate limit?** Documentado em 120 req/min/IP; esta execução fez 7 requisições à API e não atingiu o limite. Instabilidade observada nesta execução: nenhum erro transitório. Durante o desenvolvimento (mesmo dia) o download do ZIP SSP falhou uma vez com `Connection reset by peer` no meio da transferência; por isso há retry limitado no nível da aplicação. As páginas da SSP levaram 1.745–8.81 s para responder no preflight.

### Estrutura
* **Schema estável/legível?** Defesa Civil: estável e auto-descritivo, com unidades documentadas; o contrato é rígido (só a consulta exata é aceita), o que favorece estabilidade e exige monitorar drift na documentação. SSP: as 13 colunas batem com o dicionário, mas o layout de vítimas é de largura variável (trio repetido, cabeçalho `...` + 98 colunas vazias), o encoding do CSV é Latin-1 sem declaração (o nome dentro do ZIP tem `Ê`, que o `unzip` em locale C exibe como `#U00ca`). A planilha de indicadores tem abas com cerca de 16 mil colunas vazias (JUL–SET).
* **Campos mais úteis.** DC: `rio_nivel`, `rio_nivel_tendencia`, `chuva.acumulado.*`, `rio_alarmes.inundacao.status`, `homologacao`, `manutencao`, `timestamp`. SSP: `Data Fato`, `Tipo Enquadramento`, `Municipio Fato`, `Local Fato`, `Quantidade Vítimas`.
* **Campos problemáticos.** DC: `rio_nome` e `altitude` nulos em 100%; `name.local` vazio em 100.0%; cotas (limiares) fora da consulta permitida. SSP: `Bairro` (19.47% vazio, 17,271 grafias → 11,645 normalizadas); `Hora Fato` (38.45% em hora cheia); `Cor Vítima` ("Sem informação" em 27.43% das vítimas); idade sentinela 126.

### Qualidade
* **Missingness real:** ver tabelas acima. O dado crítico (data, município, categoria) é ~100% preenchido; bairro e atributos de vítima são os pontos fracos.
* **Anomalias:** {'age_negative': 0, 'age_gt_115': 4, 'age_non_numeric': 0, 'date_future': 0, 'date_invalid': 0, 'date_outside_declared_period': 0, 'time_invalid': 0, 'municipality_empty': 0, 'category_empty': 0, 'victim_count_missing': 13, 'victim_count_mismatch': 0}; DC: nenhuma estação sem timestamp nesta coleta (num snapshot anterior do mesmo dia, DCRS-00125 veio sem timestamp e sem valores — trecho verbatim preservado em `tests/fixtures/tags_data_excerpt.json`; o defeito é intermitente); estações sem nome/coordenadas: ['DCRS-00129']; `rio_nome` e `altitude` nulos em 100%; 3+3 sensores não homologados.
* **Revisões/versionamento:** a SSP declara (dicionário de dados) que o arquivo do ano é republicado mensalmente com correções retroativas; rótulos na página indicam republicação de anos fechados: ['2024 (janeiro a dezembro) – atualizado em janeiro de 2026 (.zip 16,13 MBytes)']. Não há changelog nem ID estável de fato além de `Sequência` (posição no arquivo). Medir revisões exige guardar cada versão (sha256 já registrado). A Defesa Civil não expõe versionamento; leituras passadas podem ser re-consultadas por até 3 meses.

### Cobertura
* **Gramado:** 2,825 registros (273–333/mês), 44º do RS, bairro 84.25%. Suficiente para volume/sazonalidade/categorias frequentes.
* **Canela:** 3,355 registros (325–450/mês), 39º do RS, bairro 83.82%.
* **Defesa Civil na Serra:** 7 estações a ≤40 km (RS - Rio Caí, RS - Sinos); a mais próxima é Três Coroas (DCRS-00004), 12.8 km. **Nenhuma estação está dentro de Gramado ou Canela**, então o monitoramento é regional (bacias a jusante), não do perímetro urbano.
* **Estações com rio/chuva válidos (RS):** rio 122/130, chuva 129/130.

### Produto
* **Respondível hoje:** situação atual de 130 estações (nível, tendência, chuva multi-janela, status oficial, saúde do sensor); subida em 10/30/60 min por estação (ex.: DCRS-00022 Santa Rosa - Pessegueirinho subiu 0.41 m em 1h com 24.8 mm de chuva; status oficial `normal`); ranking de chuva 24h; volume/mix/sazonalidade de ocorrências registradas por município e mês; distribuição por dia da semana, faixa horária e tipo de local; bairros onde a cobertura passa de 70%; qualidade dos dados por fonte.
* **Não respondível:** onde exatamente (sem lat/lon nas ocorrências); o que aconteceu nas últimas semanas em segurança (defasagem de 43 dias); se um rio vai inundar (sem cotas/limiares na consulta e sem previsão); por que um indicador mudou (dado administrativo, sem causalidade); taxas per capita (população fora destas fontes); histórico hidrológico além de 3 meses sem coleta própria; perfis individuais (não fazemos e não devemos).
* **Exigiria parceria/dado privado:** ocorrências georreferenciadas e quase em tempo real (PC/BM/CIOSP); cotas de inundação por estação (Defesa Civil); sensores dentro de Gramado/Canela; população flutuante/turismo (prefeituras, hotelaria).
* **Métricas que parecem realmente úteis:** subida de nível em 1h com chuva concomitante (evento real capturado nesta execução); chuva acumulada multi-janela; `technical_data_confidence` para não confiar cegamente em leituras; registros mensais por categoria versus média do ano; participação por tipo de local; cobertura/qualidade por município.

### Engenharia
* **Baixado nesta execução (RAW total em disco):** 137,338,865 bytes (inclui o CSV extraído).
* **1 ano de coleta hidrometeorológica (extrapolado do observado):** snapshot tags_data = 318,209 B (gzip 30,491 B, 10.4×). Com coleta a cada 5 min são ~33.45 GB/ano de JSON bruto, ~3.21 GB/ano comprimido. Via `historic` diário (MIN_5) para todas as estações: ~4.24 GB/ano bruto, ~0.37 GB/ano gzip; curado em Parquet, ~533.2 MB/ano. Volume trivial para GCS/BigQuery.
* **SSP:** ZIP de 12,524,194 B por 9 meses; guardar todas as republicações mensais custa ~200.4 MB/ano.
* **Gargalos:** parse SSP em Python puro levou 30.8 s para 567,659 linhas (aceitável; polars/duckdb reduziriam). O download do ZIP SSP levou 18.951 s para 12,524,194 B, e um reset de conexão foi observado durante o desenvolvimento.
* **Dependências frágeis:** (1) consulta GraphQL só aceita texto exato, e qualquer mudança na doc quebra o coletor (mitigado com extração + diff a cada execução); (2) descoberta do link SSP depende do texto/ordem da página; (3) nome de arquivo e layout SSP mudam entre anos (2021 é CSV solto); (4) categorias SSP mudam com o tempo (ex.: subdivisões de estelionato); (5) a aba de indicadores tem estrutura inconsistente entre meses; (6) estação sem timestamp/nome indica cadastro incompleto na origem.

## 5. Hipóteses
| id | hipótese | veredito | evidência |
|---|---|---|---|
| H1 | Defesa Civil fornece dados frequentes e estruturados para um módulo de resiliência | SUPPORTED | 130 estações em 1 chamada (1.759 s); 125 fresh; rio válido em 122, chuva em 129; status oficial em 96 (34 sem limiar cadastrado); séries 5-min com 100.0–100.0% de completude. |
| H2 | SSP fornece granularidade/cobertura para análises estratégicas municipais | PARTIALLY SUPPORTED | 567,659 ocorrências, 497 municípios, data/hora/categoria ~100% preenchidas; porém defasagem de 43 dias desde o fim do período coberto, sem coordenadas, bairro vazio em 19.47% e 38.45% de horas cheias. |
| H3 | Defeitos existem mas são normalizáveis e monitoráveis | SUPPORTED | anomalias críticas SSP = 0; sentinela idade=126 (4); 13 linhas sem qtd. vítimas; DC: 6.15% rio nulo, rio_nome/altitude nulos em 100%; todos detectados por flags, nada apagado; validação cruzada explicou a maior divergência (estelionato). |
| H4 | Gramado e Canela têm volume/cobertura para design partners | PARTIALLY SUPPORTED | Gramado 2,825 registros (mín 273/mês, bairro 84.25%); Canela 3,355 (mín 325/mês, bairro 83.82%). Hidrologia: 7 estações a ≤40 km, nenhuma dentro dos 2 municípios. Categorias graves têm contagens muito baixas no período (Gramado homicidio doloso=1; Canela homicidio doloso=4; Gramado latrocinio=0; Canela latrocinio=0; Gramado roubos=5; Canela roubos=4; Gramado roubo de veiculo=0; Canela roubo de veiculo=0): tendência só é estatisticamente útil para categorias volumosas. |
| H5 | Há valor em armazenar histórico próprio | SUPPORTED | API recusa histórico >3 meses (sonda: `Não é possível consultar dados anteriores a 2026-08-12 18:09:49. Consulte no máximo os últimos 3 meses.`); tags_data só traz o instante atual; SSP republica o ano inteiro a cada mês (revisões retroativas) e só versionando os arquivos é possível medir revisões; cotas de inundação não fazem parte da consulta permitida. |
| H6 | Viável criar camada semântica/API/MCP depois | SUPPORTED | 12/12 perguntas-alvo respondidas por SQL sobre Parquet curado com schema estável; as funções candidatas (get_current_flood_status, get_station_history, get_safety_trend, get_data_quality) mapeiam 1:1 para essas consultas. |


## 6. Divergências spec × fonte oficial (a fonte prevaleceu)
| spec / suposição | fonte oficial atual | tratamento |
|---|---|---|
| "baixe o arquivo **mensal** mais recente" | "publicação mensal" é um ZIP **anual acumulado** (jan–set/2026, extraído 06/10/2026), republicado por inteiro a cada mês | parser usa o ano mais recente da seção mensal; período lido do nome do arquivo |
| `historic` default ambíguo | tabela de variáveis diz `MIN_5`; tabela de intervalos diz `MIN_10 (padrão)` | `interval` sempre explícito (`MIN_5`) |
| `value: null` = "não recebido recentemente" | doc: "não mandou essa medida nos últimos 20 minutos" | usado como staleness por sensor |
| dicionário em `/dicionario-de-dados` | página existe; dicionário canônico do art. 3º é o PDF "Nota metodológica e dicionário de dados" na página de dados abertos | ambos acessados; PDF usado para interpretar o layout de vítimas |
| esquema SSP "linha = vítima?" | 1 linha = 1 ocorrência; vítimas repetem em trios à direita | tabela `ssp_victims` separada |
| indicador ≈ soma de categorias | "Estelionato" oficial exclui "fraude eletrônica"; "Furtos"/"Roubos" diferem do nosso agrupamento por substring | divergência reportada, não forçada |
| campos `rio_nome`, `altitude` no contrato | presentes na consulta, nulos em 100% das estações | mantidos como NULL e reportados |
| estações "≈130" | 130 | contagem medida a cada execução |
| dataset diário integrado (`municipality_daily_context`) | SSP termina em 2026-09-30; hidrologia é de hoje; não há sobreposição temporal | gerado `municipality_monthly_safety.csv`, hidrologia mantida separada |

## 7. Findings
**Positivos:** API da Defesa Civil rápida (~1–2 s), sem autenticação, com sinais de qualidade nativos (homologação, manutenção, null por sensor) e séries de 5 min quase completas. Capturou um evento real em curso (subida de 0.41 m/h). O SSP tem schema exatamente igual ao dicionário, cobre os 497 municípios, preenche ~100% de data/município/categoria e bate com os agregados oficiais em ±1% quando a regra de agregação é entendida.
**Negativos:** a SSP chega com defasagem de 43 dias, sem coordenadas, com horários arredondados e bairros sujos. A Defesa Civil não tem estação em Gramado/Canela, restringe o histórico a 3 meses, deixa as cotas fora da consulta, 34 estações não têm limiar cadastrado e há cadastros incompletos. A mesma categoria agregada pode significar coisas diferentes no indicador oficial e no microdado: quem somar ingenuamente vai divergir dos números do governo.

## 8. Limitações desta prova
Uma única coleta de `tags_data` (sem medir disponibilidade ao longo de dias); 5 séries de 24 h; um único arquivo SSP anual (sem comparação entre versões para medir revisões); mapeamento categoria→indicador heurístico; sem população para taxas.

## 9. Decisão
**GO WITH CAVEATS** — falhas críticas: nenhuma; ressalvas: ['dc_station_inside_gramado_or_canela', 'dc_flood_thresholds_in_payload', 'ssp_has_coordinates'].
O caminho fonte → RAW → normalização → qualidade → métricas → consultas foi provado com dados reais nas duas fontes. As ressalvas limitam o *tipo* de produto (estratégico/resiliência regional), não a viabilidade técnica.

## 10. Próximo experimento de maior valor
**Coletor contínuo da Defesa Civil por 30 dias** (tags_data a cada 5 min, mais `historic` diário de backfill), em paralelo com **2 versões mensais consecutivas do ZIP SSP**. Isso mede de uma vez: disponibilidade/latência reais da API, frequência de sensores stale/manutenção, eventos de subida na bacia do Sinos/Caí (a montante e a jusante da Serra) e a taxa de revisão retroativa da SSP (linhas alteradas, removidas ou reclassificadas entre versões). São as duas incertezas que esta prova pontual não consegue resolver e das quais depende o valor do histórico próprio (H5).
