# %% [markdown]
# # Explorar gold_vendas_oficiais.sql por etapas
# Cada célula roda a cadeia de CTEs só até um ponto e mostra o resultado —
# útil pra depurar uma etapa sem rodar o arquivo inteiro.
# No VS Code: clique em "Run Cell" (aparece acima de cada `# %%`) com o
# interpretador .venv selecionado (Ctrl+Shift+P > Python: Select Interpreter).

# %% Setup
import os
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)  # o SQL usa caminho relativo ('data/01_...')

SQL_FILE = ROOT / "sql" / "gold_vendas_oficiais.sql"
texto = SQL_FILE.read_text(encoding="utf-8")

# separa o bloco de definição das CTEs (WITH ... até a última fechar)
# do SELECT final, usando o comentário que antecede o SELECT no arquivo
MARCADOR = "-- Camada de consumo"
CTES = texto[texto.index("WITH"): texto.index(MARCADOR)]


def preview(cte: str, limit: int = 50, order_by: str = ""):
    """Roda a cadeia de CTEs e mostra as primeiras `limit` linhas da CTE indicada.

    order_by: trecho SQL de ordenação. Atenção: as colunas vêm como texto
    (ALL_VARCHAR), então para ordenar número use TRY_CAST — ex.:
        preview("bronze", order_by="TRY_CAST(id_oportunidade AS INT)")
        preview("silver", order_by="conta, data_venda DESC")
    """
    ordem = f"ORDER BY {order_by}" if order_by else ""
    return duckdb.sql(f"{CTES}\nSELECT * FROM {cte} {ordem} LIMIT {limit}")


# %% 1. Bronze -> normalização de país e estágio
preview("bronze", limit=50).show(max_width=10000, max_rows=1000)

# %% 1. silver -> normalização de país e estágio
preview("silver_normalizado", limit=50).show(max_width=10000, max_rows=10000)

# %% 2. Parsing de data (conferir a coluna data_ambigua)
preview("silver_com_data", limit=50).show(max_width=10000, max_rows=10000)

# %% 3. Parsing de moeda (conferir mrr_ausente)
preview("silver_com_mrr", limit=50).show(max_width=10000, max_rows=10000)

# %% 4. Classificação (nova_venda / upgrade / reativacao) + dedup
preview("silver_dedup", limit=50).show(max_width=10000, max_rows=10000)

# %% 5. Silver final (o que efetivamente entra na camada gold)
preview("silver", limit=50).show(max_width=10000, max_rows=10000)

# %% 6. RESULTADO FINAL DA CAMADA GOLD
# Roda o arquivo inteiro. Note que aqui NÃO se usa preview(): a gold é o SELECT
# final do .sql, que não é um CTE nomeado — então só o arquivo completo a produz.
duckdb.sql(texto).show(max_width=10000, max_rows=10000)

# %% 6b. Log de rejeitados (linhas descartadas, com motivo)
preview("rejeitados", limit=50).show(max_width=10000, max_rows=10000)

# %% 7. Trecho solto qualquer — cole aqui e rode só esta célula
duckdb.sql("""
           
SELECT *  
    FROM read_csv_auto(
    'data/01_bronze_raw/base_bruta_oportunidades.csv', ALL_VARCHAR = TRUE
),
WHERE
estagio in ('Qualificação')

""").limit(50).show(max_width=10000)

# %%
