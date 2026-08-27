# Uso de IA neste projeto

## Onde acelerou

**Levantamento inicial do dado.** Antes de escrever qualquer regra, pedi o levantamento dos valores distintos de cada coluna categórica e o agrupamento das variações que pareciam significar a mesma coisa. É tarefa mecânica e o resultado é conferível abrindo o CSV, então o risco de aceitar algo errado é baixo.

O prompt foi mais ou menos assim:

> "Liste os valores distintos de pais, estagio, sdr_perfil e plano_anterior_upgrade neste CSV. Agrupe as variações que provavelmente são a mesma coisa (maiúscula, abreviação, idioma diferente). Não decida o mapeamento final, só aponte os candidatos."

O detalhe que importa é o final: candidatos, não decisão. "Hispan" provavelmente é Espanha, mas isso continua sendo palpite até alguém do negócio confirmar.

**Primeira versão do código de limpeza e do SQL.** Usei para não perder tempo com sintaxe de regex e função de data do DuckDB. A regra de negócio dentro do rascunho, essa eu testei linha a linha contra o dado real antes de aceitar. Foi assim que apareceram dois erros que passavam despercebidos em leitura: a heurística de data comparava o número errado e quebrava em `"04/15/2026"`, e o parser de moeda lia `"R$ 1.400"` como 1,4. Nenhum dos dois dava erro de execução. Só apareceram rodando contra as linhas reais.

**Documentação.** Depois que o schema estabilizou, usei para transformar os comentários do código e a estrutura das tabelas em texto legível. Aqui o risco é baixo, porque o material descreve código que já existe e já foi validado.

## Onde não confiei sem conferir

**Regra de negócio com efeito em dinheiro.** Se "Hispan" é Espanha, se reativação entra ou não como venda oficial, se a data de fechamento é mesmo a referência: isso é decisão de quem responde pelo número, não minha nem da ferramenta. Por isso as três premissas estão marcadas no código como suposição em vez de terem virado fato só por funcionarem no teste.

**Qualquer coisa que apaga linha.** Uma regra de dedup plausível pode, no dataset específico, remover uma venda legítima. Antes de aceitar, conferi quantas linhas entraram, quantas saíram e quais especificamente foram descartadas. Foi conferindo isso que vi que uma das duplicatas do id `1008` tinha MRR preenchido e a outra não, o que fez o critério de desempate deixar de ser detalhe.

**Número que vai para outra pessoa.** Escrevi a agregação duas vezes, em pandas e em SQL, e só usei o resultado depois que as duas bateram. Se tivessem divergido, seria bug em uma delas, não número para reportar.

**Classificação que afeta meta ou comissão.** O que conta como venda oficial mexe com meta de time e remuneração de SDR. Regra sugerida por ferramenta nesse ponto precisa de aval de quem é dono da métrica antes de virar oficial.

## Critério

Uso para ganhar tempo onde consigo verificar a saída: levantamento, rascunho de código, redação sobre coisa já validada. Não uso para decidir o que eu não teria como conferir sozinho.
