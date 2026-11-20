# 02_data_lake

Leia primeiro o README.md na raiz desta aula. Do diretório raiz do pacote:

```bash
cd 02_data_lake
cp terraform.tfvars.example terraform.tfvars
# Edite os valores do exemplo antes do plan.
terraform init
terraform fmt -check
terraform validate
terraform plan -out=aula24.tfplan
terraform apply aula24.tfplan
terraform output
cd ..
python runner.py initial
python runner.py delta
```

Para a separacao de responsabilidades e os controles necessarios antes de producao, leia [ARQUITETURA_CORPORATIVA.md](../ARQUITETURA_CORPORATIVA.md). Execute `python scripts/validate_contracts.py` antes do deploy para validar o contrato dos lotes Bronze.

Ao fim de cada `terraform apply`, o projeto atualiza o diagrama PNG dos recursos em `diagramas/terraform-recursos.png`. O mesmo caminho tambem aparece no output `resource_diagram` do Terraform. O arquivo e local, nao e enviado a AWS nem versionado pelo Git.

No console Athena, escolha o workgroup e o database do output. Rode os arquivos de sql/ um statement por vez.
A primeira execução deve apresentar receita R$129,90. Após delta, R$0,00. No lake/lakehouse também confira 2 sessões, 1 cancelado e conversão 50% para 0%.
O projeto não cria usuários, roles ou políticas IAM. Reutiliza permissões aprovadas na conta. Não implanta recursos durante a geração deste material.

## Arquitetura de producao simplificada

Sem substituir o Glue Workflow, o Terraform agora inclui a camada de entrada e operacao:

- **Cognito** emite o JWT usado pelo **API Gateway HTTP**;
- `POST /ingestions` chama uma Lambda que valida o lote e responde `202 Accepted` apos enfileira-lo no **SQS**;
- outra Lambda le ate dez mensagens, impede reentregas pelo `event_id` no **DynamoDB**, grava o arquivo imutavel na Bronze e inicia o trigger do Glue quando o workflow nao esta em execucao;
- tres falhas de consumo encaminham a mensagem para a **DLQ**;
- eventos de falha dos jobs Silver/Gold seguem por **EventBridge** para um topico **SNS**; e
- `GET /results` executa a consulta de indicadores no Athena e devolve as linhas JSON para um painel ou cliente.

O fluxo didatico pelo `runner.py` permanece disponivel para carregar fixtures sem precisar autenticar na API. A camada de API suporta lotes pequenos (ate 180 KB decodificados por mensagem); para arquivos grandes, use URL pre-assinada ou outro mecanismo de upload direto ao S3 em uma evolucao posterior.

Depois do apply, consulte:

```bash
terraform output ingestion_api_url
terraform output results_api_url
terraform output lineage_api_url
terraform output queues
terraform output alerts
terraform output dashboard_url
```

Se `enable_cognito_auth = true`, a chamada deve conter `Authorization: Bearer <JWT>`. Para um teste controlado no AWS Academy, pode-se definir temporariamente `enable_cognito_auth = false`; nao use essa opcao fora do laboratorio.

## Particularidades do Data Lake

Neste projeto: quatro buckets (Bronze, Silver, Gold, resultados), dois jobs Spark, Glue Catalog e um Glue Workflow. Ingestão didática por upload do terminal substitui as origens reais ERP/API/Web. DMS e Firehose são opções de ingestão, não necessários neste conjunto estático.
O trigger `ON_DEMAND` inicia Silver quando o `runner.py` chama o Workflow. O trigger condicional inicia Gold somente se Silver terminar em `SUCCEEDED`; em falha, a Gold anterior continua publicada e o runner encerra com erro.

## Estrutura Terraform

O arquivo raiz apenas conecta os módulos e expõe os outputs usados pelo `runner.py`:

