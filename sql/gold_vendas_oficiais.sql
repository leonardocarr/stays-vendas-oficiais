-- =====================================================================================
-- Vendas oficiais por mês e país
--
-- Grão da saída: 1 linha = ano_mes x pais x tipo_venda (nova_venda | reativacao)
-- Fonte: data/01_bronze_raw/base_bruta_oportunidades.csv
-- Motor: DuckDB, lendo o CSV direto (não precisa de carga prévia)
--
-- Rodar com:  python sql/run_sql.py
--
-- Regras aplicadas:
--   1. País normalizado (BRASIL / Brasil / BR viram Brasil; idem Espanha e México)
--   2. Upgrade não entra na contagem de vendas
--   3. Reativação sai em linha própria, nunca somada à venda nova nem descartada
--   4. A venda conta pela data de fechamento, não pela data de criação
--   5. Só estágio "Ganho" conta como venda
--   6. Toda linha descartada vai para a CTE "rejeitados" com o motivo
--
-- Premissas assumidas por falta de confirmação do negócio:
--   - "Hispan" tratado como Espanha
--   - Data ambígua lida como DD/MM
--   - "R$ 1.400" lido como 1400 (ponto = separador de milhar)
-- =====================================================================================

WITH bronze AS (
    SELECT *
    FROM read_csv_auto('data/01_bronze_raw/base_bruta_oportunidades.csv', ALL_VARCHAR = TRUE)
),

-- Normalização de país e estágio. O mapa é explícito e o ELSE cai em NULL, para que um
-- valor novo apareça como não mapeado em vez de ser classificado errado por acidente.
silver_normalizado AS (
    SELECT
        NULLIF(trim(id_oportunidade), '')  AS id_oportunidade,
        trim(conta)                        AS conta,
        trim(pais)                         AS pais_bruto,

        CASE lower(trim(pais))
            WHEN 'brasil'  THEN 'Brasil'
            WHEN 'br'      THEN 'Brasil'
            WHEN 'espanha' THEN 'Espanha'
            WHEN 'hispan'  THEN 'Espanha'   -- suposição a validar
            WHEN 'mexico'  THEN 'México'
            WHEN 'méxico'  THEN 'México'
            ELSE NULL
        END AS pais_norm,

        CASE
            WHEN lower(regexp_replace(estagio, '[\s\-/]', '', 'g')) IN ('fechadoganho', 'closedwon')
                THEN 'Ganho'
            WHEN lower(regexp_replace(estagio, '[\s\-/]', '', 'g')) IN ('fechadoperdido', 'closedlost')
                THEN 'Perdido'
            ELSE 'Pipeline'
        END AS status_norm,

        trim(data_da_venda)          AS data_bruta,
        trim(valor_mrr)              AS valor_mrr_bruto,
        trim(plano_anterior_upgrade) AS plano_anterior_upgrade,
        trim(sdr_perfil)             AS sdr_perfil
    FROM bronze
),

-- Data de fechamento. Três formatos convivem no campo: "14-fev.-2026", ISO "2026-05-08"
-- e o formato com barras, que pode ser DD/MM ou MM/DD sem nada indicando qual.
silver_datas AS (
    SELECT
        *,
        regexp_extract(data_bruta, '^(\d{1,2})-([a-zç]{3})\.?-(\d{4})$', 1)        AS pt_dia,
        lower(regexp_extract(data_bruta, '^(\d{1,2})-([a-zç]{3})\.?-(\d{4})$', 2)) AS pt_mes_abrev,
        regexp_extract(data_bruta, '^(\d{1,2})-([a-zç]{3})\.?-(\d{4})$', 3)        AS pt_ano,
        TRY_CAST(split_part(data_bruta, '/', 1) AS INT) AS dm_a,
        TRY_CAST(split_part(data_bruta, '/', 2) AS INT) AS dm_b,
        TRY_CAST(split_part(data_bruta, '/', 3) AS INT) AS dm_y
    FROM silver_normalizado
),

silver_com_data AS (
    SELECT
        * EXCLUDE (pt_dia, pt_mes_abrev, pt_ano, dm_a, dm_b, dm_y),

        CASE
            WHEN pt_mes_abrev IS NOT NULL AND pt_mes_abrev <> '' THEN
                TRY_CAST(
                    pt_ano || '-' ||
                    CASE pt_mes_abrev
                        WHEN 'jan' THEN '01' WHEN 'fev' THEN '02' WHEN 'mar' THEN '03' WHEN 'abr' THEN '04'
                        WHEN 'mai' THEN '05' WHEN 'jun' THEN '06' WHEN 'jul' THEN '07' WHEN 'ago' THEN '08'
                        WHEN 'set' THEN '09' WHEN 'out' THEN '10' WHEN 'nov' THEN '11' WHEN 'dez' THEN '12'
                    END || '-' || lpad(pt_dia, 2, '0')
                AS DATE)

            WHEN regexp_matches(data_bruta, '^\d{4}-\d{2}-\d{2}$') THEN
                TRY_CAST(data_bruta AS DATE)

            WHEN dm_a IS NOT NULL AND dm_b IS NOT NULL AND dm_y IS NOT NULL THEN
                CASE WHEN dm_b > 12
                     THEN make_date(dm_y, dm_a, dm_b)   -- b não cabe como mês, então só pode ser MM/DD
                     ELSE make_date(dm_y, dm_b, dm_a)   -- padrão DD/MM
                END
            ELSE NULL
        END AS data_venda,

        -- Com os dois números abaixo de 13, DD/MM e MM/DD dão datas válidas e diferentes.
        -- A flag existe para sinalizar que o mês precisa de conferência na origem.
        (dm_a IS NOT NULL AND dm_b IS NOT NULL AND dm_a <= 12 AND dm_b <= 12 AND dm_a <> dm_b) AS data_ambigua
    FROM silver_datas
),

