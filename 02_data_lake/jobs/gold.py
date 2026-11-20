import sys
import copy
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
            })
    return sorted(references, key=lambda item: item['key'])
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
# A partição é física no S3 (data=YYYY-MM-DD) e lógica no Glue Catalog.
# A execução didática reconstrói toda a Gold; por isso overwrite é seguro aqui.
partition_values = [str(row['data']) for row in indicadores.select('data').distinct().collect()]
gold_location = f"s3://{args['GOLD']}/indicadores/"
indicadores.coalesce(1).write.mode('overwrite').partitionBy('data').parquet(gold_location)

# Gravar Parquet não cria partições no Data Catalog. O Spark de Glue deste
# laboratório não expõe a tabela externa no seu catalogo de sessão, portanto
# usamos a API Glue nativa para sincronizar os metadados de forma explícita.
glue = boto3.client('glue')
table = glue.get_table(DatabaseName=db, Name='indicadores')['Table']
catalog_partitions = []
paginator = glue.get_paginator('get_partitions')
for page in paginator.paginate(DatabaseName=db, TableName='indicadores'):
    catalog_partitions.extend(partition['Values'][0] for partition in page['Partitions'])

stale_partitions = sorted(set(catalog_partitions) - set(partition_values))
for index in range(0, len(stale_partitions), 25):
    glue.batch_delete_partition(
        DatabaseName=db,
        TableName='indicadores',
        PartitionsToDelete=[{'Values': [value]} for value in stale_partitions[index:index + 25]],
    )

storage_descriptor = copy.deepcopy(table['StorageDescriptor'])
partition_inputs = []
for partition_data in sorted(set(partition_values) - set(catalog_partitions)):
    partition_descriptor = copy.deepcopy(storage_descriptor)
    partition_descriptor['Location'] = f"{gold_location}data={partition_data}/"
    partition_inputs.append({
        'Values': [partition_data],
        'StorageDescriptor': partition_descriptor,
    })
for index in range(0, len(partition_inputs), 100):
    response = glue.batch_create_partition(
        DatabaseName=db,
        TableName='indicadores',
        PartitionInputList=partition_inputs[index:index + 100],
    )
    if response.get('Errors'):
        raise RuntimeError(f"Falha ao registrar partições Gold: {response['Errors']}")
workflow_run_id = runtime_arg('WORKFLOW_RUN_ID')
job_run_id = runtime_arg('JOB_RUN_ID')
silver_manifest_uri = f"s3://{args['RESULTS']}/manifestos/silver/workflow_run_id={workflow_run_id}/manifest.json"
manifest = {
    'schema_version': '1.0',
    'layer': 'gold',
    'recorded_at': datetime.now(timezone.utc).isoformat(),
    'workflow_run_id': workflow_run_id,
    'job_run_id': job_run_id,
    'producer': {'job_name': args['JOB_NAME'], 'code_sha256': runtime_arg('SCRIPT_SHA256', None)},
    'inputs': {
        'silver_manifest': silver_manifest_uri,
        'silver_objects': {
            name: object_references(args['SILVER'], f'{name}/', '.parquet')
            for name in ('pedidos', 'pagamentos', 'eventos')
        },
    },
    'outputs': {
        'gold_objects': object_references(args['GOLD'], 'indicadores/', '.parquet'),
        'catalog_partitions': [{'data': value, 'location': f'{gold_location}data={value}/'} for value in sorted(partition_values)],
    },
}
s3.put_object(
    Bucket=args['RESULTS'],
    Key=f'manifestos/gold/workflow_run_id={workflow_run_id}/manifest.json',
    Body=json.dumps(manifest, ensure_ascii=False, default=str).encode('utf-8'),
    ContentType='application/json',
)
job.commit()
