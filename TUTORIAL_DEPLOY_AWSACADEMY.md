# Tutorial — deploy da Aula 24 no AWS Academy

Este projeto usa S3, Glue Data Catalog, dois jobs Glue, um Glue Workflow e Athena. A `LabRole` existente e usada pelos jobs; o projeto nao cria role nem politica IAM.

## 1. Inicie o laboratorio e confirme a identidade

No AWS Academy, clique em **Start Lab**, espere o indicador verde e abra o terminal com as credenciais temporarias. Na raiz do projeto, confirme conta e regiao:

```bash
aws sts get-caller-identity
aws iam get-role --role-name LabRole --query 'Role.Arn' --output text
```

Se o segundo comando falhar, use o ARN de outra role **ja existente**, que confie em `glue.amazonaws.com` e tenha permissao para S3, Glue, CloudWatch Logs e Glue Catalog. A identidade temporaria do Lab tambem precisa de `iam:PassRole` para a role escolhida.

## 2. Prepare as ferramentas e a configuracao

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp 02_data_lake/terraform.tfvars.example.txt 02_data_lake/terraform.tfvars
```

Edite `02_data_lake/terraform.tfvars`; mantenha uma regiao disponivel no Lab e substitua a conta do exemplo pelo ARN retornado no passo anterior:

```hcl
region        = "us-east-1"
project       = "a24-lake"
glue_role_arn = "arn:aws:iam::SUA_CONTA:role/LabRole"
```

O nome do projeto precisa ser exclusivo na conta. Se ja houver recursos de teste, use por exemplo `a24-lake-seunome` (respeitando 26 caracteres no maximo).

## 3. Validar e implantar

```bash
cd 02_data_lake
terraform init
terraform fmt -check
terraform validate
terraform plan -out=aula24.tfplan
terraform apply aula24.tfplan
terraform output
cd ..
```

O apply cria quatro buckets, catalogo e tabelas Glue, workgroup Athena, jobs `silver` e `gold`, e o Workflow com dois triggers: `ON_DEMAND` para Silver e condicional (`Silver = SUCCEEDED`) para Gold.

No AWS Academy, a SCP pode bloquear `s3:GetBucketObjectLockConfiguration`. Por isso os buckets deste projeto sao criados pelo script AWS CLI chamado pelo Terraform; ele aplica bloqueio de acesso publico, SSE-S3 e versionamento na Bronze sem chamar a API bloqueada. Nao troque esse mecanismo por `aws_s3_bucket` sem antes testar a politica da conta.

## 4. Carregar e validar

```bash
.venv/bin/python runner.py initial
.venv/bin/python runner.py verify
.venv/bin/python runner.py delta
.venv/bin/python runner.py verify
```

`initial` envia CSV/JSONL a Bronze, registra hash SHA-256 e VersionId no manifesto e inicia o trigger do Workflow. O runner aguarda o fim do Workflow. `delta` envia o estorno, reprocessa Silver e Gold e preserva os objetos anteriores da Bronze.

Resultados esperados no `verify`:

| Carga | Receita | Pagos | Cancelados | Sessoes | Conversao |
| --- | ---: | ---: | ---: | ---: | ---: |
| initial | 129.90 | 1 | 1 | 2 | 50.0% |
| delta | 0.00 | 0 | 1 | 2 | 0.0% |

## 4.1 Acompanhar cada envio pelo painel AWS

Use sempre a mesma regiao definida em `terraform.tfvars` (normalmente `us-east-1`). A sequencia abaixo vale tanto para `initial` quanto para `delta`.

1. **Workflow e ordem Silver → Gold:** abra **AWS Glue** → **ETL** → **Workflows** → `a24-lake-workflow`. Na coluna *Last run status*, acompanhe `RUNNING`, `COMPLETED` ou `ERROR`. Selecione o workflow, abra **History**, escolha a execucao mais recente e clique em **View run details**. O grafo deve mostrar Silver concluindo antes de Gold iniciar.

2. **Detalhes dos jobs:** no Glue, abra **ETL jobs** → **Job run monitoring**. Filtre por `a24-lake-silver` ou `a24-lake-gold`. O status esperado e `SUCCEEDED`. Selecione a execucao e clique em **View run details** para ver horario, consumo e o *Job run ID*. Em falha, use **View CloudWatch logs** para abrir os logs do Spark.

3. **Arquivos recebidos e saidas:** abra **Amazon S3** e procure os buckets exibidos por `terraform output`. Na Bronze, confira `pedidos/`, `pagamentos/` e `eventos/`; apos o delta, havera tambem `pagamentos/lote_002.jsonl`. No bucket Results, abra `manifestos/bronze/` para os arquivos de rastreabilidade e `manifestos/silver-ultima-execucao/` e `manifestos/gold-ultima-execucao/` para o registro das etapas. As saidas Parquet ficam nos buckets Silver e Gold.

4. **Resultado analitico:** abra **Amazon Athena** → **Query editor**. No seletor superior direito, escolha o workgroup `a24-lake`; em *Database*, selecione `a24_lake`. Execute:

```sql
SELECT data, canal, receita, pagos, cancelados, sessoes,
       ROUND(100 * conversao, 1) AS conversao_pct
FROM indicadores
ORDER BY data, canal;
```

O resultado aparece no painel inferior. Antes do delta, espere receita `129.90` e conversao `50.0`; depois do delta, `0.00` e `0.0`. Em **Recent queries**, voce pode abrir o *Query execution ID* de cada consulta, verificar se terminou em `SUCCEEDED` e baixar o CSV se necessario.

Para inspeção adicional, use os nomes retornados por `terraform output`:

```bash
aws glue get-workflow-runs --region us-east-1 --name a24-lake-workflow --max-results 5
aws s3 ls "s3://$(terraform -chdir=02_data_lake output -json buckets | jq -r .results)/manifestos/" --recursive
```

## 5. Encerrar e evitar custos

Somente depois que não houver jobs Glue em execução:

```bash
cd 02_data_lake
terraform plan -destroy -out=destroy.tfplan
terraform show -no-color destroy.tfplan
terraform apply destroy.tfplan
```

O destroy remove triggers, jobs, Workflow, tabelas, workgroup e os quatro buckets. O script do projeto esvazia também versões e delete markers da Bronze; confirme o plano antes de aplicar. Por fim, encerre o Learner Lab.
