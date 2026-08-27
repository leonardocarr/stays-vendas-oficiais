# Por que camadas, e o que mudaria com mais escala

## A escolha

O pipeline separa dado cru, dado limpo no grão atômico e dado agregado. É o padrão que o Databricks batizou de medallion, mas a ideia é bem mais antiga e aparece com outros nomes em qualquer stack: staging/cleaned/curated, ou staging/intermediate/marts no dbt.

Para um extrato de CRM que chega com formato instável, o ganho é prático. Cada camada tem uma responsabilidade só, e dá para apontar em qual delas um problema nasceu. Sem isso, todo o tratamento acabaria dentro de uma query única de duzentas linhas, onde ninguém consegue isolar o que a regra de país fez do que a regra de data fez.

Vale notar que a camada tratada já está no grão de uma tabela fato: uma linha por venda, com país, data, classe e MRR como atributos. A camada de consumo é uma agregação possível em cima dela, não a única. Se amanhã pedirem a quebra por plano ou por SDR, não é preciso mexer no pipeline: é escrever outra agregação sobre a mesma base tratada.

## O que considerei e não usei

**dbt.** É o mesmo modelo em camadas, só que como framework, com testes declarativos em YAML, lineage e documentação geradas sozinhas. Para um CSV rodado uma vez, montar um projeto dbt (que ainda quer um warehouse por trás) custa mais do que entrega. Se este pipeline virasse recorrente, com o CRM exportando toda semana, seria a primeira migração que eu faria. Não pelo SQL, que seria praticamente o mesmo, mas para parar de manter documentação e testes na mão.

**Star schema.** Cheguei a esboçar `dim_pais`, `dim_calendario` e `dim_conta` separadas, ligadas por chave a uma fato de vendas. Não segui. Com três países e uma fonte pequena, essas "dimensões" não têm atributo próprio nenhum que justifique uma tabela: seriam listas de dois ou três valores, adicionando join e complexidade sem devolver nada. Star schema se paga quando as dimensões carregam atributos de verdade (um cadastro de conta com segmento, porte, data de entrada) ou quando o volume e a ferramenta de BI pedem esse formato. Aqui seria aplicar o padrão por reflexo.

**Great Expectations ou testes formais.** Hoje as checagens são flags calculadas junto com a transformação (`data_ambigua`, `mrr_ausente`) mais alguns prints. Funciona quando uma pessoa acompanha a execução. Com mais gente consumindo o dado, eu trocaria por testes declarativos que quebram o pipeline e emitem relatório, em vez de depender de alguém reparar em uma linha de log dizendo que 10 datas ficaram ambíguas.

## O que eu mudaria já

Manter duas implementações da mesma lógica foi útil como conferência, mas não é algo para carregar adiante. Em produção eu escolheria uma como oficial, e seria o SQL: roda em qualquer motor, é mais fácil de testar sozinho e é o que um time de analytics engineering usa no dia a dia. A versão em pandas ficaria como exploração, fora do caminho de produção.

## Resumo

O modelo em camadas resolve bem este caso, e está implementado de forma que dá para auditar: grão atômico na camada tratada, agregação explícita na de consumo, premissas marcadas no código. As alternativas acima não são melhores aqui; são passos de maturidade que fazem sentido quando o pipeline passa a rodar sozinho e mais gente depende dele.
