"""Mostra o log de rejeitados (linhas descartadas do pipeline, com motivo).

Reaproveita a cadeia de CTEs de gold_vendas_oficiais.sql e seleciona da CTE
"rejeitados" em vez da agregação gold — não duplica a lógica de limpeza.

No VS Code: Run Python File (▶️), com o interpretador .venv selecionado.
"""
import os
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)  # o SQL usa caminho relativo ('data/01_...')

texto = (ROOT / "sql" / "gold_vendas_oficiais.sql").read_text(encoding="utf-8")
MARCADOR = "-- Camada de consumo"
CTES = texto[texto.index("WITH"): texto.index(MARCADOR)]

rejeitados = duckdb.sql(f"{CTES}\nSELECT * FROM rejeitados ORDER BY motivo_rejeicao, conta").df()

print(rejeitados.to_string(index=False))
print()
print("Total de linhas rejeitadas:", len(rejeitados))
print(rejeitados["motivo_rejeicao"].value_counts())
print()

ganho_sem_data = rejeitados[rejeitados.motivo_rejeicao == "ganho_sem_data_fechamento"]
if len(ganho_sem_data):
    print(
        f"Atenção: R$ {ganho_sem_data['mrr'].sum():,.2f} de MRR em vendas ganhas ficam "
        "fora do relatório por falta de data de fechamento no CRM. Vale checar com o time."
    )
