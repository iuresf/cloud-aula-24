SELECT data,canal,receita,pagos,cancelados,sessoes,ROUND(100*conversao,1) AS conversao_pct FROM indicadores ORDER BY data,canal;
