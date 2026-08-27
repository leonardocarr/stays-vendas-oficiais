# Stays — Vendas Oficiais

Pipeline que pega um extrato bruto de oportunidades do CRM e devolve a contagem de vendas oficiais por mês e por país, separando venda nova de upgrade e reativação.

## O problema

O CRM registra tudo como "oportunidade": a venda nova, o upgrade de plano de quem já é cliente e a reativação de quem tinha cancelado. Os três trazem receita, e o relatório financeiro soma os três. Só que a pergunta "o comercial está trazendo cliente novo, e em que ritmo?" precisa de um número diferente. Somar upgrade junto responde errado essa pergunta.

A explicação disso em linguagem não técnica está em [docs/comunicacao_lideranca.md](docs/comunicacao_lideranca.md).

## Modelo em camadas

Três camadas, no padrão bruto → tratado → consumo (o mesmo que a literatura chama de bronze/silver/gold):

| Camada | Grão | Chave | O que trata |
|---|---|---|---|
| **Bruto** — bronze (`data/01_bronze_raw/`) | 1 linha = 1 registro como veio do CRM | Não tem. O arquivo traz id repetido e id vazio. | Nada. O CSV é lido com todas as colunas como texto, sem conversão nenhuma. Serve de fonte de auditoria: quando um número parecer estranho lá na frente, é aqui que se confere o que o CRM mandou de fato. |
| **Tratado** — silver (`data/02_silver_processed/`) | 1 linha = 1 oportunidade, já sem duplicatas | Composta: `id_oportunidade` + `conta` + `data_venda`. As três juntas, porque o id sozinho não dá conta (vem vazio em uma linha e repetido em duas). | Normaliza país e estágio, converte data e valor, remove duplicatas e classifica cada linha em `nova_venda`, `upgrade` ou `reativacao`. Também marca as linhas problemáticas com `data_ambigua` e `mrr_ausente`. Mantém o grão de oportunidade, então dá para abrir qualquer número da camada seguinte e ver exatamente quais vendas o compõem. O que é descartado vai para um log separado, com o motivo. |
| **Consumo** — gold (`data/03_gold_output/`) | 1 linha = `ano_mes` × `pais` × `tipo_venda` | `ano_mes` + `pais` + `tipo_venda` | Filtra só o que está como "Ganho", tira os upgrades da contagem e agrega quantidade e MRR. É a camada que vai para o BI. Quem consome ela não precisa saber que existe um país escrito como "Hispan" no dado de origem. |

Uma regra atravessa as três: **a venda conta pela data de fechamento** (`data_da_venda`), não pela data de criação da oportunidade. É o que faz um negócio fechado em fevereiro aparecer em fevereiro, mesmo tendo entrado no funil em janeiro.

Sobre a escolha dessa arquitetura e as alternativas que descartei, ver [docs/metodologia.md](docs/metodologia.md).

## Como rodar

```bash
# pipeline completo: gera o parquet da silver e os CSVs da gold
python notebooks/pipeline.py

# só a camada gold, direto do CSV bruto, via SQL
python sql/run_sql.py
```

Para inspecionar o SQL por etapas em vez de rodar o arquivo inteiro, use [sql/explorar_sql.py](sql/explorar_sql.py) no VS Code. Cada célula `# %%` mostra o resultado de uma CTE.

## Duas implementações

A mesma lógica está escrita duas vezes:

- [notebooks/pipeline.py](notebooks/pipeline.py) — pandas do bruto até o tratado, DuckDB para agregar
- [sql/gold_vendas_oficiais.sql](sql/gold_vendas_oficiais.sql) — SQL puro, do CSV até a agregação final

Rodei as duas contra os mesmos dados e as 16 linhas de resultado batem. Foi assim que ganhei confiança no número antes de escrever qualquer coisa sobre ele: se as duas discordassem, haveria bug em alguma, e eu saberia disso antes de reportar.

## O que é descartado, e por quê

Nenhuma linha sai do pipeline sem registro. Rode `python sql/run_rejeitados.py` (ou veja a seção 4 do `pipeline.py`, que grava em `data/02_silver_processed/oportunidades_rejeitadas.csv`).

Das 43 linhas do extrato, 15 não chegam na camada final:

- `status_perdido` (4) e `status_pipeline` (4): a oportunidade não é venda fechada. Exclusão de negócio, esperada.
- `duplicata` (2): mesmo id, conta e data repetidos no extrato. Também esperada.
- `ganho_sem_data_fechamento` (5): essas incomodam. São vendas marcadas como "Ganho" no CRM, mas com o campo de data vazio. Como a regra define a venda pela data de fechamento, elas ficam de fora. São **R$ 5.860 de MRR já fechado que não aparecem no relatório**, não porque alguém decidiu excluir, mas porque um campo não foi preenchido no CRM.

Esse último caso só apareceu porque o log separa por motivo. Uma contagem agregada de "15 linhas removidas" teria escondido a diferença entre uma exclusão correta e receita sumindo por falha de cadastro.

## Riscos de qualidade no dado bruto

**1. A chave de negócio não é confiável.** Em 43 linhas, uma tem `id_oportunidade` vazio e dois ids aparecem repetidos (`1004` e `1008`). Sem chave única garantida, dá para contar a mesma venda duas vezes ou jogar fora uma venda real.

