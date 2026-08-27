"""Roda gold_vendas_oficiais.sql via DuckDB e mostra o resultado.
No VS Code: abra este arquivo e clique em Run Python File (▶️), com o
interpretador .venv selecionado (Ctrl+Shift+P > Python: Select Interpreter).
"""
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[1]
sql_path = ROOT / "sql" / "gold_vendas_oficiais.sql"

# o SQL usa caminho relativo ('data/01_...'), então rodamos a partir da raiz do projeto
import os
os.chdir(ROOT)

resultado = duckdb.sql(sql_path.read_text(encoding="utf-8"))
print(resultado)
