# %% [markdown]
# # Vendas oficiais — pipeline em pandas
# CSV bruto -> limpeza em pandas (camada tratada) -> agregação em DuckDB (camada de consumo).
#
# Premissas assumidas por falta de confirmação do negócio: "Hispan" como Espanha;
# reativação identificada pelo time "Customer Success - Retenção"; data ambígua lida
# como DD/MM. A venda conta pela data de fechamento.

# %% Setup
import sys, subprocess
from pathlib import Path

try:
    ROOT = Path(__file__).resolve().parents[1]
except NameError:                                        # rodando célula a célula
    cwd = Path.cwd()
    ROOT = next((p for p in [cwd, *cwd.parents] if (p / "data").exists()), cwd)

RAW       = ROOT / "data" / "01_bronze_raw" / "base_bruta_oportunidades.csv"
PROCESSED = ROOT / "data" / "02_silver_processed"
OUTPUT    = ROOT / "data" / "03_gold_output"
PROCESSED.mkdir(parents=True, exist_ok=True)
OUTPUT.mkdir(parents=True, exist_ok=True)

req = ROOT / "requirements.txt"
if req.exists():
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(req)], check=True)
    print("Dependências instaladas a partir de:", req)
else:
    print("AVISO: requirements.txt não encontrado em", ROOT, "- instale pelo terminal.")

# %% Imports
import pandas as pd
import numpy as np
import re
import duckdb

df = pd.read_csv(RAW, dtype=str).fillna("")
print("Linhas cruas:", len(df))

# %% [markdown]
# ## 1. Olhar o dado antes de limpar
# %%
print("PAÍS:\n", df["pais"].value_counts(), "\n")
print("ESTÁGIO:\n", df["estagio"].value_counts(), "\n")
print("SDR:\n", df["sdr_perfil"].value_counts())

# %% [markdown]
# ## 2. Limpeza
# %%
mapa_pais = {"brasil": "Brasil", "br": "Brasil",
             "espanha": "Espanha", "hispan": "Espanha",   # suposição a validar
             "méxico": "México", "mexico": "México"}
df["pais_norm"] = df["pais"].str.strip().str.lower().map(mapa_pais)

def status(e):
    e = e.strip().lower().replace(" ", "").replace("-", "").replace("/", "")
    if e in {"fechadoganho", "closedwon"}:    return "Ganho"
    if e in {"fechadoperdido", "closedlost"}: return "Perdido"
    return "Pipeline"
df["status_norm"] = df["estagio"].map(status)

meses = {"jan":"01","fev":"02","mar":"03","abr":"04","mai":"05","jun":"06",
         "jul":"07","ago":"08","set":"09","out":"10","nov":"11","dez":"12"}
def parse_data(s):
    s = s.strip()
    if not s: return pd.NaT
    m = re.match(r"(\d{1,2})-([a-z]{3})\.?-(\d{4})", s.lower())
    if m: return pd.Timestamp(f"{m[3]}-{meses[m[2]]}-{int(m[1]):02d}")
    if re.match(r"\d{4}-\d{2}-\d{2}", s): return pd.Timestamp(s)
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        a, b, y = int(m[1]), int(m[2]), int(m[3])
        # DD/MM por padrão; vira MM/DD só quando b passa de 12 e não cabe como mês
        # (ex.: "04/15/2026" é 15 de abril)
        d, mth = (b, a) if b > 12 else (a, b)   # regra a validar
        return pd.Timestamp(f"{y}-{mth:02d}-{d:02d}")
    return pd.NaT
df["data_venda"] = df["data_da_venda"].map(parse_data)

def data_ambigua(s):
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s.strip())
    return bool(m) and int(m[1]) <= 12 and int(m[2]) <= 12
df["data_ambigua"] = df["data_da_venda"].map(data_ambigua)

def parse_moeda(s):
    s = s.replace("R$", "").strip()
    if not s: return np.nan
    if "," in s:
        s = s.replace(".", "").replace(",", ".")   # "1.490,00" -> 1490.00
    elif re.search(r"\.\d{3}$", s):
        s = s.replace(".", "")                     # "1.400" -> 1400, não 1.4
    try: return float(s)
    except ValueError: return np.nan
df["mrr"] = df["valor_mrr"].map(parse_moeda)
df["mrr_ausente"] = df["mrr"].isna()