- `modules/storage`: cria e remove as zonas S3 pelo script compatível com o SCP do AWS Academy;
- `modules/catalog`: banco e tabelas externas do Glue Data Catalog;
- `modules/etl`: scripts, jobs, Workflow e triggers Glue;
- `modules/athena`: workgroup e destino dos resultados SQL.
Silver lê CSV e JSONL da Bronze, converte datas e moeda, valida, deduplica e seleciona a versão mais recente de pagamento. Gold agrega vendas, sessões e conversões separadamente e só depois combina os resultados.
O Terraform declara schemas explícitos. Não usa crawler. Um crawler pode descobrir o schema, mas não transforma nem deduplica os dados. A Bronze é particionada fisicamente por data de ingestão, por exemplo `pedidos/ingestion_date=2026-11-19/api_lote_001.csv`; isso preserva o dado bruto e facilita retenção, auditoria e reprocessamento por lote de chegada. Silver usa leitura recursiva para consumir essas subpastas e continua sem partição física de saída: `Window.partitionBy('pedido_id')` é somente uma janela de deduplicação do Spark.

A tabela Gold `indicadores` é particionada fisicamente por data de negócio, em caminhos como `s3://<bucket-gold>/indicadores/data=2026-10-21/`. Assim, `ingestion_date` responde quando o arquivo chegou à Bronze, enquanto `data` responde a qual dia do negócio o indicador pertence.

## Rastreabilidade por manifestos

Cada publicação gera manifestos JSON imutáveis no bucket de resultados. Eles permitem seguir o dado de ponta a ponta, sem depender de logs transitórios:

- `manifestos/bronze/event_id=<UUID>.json`: origem API, chave original, objeto Bronze particionado, `VersionId`, ETag, tamanho, SHA-256 e hash da Lambda;
- `manifestos/silver/workflow_run_id=<ID>/manifest.json`: `WorkflowRunId`, `JobRunId`, hash do job, objetos Bronze e seus manifestos de origem, além dos Parquet Silver publicados; e
- `manifestos/gold/workflow_run_id=<ID>/manifest.json`: referência ao manifesto Silver, objetos Silver lidos, arquivos Gold, datas publicadas e localizações registradas no Glue Catalog.

No painel/cliente autenticado, consulte `GET /lineage` (output `lineage_api_url`) para listar os manifestos. Para ver o conteúdo de um deles, abra no S3 o bucket `results`, na chave devolvida pela API. No console, os mesmos artefatos estão em **S3 > bucket results > manifestos/**. O `event_id` recebido no `POST /ingestions` é a chave de correlação da entrada até a Bronze; o `workflow_run_id` correlaciona Silver e Gold.

Após gravar a Gold, o próprio job registra cada `data` no Glue Catalog com `ALTER TABLE ... ADD IF NOT EXISTS PARTITION` e remove do catálogo datas que não foram mais geradas. Portanto não é necessário executar `MSCK REPAIR TABLE`. Para uma consulta econômica no Athena, sempre filtre a data:

```sql
SELECT data, canal, receita, pagos, cancelados, sessoes, conversao
FROM indicadores
WHERE data = '2026-10-21';
```

Nesta versão didática Gold é reconstruída por completo em cada execução. Em uma evolução incremental, remova e recalcule apenas as partições de datas afetadas (inclusive por estornos tardios) e mantenha o catálogo sincronizado.
Ao executar delta, o lake relê os eventos originais e reconstrói Silver/Gold. Não se deve apenas acrescentar uma linha estornada e somar todos os arquivos anteriores.

## Falhas comuns

AccessDenied: confirme identidade temporária, iam:PassRole, acesso às zonas S3, Glue Catalog, logs e grants Lake Formation se habilitado. Para a camada de entrada, a LabRole tambem precisa permitir Lambda, SQS, DynamoDB, API Gateway, CloudWatch Logs, Athena e `glue:StartTrigger`. Não tente contornar políticas do Academy.
Tabela vazia: termine os jobs e confira o LOCATION no Glue.
Tabela não encontrada: confira região, catálogo, database e conclusão do primeiro job.
Spark falhou: abra CloudWatch com o JobRunId salvo. Erro de contrato deve ser corrigido na origem, preservando o bruto para auditoria.
Resultado antigo: aguarde Gold, execute uma consulta nova e confirme P1042 no estado atual.

## Critério de aceite

Compare o resultado inicial e após delta. Reenvie `delta` e confirme o mesmo total (idempotência do estado). Salve query IDs e JobRunIds, diagrama e justificativa da arquitetura.
Ao finalizar, rode `python runner.py cleanup` e `terraform destroy` na pasta deste projeto. Revise antes o plano de destruição.
