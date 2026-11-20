import sys
import json
from datetime import datetime, timezone
import boto3
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
s3 = boto3.client('s3')


def runtime_arg(name, default='manual'):
    option = f'--{name}'
    return next((sys.argv[i + 1] for i, value in enumerate(sys.argv[:-1]) if value == option), default)


def object_references(bucket, prefix, suffix=None):
    references = []
    paginator = s3.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get('Contents', []):
            if suffix and not item['Key'].endswith(suffix):
                continue
            head = s3.head_object(Bucket=bucket, Key=item['Key'])
            references.append({
                'uri': f"s3://{bucket}/{item['Key']}",
                'key': item['Key'],
                'version_id': head.get('VersionId'),
                'etag': head['ETag'].strip('"'),
                'size_bytes': head['ContentLength'],
                'sha256': head.get('Metadata', {}).get('content-sha256'),
            })
    return sorted(references, key=lambda item: item['key'])

# Contrato explicito: campos invalidos interrompem a publicacao.
raw = spark.read.option('header', True).option('sep',';').schema(
    'id STRING, dia STRING, valor STRING, status STRING, canal STRING'
).option('recursiveFileLookup', 'true').csv(f"s3://{args['BRONZE']}/pedidos/")
pedidos = raw.select(
    F.trim('id').alias('pedido_id'), F.to_date('dia','dd/MM/yyyy').alias('data'),
    F.regexp_replace('valor',',','.').cast('decimal(12,2)').alias('valor'),
    F.lower(F.trim('status')).alias('status'), F.lower(F.trim('canal')).alias('canal')
).dropDuplicates()
assert pedidos.filter('pedido_id IS NULL OR data IS NULL OR valor IS NULL OR valor < 0').count() == 0, 'Pedido invalido'
assert pedidos.filter("status NOT IN ('pago','cancelado') OR canal IS NULL").count() == 0, 'Status/canal invalido'
assert pedidos.groupBy('pedido_id').count().filter('count > 1').count() == 0, 'Conflito de pedido: contrato sem versao'
pagamentos = spark.read.schema('pedido_id STRING, resultado STRING, atualizado_em STRING') \
    .option('recursiveFileLookup', 'true').json(f"s3://{args['BRONZE']}/pagamentos/") \
    .withColumn('atualizado_em',F.to_timestamp('atualizado_em'))
assert pagamentos.filter("pedido_id IS NULL OR atualizado_em IS NULL OR resultado IS NULL OR resultado NOT IN ('aprovado','sem_cobranca','estornado')").count() == 0, 'Pagamento invalido'
assert pagamentos.groupBy('pedido_id','atualizado_em').agg(F.countDistinct('resultado').alias('n')).filter('n > 1').count() == 0, 'Versoes empatadas e conflitantes'
w = Window.partitionBy('pedido_id').orderBy(F.col('atualizado_em').desc())
pagamentos = pagamentos.withColumn('rn',F.row_number().over(w)).filter('rn = 1').drop('rn')
eventos = spark.read.schema('evento_id STRING, sessao STRING, evento STRING, pedido_id STRING, dia STRING, canal STRING') \
    .option('recursiveFileLookup', 'true').json(f"s3://{args['BRONZE']}/eventos/") \
    .withColumn('data',F.to_date('dia')).drop('dia').dropDuplicates()
assert eventos.filter('evento_id IS NULL OR sessao IS NULL OR data IS NULL OR canal IS NULL').count() == 0, 'Evento invalido'
assert eventos.groupBy('evento_id').count().filter('count > 1').count() == 0, 'Evento conflitante'
eventos = eventos.select('evento_id','sessao','evento','pedido_id','data','canal')
datasets = {'pedidos':pedidos,'pagamentos':pagamentos,'eventos':eventos}

for name,df in datasets.items():
    df.coalesce(1).write.mode('overwrite').parquet(f"s3://{args['SILVER']}/{name}/")

# Manifesto imutável: liga os objetos Bronze consumidos aos Parquet Silver
# produzidos, e aponta aos manifestos por objeto criados na entrada API.
workflow_run_id = runtime_arg('WORKFLOW_RUN_ID')
job_run_id = runtime_arg('JOB_RUN_ID')
bronze_inputs = {
    name: object_references(args['BRONZE'], f'{name}/')
    for name in datasets
}
silver_outputs = {
    name: object_references(args['SILVER'], f'{name}/', '.parquet')
    for name in datasets
}
bronze_manifests = [
    ref['uri'] for ref in object_references(args['RESULTS'], 'manifestos/bronze/', '.json')
]
manifest = {
    'schema_version': '1.0',
    'layer': 'silver',
    'recorded_at': datetime.now(timezone.utc).isoformat(),
    'workflow_run_id': workflow_run_id,
    'job_run_id': job_run_id,
    'producer': {'job_name': args['JOB_NAME'], 'code_sha256': runtime_arg('SCRIPT_SHA256', None)},
    'inputs': {'bronze_objects': bronze_inputs, 'bronze_manifests': bronze_manifests},
    'outputs': {'silver_objects': silver_outputs},
}
s3.put_object(
    Bucket=args['RESULTS'],
    Key=f'manifestos/silver/workflow_run_id={workflow_run_id}/manifest.json',
    Body=json.dumps(manifest, ensure_ascii=False, default=str).encode('utf-8'),
    ContentType='application/json',
)
# Overwrite de arquivos nao e transacao de tabela. Execute sem leitores concorrentes.
job.commit()
