# SSP-RS — Schema real observado (execução 2026-11-12)

Página de origem: https://ssp.rs.gov.br/dados-abertos
Link escolhido (descoberto na página, seção "publicação mensal"): **2026 (janeiro a setembro) (.zip 11,94MBytes)**
URL: `https://ssp.rs.gov.br/upload/arquivos/202610/16112425-spj-dados-abertos-ocorrencias-jan-set-2026-em-06-10-2026.zip`
Download: HTTP 200 · 12,524,194 bytes · 18.951 s ·
tentativas 1 · sha256 `f87306dacea2d772ba7c26b56ad313f63d556b11783dde3184fe0b6d72a9fcc3`

## Conteúdo do ZIP
| member_name_in_zip | utf8_name_flag | uncompressed_size | zip_datetime | sha256 |
|---|---|---|---|---|
| SPJ_DADOS_ABERTOS_OCORRÊNCIAS_JAN_SET_2026 - Em 06.10.2026.csv | True | 123,388,616 | 2026-10-16T10:55:26 | 0e3092881679f780994d624d2889428201119ea49173d2d21e89626d4424b369 |

Nota: o ZIP marca os nomes como UTF-8 (`utf8_name_flag=True`) e o Python decodifica corretamente; ferramentas como `unzip` em locale C exibem `#U00ca` no lugar de `Ê` — usar sempre a biblioteca, não o CLI.

## Formato
| item | valor |
|---|---|
| encoding detectado | `latin-1` |
| delimitador | `;` |
| linhas de dados | 567,659 |
| células no cabeçalho | 112 (13 nomeadas + `...` + 98 vazias) |
| distribuição de largura das linhas | `{112: 567659}` |
| período declarado no nome | 2026-01-01 a 2026-09-30 |
| data de extração no nome | 2026-10-06 |
| cabeçalho confere com dicionário oficial | **True** |

**Layout de vítimas:** conforme o dicionário oficial, cada linha é **uma ocorrência**; o trio
`Idade/Sexo/Cor Vítima` se repete à direita uma vez por vítima. O cabeçalho só nomeia o 1º trio, seguido de uma
coluna literal `...` e cabeçalhos vazios. Ocorrências com >1 vítima: 34,739;
máximo de vítimas numa linha: 34. A tabela `ssp_victims.parquet` normaliza esse layout (1 linha por vítima).

## Perfil por coluna (13 colunas nomeadas; vítima = 1º trio)
| raw_column | column | dtype_inferred | null_count | null_pct | unique_count | sample_values |
|---|---|---|---|---|---|---|
| Sequência | occurrence_id | integer | 0 | 0 | 567,659 | 567659, 1, 2, 3, 4 |
| Data Fato | occurrence_date_raw | date(DD/MM/YYYY) | 0 | 0 | 273 | 01/04/2026, 06/03/2026, 20/03/2026, 10/03/2026, 06/02/2026 |
| Hora Fato | occurrence_time_raw | time(HH:MM:SS) | 0 | 0 | 24,274 | 10:00:00, 12:00:00, 15:00:00, 08:00:00, 14:00:00 |
| Grupo Fato | fact_group | text | 0 | 0 | 2 | CRIMES, CONTRAVENCOES |
| Tipo Enquadramento | category_raw | text | 0 | 0 | 287 | AMEACA, ESTELIONATO, OUTROS CRIMES, LESAO CORPORAL, LESAO CORPORAL CULPOSA DIRECAO VEIC AUTOMOTOR |
| Tipo Fato | fact_type | text | 0 | 0 | 1 | Consumado |
| Municipio Fato | municipality_raw | text | 0 | 0 | 497 | PORTO ALEGRE, CAXIAS DO SUL, CANOAS, SANTA MARIA, PELOTAS |
| Local Fato | place_type | text | 0 | 0 | 9 | OUTROS, RESIDENCIA, VIA PUBLICA, ESTABELECIMENTO COMERCIAL, ETABELECIMENTO ENSINO |
| Bairro | neighborhood_raw | text | 110,539 | 19.47 | 17,271 | Centro, CENTRO, Centro Histórico, São José, INTERIOR |
| Quantidade Vítimas | victim_count | decimal | 13 | 0 | 21 | 1.0, 0.0, 2.0, 3.0, 4.0 |
| Idade Vítima | victim_age | decimal | 107,611 | 18.96 | 100 | 43.0, 31.0, 44.0, 32.0, 37.0 |
| Sexo Vítima | victim_sex | text | 107,858 | 19 | 2 | Feminino, Masculino |
| Cor Vítima | victim_race | text | 107,324 | 18.91 | 6 | Branca, Sem informação, Parda, Preta, Indígena |


Minimização: nenhum campo identificador pessoal existe no arquivo; amostras exibem só valores categóricos/agregados.