# %% [markdown]
# ## 3. Classificação e dedup
# A chave de dedup é composta porque id_oportunidade vem vazio em uma linha e repetido
# em duas. Entre duplicatas fica a cópia com mais campos preenchidos.
# %%
antes = len(df)
df["_id"] = df["id_oportunidade"].replace("", np.nan)
df["_completude"] = df.notna().sum(axis=1)

def classe(r):
    if r["plano_anterior_upgrade"].strip():                       return "upgrade"
    if r["sdr_perfil"].strip() == "Customer Success - Retenção":  return "reativacao"
    return "nova_venda"
df["classe"] = df.apply(classe, axis=1)

df_ordenado = df.sort_values("_completude", ascending=False)
eh_duplicata = df_ordenado.duplicated(subset=["_id", "conta", "data_venda"], keep="first")
duplicatas = df_ordenado[eh_duplicata].assign(motivo_rejeicao="duplicata")
df = df_ordenado[~eh_duplicata].copy()
print(f"Dedup: {antes} -> {len(df)} linhas ({len(duplicatas)} duplicatas removidas)")
print(df["classe"].value_counts())

# %% [markdown]
# ## 4. Log do que foi descartado
# Perdido e Pipeline são exclusões de negócio, esperadas. Já ganho_sem_data_fechamento
# é venda fechada saindo do relatório por campo não preenchido no CRM.
# %%
def motivo_exclusao(r):
    if r["status_norm"] != "Ganho": return f"status_{r['status_norm'].lower()}"
    if pd.isna(r["data_venda"]):    return "ganho_sem_data_fechamento"
    return None
df["motivo_rejeicao"] = df.apply(motivo_exclusao, axis=1)

cols_rejeitados = ["_id","conta","pais_norm","status_norm","data_venda","mrr","classe","motivo_rejeicao"]
rejeitados = pd.concat([
    duplicatas[cols_rejeitados],
    df[df["motivo_rejeicao"].notna()][cols_rejeitados],
], ignore_index=True)
rejeitados.to_csv(PROCESSED / "oportunidades_rejeitadas.csv", index=False)
print(f"Rejeitados: {len(rejeitados)} linhas ->", PROCESSED / "oportunidades_rejeitadas.csv")
print(rejeitados["motivo_rejeicao"].value_counts())

ganho_sem_data = rejeitados[rejeitados.motivo_rejeicao == "ganho_sem_data_fechamento"]
if len(ganho_sem_data):
    print(f"ATENÇÃO: R$ {ganho_sem_data['mrr'].sum():,.2f} de MRR em vendas 'Ganho' "
          "ficam fora do relatório só por falta de data de fechamento no CRM.")

# %% [markdown]
# ## 5. Salva a camada SILVER
# %%
silver = df[df["motivo_rejeicao"].isna()].copy()
cols = ["_id","conta","pais_norm","status_norm","data_venda","mrr",
        "plano","unidades_vendidas","classe","data_ambigua","mrr_ausente"]
silver_path = PROCESSED / "oportunidades_tratadas.parquet"
silver[cols].to_parquet(silver_path, index=False)
print("Silver salvo:", len(silver), "linhas")

# %% [markdown]
# ## 6. Camada GOLD — SQL via DuckDB
# %%
con = duckdb.connect()
con.execute(f"CREATE VIEW silver AS SELECT * FROM read_parquet('{silver_path.as_posix()}')")

vendas = con.execute("""
    SELECT strftime(data_venda, '%Y-%m') AS ano_mes, pais_norm AS pais,
           COUNT(*) AS qtd_vendas, SUM(mrr) AS mrr_novo
    FROM silver WHERE classe = 'nova_venda'
    GROUP BY 1, 2 ORDER BY 1, 2
""").df()
print(vendas)

reativacoes = con.execute("""
    SELECT strftime(data_venda, '%Y-%m') AS ano_mes, pais_norm AS pais,
           COUNT(*) AS qtd_reativacoes, SUM(mrr) AS mrr_reativado
    FROM silver WHERE classe = 'reativacao'
    GROUP BY 1, 2 ORDER BY 1, 2
""").df()
print(reativacoes)

vendas.to_csv(OUTPUT / "vendas_oficiais_mes_pais.csv", index=False)
reativacoes.to_csv(OUTPUT / "reativacoes_mes_pais.csv", index=False)
print("Camada de consumo salva em", OUTPUT)

# %% [markdown]
# ## 7. Checagens de qualidade
# %%
print("Datas ambíguas (revisar):", int(df["data_ambigua"].sum()))
print("Vendas com MRR ausente:", int(silver[silver.classe=='nova_venda']["mrr_ausente"].sum()))