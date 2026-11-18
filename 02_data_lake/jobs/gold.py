import sys
from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.context import SparkContext
from pyspark.sql import functions as F, Window
args = getResolvedOptions(sys.argv, ['JOB_NAME','BRONZE','SILVER','GOLD','RESULTS','DATABASE'])
ctx = GlueContext(SparkContext.getOrCreate())
spark = ctx.spark_session
spark.conf.set('spark.sql.session.timeZone', 'UTC')
spark.conf.set('spark.sql.ansi.enabled', 'true')
job = Job(ctx)
job.init(args['JOB_NAME'], args)
db = args['DATABASE']
pedidos = spark.read.parquet(f"s3://{args['SILVER']}/pedidos/")
pagamentos = spark.read.parquet(f"s3://{args['SILVER']}/pagamentos/")
eventos = spark.read.parquet(f"s3://{args['SILVER']}/eventos/")

pedidos.createOrReplaceTempView('p')
pagamentos.createOrReplaceTempView('pg')
eventos.createOrReplaceTempView('e')
# Agregar vendas e sessoes separadamente evita multiplicacao pelo JOIN de eventos.
indicadores = spark.sql("""
WITH vendas AS (
 SELECT p.data, p.canal,
   CAST(SUM(CASE WHEN p.status='pago' AND pg.resultado='aprovado'
       THEN p.valor ELSE 0 END) AS DECIMAL(14,2)) AS receita,
   CAST(SUM(CASE WHEN p.status='pago' AND pg.resultado='aprovado' THEN 1 ELSE 0 END) AS BIGINT) AS pagos,
   CAST(SUM(CASE WHEN p.status='cancelado' THEN 1 ELSE 0 END) AS BIGINT) AS cancelados
 FROM p LEFT JOIN pg ON p.pedido_id=pg.pedido_id GROUP BY p.data,p.canal
), visitas AS (
 SELECT data,canal,COUNT(DISTINCT sessao) AS sessoes FROM e GROUP BY data,canal
), convertidas AS (
 SELECT e.data,e.canal,COUNT(DISTINCT e.sessao) AS compras
 FROM e JOIN p ON e.pedido_id=p.pedido_id JOIN pg ON p.pedido_id=pg.pedido_id
 WHERE e.evento='checkout' AND p.status='pago' AND pg.resultado='aprovado'
 GROUP BY e.data,e.canal
), chaves AS (
 SELECT data,canal FROM vendas UNION SELECT data,canal FROM visitas
)
SELECT k.data,k.canal,COALESCE(v.receita,CAST(0 AS DECIMAL(14,2))) AS receita,
 COALESCE(v.pagos,CAST(0 AS BIGINT)) AS pagos,COALESCE(v.cancelados,CAST(0 AS BIGINT)) AS cancelados,
 COALESCE(s.sessoes,CAST(0 AS BIGINT)) AS sessoes,
 CASE WHEN s.sessoes > 0 THEN CAST(COALESCE(c.compras,0) AS DOUBLE)/s.sessoes ELSE NULL END AS conversao
FROM chaves k LEFT JOIN vendas v ON k.data=v.data AND k.canal=v.canal
LEFT JOIN visitas s ON k.data=s.data AND k.canal=s.canal
LEFT JOIN convertidas c ON k.data=c.data AND k.canal=c.canal
""")
indicadores.coalesce(1).write.mode('overwrite').parquet(f"s3://{args['GOLD']}/indicadores/")
workflow_run_id = next((sys.argv[i + 1] for i, v in enumerate(sys.argv[:-1]) if v == '--WORKFLOW_RUN_ID'), None)
spark.createDataFrame([(workflow_run_id or 'manual', 'gold')],
                      'workflow_run_id string, etapa string') \
     .coalesce(1).write.mode('overwrite').json(f"s3://{args['RESULTS']}/manifestos/gold-ultima-execucao/")
job.commit()
