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

No console Athena, escolha o workgroup e o database do output. Rode os arquivos de sql/ um statement por vez.
A primeira execução deve apresentar receita R$129,90. Após delta, R$0,00. No lake/lakehouse também confira 2 sessões, 1 cancelado e conversão 50% para 0%.
O projeto não cria usuários, roles ou políticas IAM. Reutiliza permissões aprovadas na conta. Não implanta recursos durante a geração deste material.

## Particularidades do Data Lake

Neste projeto: quatro buckets (Bronze, Silver, Gold, resultados), dois jobs Spark, Glue Catalog e um Glue Workflow. Ingestão didática por upload do terminal substitui as origens reais ERP/API/Web. DMS e Firehose são opções de ingestão, não necessários neste conjunto estático.
O trigger `ON_DEMAND` inicia Silver quando o `runner.py` chama o Workflow. O trigger condicional inicia Gold somente se Silver terminar em `SUCCEEDED`; em falha, a Gold anterior continua publicada e o runner encerra com erro.
Silver lê CSV e JSONL da Bronze, converte datas e moeda, valida, deduplica e seleciona a versão mais recente de pagamento. Gold agrega vendas, sessões e conversões separadamente e só depois combina os resultados.
O Terraform declara schemas explícitos. Não usa crawler. Um crawler pode descobrir o schema, mas não transforma nem deduplica os dados. Como as saídas não são particionadas, MSCK REPAIR TABLE não é necessário.
Ao executar delta, o lake relê os eventos originais e reconstrói Silver/Gold. Não se deve apenas acrescentar uma linha estornada e somar todos os arquivos anteriores.

## Falhas comuns

AccessDenied: confirme identidade temporária, iam:PassRole, acesso às zonas S3, Glue Catalog, logs e grants Lake Formation se habilitado. Não tente contornar políticas do Academy.
Tabela vazia: termine os jobs e confira o LOCATION no Glue.
Tabela não encontrada: confira região, catálogo, database e conclusão do primeiro job.
Spark falhou: abra CloudWatch com o JobRunId salvo. Erro de contrato deve ser corrigido na origem, preservando o bruto para auditoria.
Resultado antigo: aguarde Gold, execute uma consulta nova e confirme P1042 no estado atual.

## Critério de aceite

Compare o resultado inicial e após delta. Reenvie `delta` e confirme o mesmo total (idempotência do estado). Salve query IDs e JobRunIds, diagrama e justificativa da arquitetura.
Ao finalizar, rode `python runner.py cleanup` e `terraform destroy` na pasta deste projeto. Revise antes o plano de destruição.
