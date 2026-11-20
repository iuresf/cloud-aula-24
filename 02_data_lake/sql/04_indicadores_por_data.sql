-- Troque a data por uma partição existente no Glue Catalog.
-- O filtro em data permite ao Athena ler somente data=YYYY-MM-DD/.
SELECT data, canal, receita, pagos, cancelados, sessoes,
       ROUND(100 * conversao, 1) AS conversao_pct
FROM indicadores
WHERE data = '2026-10-21'
ORDER BY canal;
