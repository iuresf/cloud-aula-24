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

# Contrato explicito: campos invalidos interrompem a publicacao.
raw = spark.read.option('header', True).option('sep',';').schema(
    'id STRING, dia STRING, valor STRING, status STRING, canal STRING'
).csv(f"s3://{args['BRONZE']}/pedidos/")
pedidos = raw.select(
    F.trim('id').alias('pedido_id'), F.to_date('dia','dd/MM/yyyy').alias('data'),
    F.regexp_replace('valor',',','.').cast('decimal(12,2)').alias('valor'),
    F.lower(F.trim('status')).alias('status'), F.lower(F.trim('canal')).alias('canal')
).dropDuplicates()
assert pedidos.filter('pedido_id IS NULL OR data IS NULL OR valor IS NULL OR valor < 0').count() == 0, 'Pedido invalido'
assert pedidos.filter("status NOT IN ('pago','cancelado') OR canal IS NULL").count() == 0, 'Status/canal invalido'
assert pedidos.groupBy('pedido_id').count().filter('count > 1').count() == 0, 'Conflito de pedido: contrato sem versao'
pagamentos = spark.read.schema('pedido_id STRING, resultado STRING, atualizado_em STRING').json(
    f"s3://{args['BRONZE']}/pagamentos/"
).withColumn('atualizado_em',F.to_timestamp('atualizado_em'))
assert pagamentos.filter("pedido_id IS NULL OR atualizado_em IS NULL OR resultado IS NULL OR resultado NOT IN ('aprovado','sem_cobranca','estornado')").count() == 0, 'Pagamento invalido'
assert pagamentos.groupBy('pedido_id','atualizado_em').agg(F.countDistinct('resultado').alias('n')).filter('n > 1').count() == 0, 'Versoes empatadas e conflitantes'
w = Window.partitionBy('pedido_id').orderBy(F.col('atualizado_em').desc())
pagamentos = pagamentos.withColumn('rn',F.row_number().over(w)).filter('rn = 1').drop('rn')
eventos = spark.read.schema('evento_id STRING, sessao STRING, evento STRING, pedido_id STRING, dia STRING, canal STRING').json(
    f"s3://{args['BRONZE']}/eventos/"
).withColumn('data',F.to_date('dia')).drop('dia').dropDuplicates()
assert eventos.filter('evento_id IS NULL OR sessao IS NULL OR data IS NULL OR canal IS NULL').count() == 0, 'Evento invalido'
assert eventos.groupBy('evento_id').count().filter('count > 1').count() == 0, 'Evento conflitante'
eventos = eventos.select('evento_id','sessao','evento','pedido_id','data','canal')
datasets = {'pedidos':pedidos,'pagamentos':pagamentos,'eventos':eventos}

for name,df in datasets.items():
    df.coalesce(1).write.mode('overwrite').parquet(f"s3://{args['SILVER']}/{name}/")
# O Glue injeta WORKFLOW_RUN_ID quando o job e iniciado pelo Workflow. O dado
# continua sendo opcional para manter o job executavel manualmente no console.
workflow_run_id = next((sys.argv[i + 1] for i, v in enumerate(sys.argv[:-1]) if v == '--WORKFLOW_RUN_ID'), None)
spark.createDataFrame([(workflow_run_id or 'manual', 'silver', len(datasets))],
                      'workflow_run_id string, etapa string, datasets bigint') \
     .coalesce(1).write.mode('overwrite').json(f"s3://{args['RESULTS']}/manifestos/silver-ultima-execucao/")
# Overwrite de arquivos nao e transacao de tabela. Execute sem leitores concorrentes.
job.commit()
