# Uso de IA neste projeto

## Onde acelerou

### 1. Levantamento inicial do dado

Antes de escrever qualquer regra, pedi o levantamento dos valores distintos de cada coluna categórica e o agrupamento das variações que pareciam significar a mesma coisa. É tarefa mecânica e o resultado é conferível abrindo o CSV, então o risco de aceitar algo errado é baixo.

> Liste os valores distintos de pais, estagio, sdr_perfil e plano_anterior_upgrade neste CSV. Agrupe as variações que provavelmente são a mesma coisa (maiúscula, abreviação, idioma diferente). Não decida o mapeamento final, só aponte os candidatos.

O detalhe que importa é o final: candidatos, não decisão. "Hispan" provavelmente é Espanha, mas isso continua sendo palpite até alguém do negócio confirmar.

### 2. Primeira versão do código de limpeza e do SQL

Aqui a divisão é a que uso sempre: eu defino a regra, a ferramenta escreve a sintaxe. Não peço "trate as datas desse arquivo", porque isso entrega a decisão. Peço a implementação de uma regra que já decidi.

> Escreva uma função Python que converta para data estes três formatos: "14-fev.-2026", "2026-05-08" e "01/02/2026". No terceiro, assuma DD/MM e inverta para MM/DD apenas quando o segundo número passar de 12. Retorne nulo quando não reconhecer o formato, sem levantar exceção.

O que ganho é tempo de regex e de função de data do DuckDB. O que não delego é a regra em si: quem decidiu que o padrão é DD/MM fui eu, e está marcado no código como suposição.

Todo rascunho assim passou por teste contra o dado real antes de entrar. Foi o que revelou dois erros que ninguém pega lendo: a heurística de data comparava o número errado e quebrava em `"04/15/2026"`, e o parser de moeda lia `"R$ 1.400"` como 1,4. Nenhum dos dois levantava exceção. Só apareceram rodando linha a linha.

### 3. Documentação

Depois que o schema estabilizou, usei para transformar schema e comentários de código em texto legível. O risco é baixo porque o material descreve código que já existe e já foi validado, mas o prompt carrega uma trava:

> A partir deste schema e dos comentários do código, escreva uma tabela com uma linha por coluna: nome, tipo e descrição. Use apenas o que está no código. Onde a intenção não estiver clara, escreva "não documentado" em vez de deduzir.

Sem essa última frase, o que vem de volta é plausível e inventado. Uma coluna chamada `valor_nmrr_upgrade` ganha uma descrição convincente sobre receita incremental que ninguém confirmou. "Não documentado" é uma resposta útil; um palpite bem escrito, não.

## Onde não confiei sem conferir

**Regra de negócio com efeito em dinheiro.** Se "Hispan" é Espanha, se reativação entra como venda oficial, se a data de fechamento é mesmo a referência: isso é decisão de quem responde pelo número. Por isso as três premissas estão marcadas no código como suposição, em vez de terem virado fato só por funcionarem no teste.

**Qualquer coisa que apaga linha.** Uma regra de dedup plausível pode, no dataset específico, remover uma venda legítima. Antes de aceitar, conferi quantas linhas entraram, quantas saíram e quais especificamente foram descartadas. Foi assim que vi que uma das duplicatas do id `1008` tinha MRR preenchido e a outra não, o que transformou o critério de desempate de detalhe em coisa que preserva R$ 990.

**Número que vai para outra pessoa.** Escrevi a agregação duas vezes, em pandas e em SQL, e só usei o resultado depois que as duas bateram. Se tivessem divergido, seria bug em uma delas, não número para reportar.

**Classificação que afeta meta ou comissão.** O que conta como venda oficial mexe com meta de time e remuneração de SDR. Regra sugerida por ferramenta nesse ponto precisa de aval de quem é dono da métrica antes de virar oficial.

## O critério, na prática

Antes de aceitar qualquer saída, faço uma pergunta só: **se isso estiver errado, como eu descubro?**

Se a resposta for "rodando contra o dado" ou "relendo o código", uso sem medo, porque tenho como verificar. Levantamento de valores, rascunho de regex, redação sobre código pronto: tudo isso cai aqui.

Se a resposta for "só saberia se alguém do negócio me contasse", não uso para decidir. Uso no máximo para listar as opções, e a escolha fica marcada como pendência. É a diferença entre a ferramenta acelerar o trabalho e ela tomar decisão no lugar de quem responde por ela.

## Documentar o modelo de dados sem virar gargalo

O problema que essa proposta resolve não é escrever o dicionário. É ele continuar verdadeiro depois. Documentação escrita à parte envelhece: alguém muda a regra, esquece o documento, e em três meses ele mente. Quando isso acontece, todo mundo volta a perguntar para quem escreveu o pipeline, que é exatamente a dependência que se queria eliminar.

A proposta é gerar o dicionário a partir do código, com estas quatro partes:

**A fonte da verdade é o código, não um documento paralelo.** O que alimenta a geração é o schema de cada camada mais os comentários que registram decisão, incluindo os marcadores de suposição. Nada de manter descrição de coluna em planilha separada.

**A geração entra no mesmo commit da mudança.** Quando uma alteração mexe em schema ou em regra, o dicionário é regerado e o diff dele vai junto no mesmo commit. Assim a documentação nunca fica mais de um commit atrás do código. Sem isso, volta a depender de alguém lembrar.

**O prompt proíbe inferência.** É a trava da etapa 3 acima: descreva o que está no código, escreva "não documentado" no resto. O maior risco aqui não é a ferramenta errar o tipo de uma coluna, é ela inventar significado de negócio com texto convincente.

**Uma pessoa revisa antes de entrar.** A ferramenta faz o rascunho, alguém confirma. Leva minutos e é o que separa documentação gerada de documentação confiável.

O que decide se alguém consegue consumir sem me procurar não é a lista de colunas. É o dicionário responder as quatro perguntas que fazem a pessoa vir perguntar:

- O que cada coluna significa e de que tipo é.
- Qual o grão e qual a chave, para ninguém fazer join errado e duplicar linha sem perceber.
- Que pergunta a tabela responde e, principalmente, **qual ela não responde**. É o que evita alguém usar `mrr_total` achando que é a receita do mês.
- O que foi descartado, por quê, e quais premissas ainda não foram confirmadas.

Essas duas últimas são as que costumam gerar a pergunta. "Por que esse número não bate com o financeiro?" e "cadê a venda da conta X?" têm resposta escrita em [data_dictionary.md](data_dictionary.md), no log de rejeitados e em [comunicacao_lideranca.md](comunicacao_lideranca.md), sem precisar de mim.

Vale dizer o que isso vira em escala. Com o pipeline rodando de forma recorrente, essa rotina manual é substituída pelo que o dbt já faz nativamente: documentação e lineage gerados a partir dos próprios modelos. A versão descrita aqui é o mesmo princípio no tamanho deste projeto, e o raciocínio completo está em [metodologia.md](metodologia.md).
