# Dicionário de dados

Descreve as três camadas do pipeline, coluna por coluna, para quem for consumir a saída sem ler o código.

Rascunhado com apoio de IA a partir do schema e dos comentários de premissa deixados no código, e revisado à mão antes de publicar. A ideia é que atualizar isso custe pouco quando o schema mudar, em vez de virar aquele documento que envelhece porque ninguém lembra de mexer. O critério de uso está em [uso_de_ia.md](uso_de_ia.md).

## Camada bruta (bronze)

**Arquivo:** `data/01_bronze_raw/base_bruta_oportunidades.csv`
**Grão:** 1 linha = 1 registro exportado do CRM, sem tratamento
**Chave:** não tem chave garantida

| Coluna | Tipo | Descrição | Observação |
|---|---|---|---|
| `id_oportunidade` | texto | Id da oportunidade no CRM | Vem vazio em uma linha e repetido em duas |
| `conta` | texto | Nome do cliente | |
| `pais` | texto | País da conta, digitado livre | `BRASIL`, `Brasil`, `BR`, `brasil`, `Hispan` |
| `estagio` | texto | Estágio do funil | Mistura português e inglês |
| `data_da_venda` | texto | Data de fechamento | Três formatos misturados, parte ambígua |
| `valor_mrr` | texto | Receita recorrente mensal | Formato BR e americano misturados, com e sem `R$` |
| `plano` | texto | Plano vendido | |
| `unidades_vendidas` | texto | Quantidade de licenças | |
| `sdr_perfil` | texto | Time responsável | `Customer Success - Retenção` marca reativação |
| `plano_anterior_upgrade` | texto | Plano anterior | Só é preenchido em upgrade; é essa presença que sinaliza o upgrade |
| `motivo_do_upgrade` | texto | Motivo do upgrade | Não usado na saída atual |
| `valor_nmrr_upgrade` | texto | MRR incremental do upgrade | Não usado na saída atual |
| `unidades_vendidas_upgrade` | texto | Licenças adicionais | Não usado na saída atual |

## Camada tratada (silver)

**Arquivo:** `data/02_silver_processed/oportunidades_tratadas.parquet`
**Grão:** 1 linha = 1 oportunidade, sem duplicatas
**Chave:** `_id` + `conta` + `data_venda` (composta; o id sozinho não é confiável)

| Coluna | Tipo | Descrição |
|---|---|---|
| `_id` | texto ou nulo | Id do CRM; vazio virou nulo |
| `conta` | texto | Nome da conta |
| `pais_norm` | texto | `Brasil`, `Espanha` ou `México`; nulo quando o valor de origem não foi reconhecido |
| `status_norm` | texto | `Ganho`, `Perdido` ou `Pipeline` |
| `data_venda` | data | Data de fechamento convertida; nula quando não deu para ler |
| `mrr` | decimal | Receita recorrente mensal convertida |
| `plano` | texto | Plano vendido |
| `unidades_vendidas` | texto | Licenças |
| `classe` | texto | `nova_venda`, `upgrade` ou `reativacao` |
| `data_ambigua` | booleano | Verdadeiro quando DD/MM e MM/DD dariam datas válidas e diferentes. Confira antes de usar o mês |
| `mrr_ausente` | booleano | Verdadeiro quando não havia valor de MRR para converter |

Como `classe` é definida: `upgrade` quando `plano_anterior_upgrade` está preenchido; senão `reativacao` quando `sdr_perfil` é `Customer Success - Retenção`; senão `nova_venda`.

## Log de rejeitados

**Arquivo:** `data/02_silver_processed/oportunidades_rejeitadas.csv`, ou a CTE `rejeitados` no SQL (ver `sql/run_rejeitados.py`)
**Grão:** 1 linha = 1 oportunidade descartada
**Chave:** `_id` + `motivo_rejeicao`

Além de `motivo_rejeicao`, traz as mesmas colunas da camada tratada, com o contexto que a linha tinha quando saiu.

| `motivo_rejeicao` | Significado |
|---|---|
| `status_perdido` | Oportunidade perdida. Exclusão de negócio |
| `status_pipeline` | Ainda em aberto no funil. Exclusão de negócio |
| `duplicata` | Mesmo id, conta e data já contabilizados. Ficou a cópia mais completa |
| `ganho_sem_data_fechamento` | Venda ganha, mas sem data preenchida no CRM. Não é decisão de negócio; é receita que sai do relatório por falta de cadastro |

Os três primeiros são esperados. O último merece acompanhamento: hoje são R$ 5.860 de MRR fechado fora da contagem.

## Camada de consumo (gold)

**Arquivo:** `data/03_gold_output/vendas_oficiais_mes_pais.csv`. O `pipeline.py` também grava `reativacoes_mes_pais.csv` separado; a versão SQL entrega tudo numa tabela só, distinguindo pela coluna `tipo_venda`.
**Grão:** 1 linha = `ano_mes` × `pais` × `tipo_venda`
**Chave:** as três colunas acima

| Coluna | Tipo | Descrição |
|---|---|---|
| `ano_mes` | texto `AAAA-MM` | Mês de fechamento |
| `pais` | texto | `Brasil`, `Espanha` ou `México` |
| `tipo_venda` | texto | `nova_venda` ou `reativacao`. Upgrade não aparece aqui |
| `qtd_vendas` | inteiro | Quantidade de oportunidades no grupo |
| `mrr_total` | decimal | Soma do MRR. Fica nulo quando nenhuma linha do grupo tinha valor |

Serve para responder quantas vendas novas e quantas reativações foram fechadas por mês e país, e quanto de MRR isso representa.

Não serve para receita total do mês. Essa inclui upgrade, e está no relatório financeiro. O motivo da diferença está em [comunicacao_lideranca.md](comunicacao_lideranca.md).

## Premissas em aberto

- `Hispan` tratado como Espanha. Não confirmado com o negócio.
- Data ambígua lida como DD/MM.
- `R$ 1.400` lido como 1400, com o ponto valendo separador de milhar.

As três também estão marcadas no código, no ponto onde cada uma é aplicada. Se alguém confirmar ou corrigir, é lá que muda.