-- MRR. O campo mistura "1.490,00", "R$ 1.400", "490.00" e "590".
silver_moeda AS (
    SELECT
        *,
        regexp_replace(trim(replace(valor_mrr_bruto, 'R$', '')), '\s', '', 'g') AS valor_limpo
    FROM silver_com_data
),

silver_com_mrr AS (
    SELECT
        * EXCLUDE (valor_limpo),
        CASE
            WHEN valor_limpo = '' THEN NULL
            WHEN valor_limpo LIKE '%,%'                    -- padrão BR: ponto separa milhar, vírgula decimal
                THEN TRY_CAST(replace(replace(valor_limpo, '.', ''), ',', '.') AS DOUBLE)
            WHEN regexp_matches(valor_limpo, '\.\d{3}$')   -- ponto e três dígitos sem vírgula: milhar
                THEN TRY_CAST(replace(valor_limpo, '.', '') AS DOUBLE)
            ELSE TRY_CAST(valor_limpo AS DOUBLE)
        END AS mrr
    FROM silver_moeda
),

-- Upgrade é sinalizado por plano_anterior_upgrade preenchido. Confirmei que as outras três
-- colunas de upgrade (motivo, nmrr, unidades) só aparecem juntas com ela, então uma sozinha
-- basta. O COALESCE existe porque a coluna vazia chega como NULL, e sem ele a condição
-- dependeria de NULL se comportar como falso dentro do CASE.
silver_classificado AS (
    SELECT
        *,
        CASE
            WHEN COALESCE(plano_anterior_upgrade, '') <> ''  THEN 'upgrade'
            WHEN sdr_perfil = 'Customer Success - Retenção'  THEN 'reativacao'
            ELSE 'nova_venda'
        END AS classe,
        mrr IS NULL AS mrr_ausente
    FROM silver_com_mrr
),

-- Dedup pela chave composta, já que id_oportunidade sozinho vem vazio e repetido.
-- O desempate mantém a cópia mais completa: no id 1008, uma linha tinha MRR e a outra não.
silver_dedup AS (
    SELECT * EXCLUDE (rn)
    FROM (
        SELECT
            *,
            ROW_NUMBER() OVER (
                PARTITION BY id_oportunidade, conta, data_venda
                ORDER BY (mrr IS NOT NULL)::INT + (pais_norm IS NOT NULL)::INT DESC
            ) AS rn
        FROM silver_classificado
    )
    WHERE rn = 1
),

silver AS (
    SELECT
        id_oportunidade, conta,
        pais_norm AS pais,
        status_norm, data_venda, mrr, classe, data_ambigua, mrr_ausente
    FROM silver_dedup
    WHERE status_norm = 'Ganho' AND data_venda IS NOT NULL
),

-- Log do que foi descartado. Perdido e Pipeline são exclusões de negócio, esperadas.
-- Já ganho_sem_data_fechamento é venda fechada saindo do relatório por campo não preenchido
-- no CRM, e vale acompanhamento: ver sql/run_rejeitados.py.
rejeitados AS (
    SELECT
        id_oportunidade, conta, pais_norm AS pais, status_norm, data_venda, mrr, classe,
        'duplicata' AS motivo_rejeicao
    FROM (
        SELECT
            *,
            ROW_NUMBER() OVER (
                PARTITION BY id_oportunidade, conta, data_venda
                ORDER BY (mrr IS NOT NULL)::INT + (pais_norm IS NOT NULL)::INT DESC
            ) AS rn
        FROM silver_classificado
    )
    WHERE rn > 1

    UNION ALL

    SELECT
        id_oportunidade, conta, pais_norm AS pais, status_norm, data_venda, mrr, classe,
        CASE
            WHEN status_norm = 'Ganho' THEN 'ganho_sem_data_fechamento'
            ELSE 'status_' || lower(status_norm)
        END AS motivo_rejeicao
    FROM silver_dedup
    WHERE NOT (status_norm = 'Ganho' AND data_venda IS NOT NULL)
)

-- Camada de consumo
SELECT
    strftime(data_venda, '%Y-%m') AS ano_mes,
    pais,
    classe                        AS tipo_venda,
    COUNT(*)                      AS qtd_vendas,
    SUM(mrr)                      AS mrr_total
FROM silver
WHERE classe IN ('nova_venda', 'reativacao')
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;
