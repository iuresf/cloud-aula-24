"""Executor Aula 24: upload S3 -> Glue Workflow (Silver, Gold) -> Athena."""
import argparse
import hashlib
import json
import subprocess
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import boto3

PROJECT = "02_data_lake"
ROOT = Path(__file__).resolve().parent
DIR = ROOT / PROJECT
ap = argparse.ArgumentParser(description="Ingestao e validacao da aula 24")
ap.add_argument('action', choices=['initial', 'delta', 'verify', 'cleanup'])
a = ap.parse_args()
o = {k:v['value'] for k,v in json.loads(subprocess.check_output(['terraform','output','-json'],cwd=DIR)).items()}
session = boto3.Session(region_name=o['region'])
s3,glue,athena = session.client('s3'),session.client('glue'),session.client('athena')
run_id = str(uuid.uuid4())
ev = DIR/'evidencias'; ev.mkdir(exist_ok=True)

def record(kind,payload):
    (ev/f'{run_id}-{kind}.json').write_text(json.dumps(payload,default=str,ensure_ascii=False,indent=2))

def upload(stage):
    base = ROOT/'dados'/stage
    manifest = []
    for f in sorted(base.rglob('*')):
        if not f.is_file(): continue
        key = f.relative_to(base).as_posix()
        content = f.read_bytes()
        r = s3.put_object(Bucket=o['buckets']['bronze'],Key=key,Body=content)
        manifest.append({'key':key,'version_id':r.get('VersionId'),'sha256':hashlib.sha256(content).hexdigest()})
    if not manifest: raise ValueError('Nenhum arquivo em '+str(base))
    key = f'manifestos/bronze/{run_id}.json'
    s3.put_object(Bucket=o['buckets']['results'],Key=key,Body=json.dumps(manifest).encode())
    record('manifesto', {'key': key, 'objetos': manifest})
    return key

def query(statement):
    q = athena.start_query_execution(QueryString=statement,QueryExecutionContext={'Database':o['database']},WorkGroup=o['workgroup'])['QueryExecutionId']
    deadline = time.monotonic()+600
    while time.monotonic()<deadline:
        r=athena.get_query_execution(QueryExecutionId=q)['QueryExecution']
        state=r['Status']['State']
        if state=='SUCCEEDED':
            rows=[];token=None
            while True:
                opts={'QueryExecutionId':q}
                if token: opts['NextToken']=token
                page=athena.get_query_results(**opts)
                rows.extend(page['ResultSet']['Rows']);token=page.get('NextToken')
                if not token: break
            result=[[c.get('VarCharValue') for c in row['Data']] for row in rows]
            record('athena-'+q,{'sql':statement,'rows':result,'statistics':r.get('Statistics')})
            return result
        if state in ('FAILED','CANCELLED'):raise RuntimeError(r['Status'])
        time.sleep(2)
    athena.stop_query_execution(QueryExecutionId=q)
    raise TimeoutError(q)

def workflow(manifest_key):
    name=o['workflow']
    started_after = datetime.now(timezone.utc)
    # ON_DEMAND e o ponto de entrada do Workflow. StartWorkflowRun sozinho
    # cria uma execucao sem esta acao inicial em algumas contas do Glue.
    glue.start_trigger(Name=o['triggers']['start_silver'])
    run = None
    discovery_deadline = time.monotonic()+60
    while time.monotonic() < discovery_deadline:
        runs = glue.get_workflow_runs(Name=name, MaxResults=10)['Runs']
        candidates = [r for r in runs if r['StartedOn'].astimezone(timezone.utc) >= started_after]
        if candidates:
            run = max(candidates, key=lambda r: r['StartedOn'])['WorkflowRunId']
            break
        time.sleep(2)
    if not run:
        raise TimeoutError(f'Workflow {name} nao iniciou apos o trigger ON_DEMAND')
    # A correlacao dinamica fica registrada junto ao manifesto e nas evidencias.
    # Propriedades padrao do Terraform ficam disponiveis a todos os jobs do Workflow.
    record('workflow-iniciado', {'workflow': name, 'workflow_run_id': run, 'bronze_manifesto': manifest_key})
    deadline=time.monotonic()+900
    while time.monotonic()<deadline:
        r=glue.get_workflow_run(Name=name,RunId=run,IncludeGraph=True)['Run']
        state=r['Status']
        if state=='COMPLETED':
            record('workflow-concluido',r)
            return run
        if state in ('ERROR','STOPPED'):
            record('workflow-falhou',r)
            raise RuntimeError(r.get('ErrorMessage',state))
        time.sleep(10)
    raise TimeoutError(f'Workflow {name}/{run}')

def verify():
    rows=query((DIR/'sql/02_indicadores.sql').read_text())
    assert query('SELECT COUNT(*) AS n FROM pedidos')[1][0]=='2'
    assert len(query('SELECT pedido_id FROM pedidos GROUP BY pedido_id HAVING COUNT(*)>1'))==1
    assert len(rows)==2,'Esperado um grupo de indicadores no conjunto didatico'
    receita=Decimal(rows[1][2]); assert receita in (Decimal('129.90'),Decimal('0.00'))
    assert rows[1][4]=='1' and rows[1][5]=='2'
    assert Decimal(rows[1][6])==(Decimal('50.0') if receita>0 else Decimal('0.0'))
    print(json.dumps(rows,ensure_ascii=False,indent=2));return receita

if a.action in ('initial','delta'):
    manifest_key = upload('inicial' if a.action=='initial' else 'delta')
    workflow(manifest_key)
    receita=verify()
    expected=Decimal('129.90' if a.action=='initial' else '0.00')
    assert receita==expected,f'Esperado {expected}, encontrado {receita}. Initial requer ambiente sem delta.'
elif a.action=='verify':
    verify()

elif a.action=='cleanup':
    # O Terraform gerencia todas as tabelas declaradas deste Data Lake.
    print('Revise terraform plan -destroy e execute terraform destroy dentro de '+PROJECT)