*Tratamento:* dedup pela chave composta (`id_oportunidade`, `conta`, `data_venda`), mantendo entre as duplicatas o registro mais completo. O total removido é impresso na execução (`Dedup: 43 -> 41 linhas`) e as linhas descartadas vão para o log. No caso do id `1008`, as duas cópias eram iguais exceto pelo MRR: uma tinha 990,00 e a outra estava vazia. O critério de completude manteve a certa. Sem esse desempate, R$ 990 sairiam do relatório em silêncio.

**2. As datas vêm em formatos misturados, e parte delas é ambígua.** O campo `data_da_venda` tem `"14-fev.-2026"`, ISO (`"2026-05-08"`) e o formato com barras. Nas barras não há indicação de ser DD/MM ou MM/DD, e quando dia e mês são ambos menores que 13 (como em `"01/02/2026"`) as duas leituras são válidas e caem em meses diferentes. O efeito é venda no mês errado, o que distorce tendência mensal e comissionamento.

*Tratamento:* adoto DD/MM como padrão e só inverto quando o segundo número passa de 12, o que torna DD/MM impossível. As linhas realmente ambíguas ganham a flag `data_ambigua` em vez de serem resolvidas em silêncio: são 10 das 43. Nelas, as duas leituras sempre caem em meses diferentes, e isso afeta R$ 5.380 de MRR em vendas ganhas. A saída de verdade é conferir essas datas no CRM; a flag existe para que alguém saiba que precisa conferir.

**3. As categorias foram digitadas de formas diferentes.** São 8 grafias distintas em `pais` para 3 países: `"BRASIL"`, `"Brasil"`, `"brasil"`, `"BR"`, `"ESPANHA"`, `"Espanha"`, `"Hispan"` e `"México"`. Em `estagio` são 7 valores, misturando português e inglês: `"Fechado - Ganho"`, `"Fechado/Ganho"`, `"fechado/ganho"`, `"Closed Won"`, além dos equivalentes de perdido e do `"Qualificação"`. Isso sub ou superestima vendas por país e pode fazer uma venda ganha não ser reconhecida como tal.

*Tratamento:* um mapa de normalização único, em um só lugar do código, com saída explícita para `NULL` quando o valor não é reconhecido. Um valor novo aparecendo no extrato fica visível como não mapeado, em vez de ser descartado ou classificado errado por acidente.

## Outros riscos encontrados

Os três acima são os que respondem ao que foi pedido. Estes apareceram durante a análise e valem registro.

**`sdr_perfil` vem vazio em 9 das 43 linhas, e é ele que identifica reativação.** Esse é o mais incômodo. A regra de classificação só reconhece reativação quando `sdr_perfil` é `"Customer Success - Retenção"`. Sem o campo, a linha cai em `nova_venda` por descarte, não por evidência. Hoje **6 das 19 vendas novas do relatório** estão nessa situação: se alguma delas for reativação, está sendo contada na conta errada, inflando aquisição e escondendo recuperação de churn.

Não dá para resolver isso no código, porque o dado que decidiria não está no arquivo. O tratamento honesto é: manter a classificação atual, deixar registrado que ela vale enquanto o campo estiver preenchido, e pedir ao time do CRM ou a obrigatoriedade do campo, ou um flag próprio de reativação, do mesmo jeito que o upgrade já tem em `plano_anterior_upgrade`. Depender de "quem atendeu" para dizer "o que foi a venda" é frágil: basta uma reativação ser tocada por outro time para ela virar venda nova sem ninguém perceber.

**`valor_mrr` mistura formatos.** Convivem `"1.490,00"` e `"R$ 1.400"`. No segundo caso o ponto é separador de milhar, mas `float("1.400")` em Python devolve `1.4`. A regra adotada lê ponto seguido de três dígitos, sem vírgula na string, como milhar. Foi um bug real encontrado na primeira versão do código.

**6 vendas entram no relatório sem valor de MRR.** A contagem delas está certa, mas o `SUM` ignora nulo em silêncio, então o `mrr_total` do grupo fica menor do que a realidade, ou nulo quando nenhuma linha do grupo tem valor. A flag `mrr_ausente` marca essas linhas na camada tratada.

**Vendas ganhas sem data de fechamento.** Descrito na seção anterior: 5 linhas, R$ 5.860 de MRR fora do relatório.

## Premissas em aberto

Três decisões foram tomadas por falta de quem confirmasse, e estão marcadas como suposição no código:

- `"Hispan"` sendo tratado como Espanha.
- Data ambígua sendo lida como DD/MM por padrão.
- `"R$ 1.400"` valendo 1400 e não 1,4.

Se alguém do negócio confirmar ou corrigir qualquer uma, o ajuste é em um ponto só do código.

## Uso de IA

Detalhes de onde usei, com os prompts, e onde não confiei sem conferir: [docs/uso_de_ia.md](docs/uso_de_ia.md).

## Documentação do modelo

[docs/data_dictionary.md](docs/data_dictionary.md) descreve cada coluna das três camadas, para alguém do time consumir a saída sem precisar ler o pipeline nem me perguntar.
