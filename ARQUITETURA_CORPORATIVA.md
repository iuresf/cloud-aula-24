# Perfil corporativo

O Terraform entrega o fluxo operacional e marca os recursos com `Project`, `Environment`, `DataClassification`, `ManagedBy` e `Architecture`. Use um state remoto, conta AWS e `terraform.tfvars` distintos para cada ambiente (`dev`, `hml`, `prod`); nunca compartilhe state ou buckets entre eles.

## Controles implementados

- API autenticada por Cognito, SQS com DLQ e deduplicacao por `event_id` no DynamoDB.
- S3 com bloqueio publico e criptografia; Bronze possui versionamento.
- Metadados de classificacao, qualidade e linhagem no Glue Catalog.
- Alarmes para DLQ, erros das Lambdas e falhas dos jobs Glue, enviados ao SNS.
- Contratos de arquivos Bronze em `02_data_lake/scripts/validate_contracts.py` e CI em `.github/workflows/quality.yml`.
- Manifestos imutaveis por execucao: Bronze com chave, `VersionId`, SHA-256 e `event_id`; Silver com entradas Bronze/saidas Silver; Gold com entradas Silver, saidas Gold e particoes catalogadas. A consulta autenticada `GET /lineage` lista as evidencias.

## Obrigatorio antes de producao

1. Criar roles separadas para Terraform, Glue e Lambda, com menor privilegio. A `LabRole` existe apenas para o laboratorio.
2. Trocar SSE-S3 por chaves KMS por ambiente e conceder uso somente as roles de execucao. Guardar segredos em Secrets Manager e nunca em `terraform.tfvars` ou variaveis de ambiente de Lambda.
3. Implantar workloads em subnets privadas e criar VPC endpoints para S3, SQS, DynamoDB, Secrets Manager, Glue e CloudWatch. A configuracao depende do VPC, subnets e security groups corporativos e por isso nao e criada automaticamente.
4. Habilitar Lake Formation com administradores e grants por dominio de dados. Isso e uma configuracao global da conta e deve ser aplicada por equipe de plataforma, nunca pelo state deste laboratorio.
5. Migrar publicacoes Silver/Gold para tabelas Apache Iceberg, com particionamento e compactacao. O Parquet `overwrite` atual nao oferece ACID, snapshot ou `MERGE` transacional.
6. Definir SLOs, retencao, backup, teste de recuperacao e procedimento de reprocessamento para cada dominio.

Esses controles sao separados porque exigem decisoes de seguranca, rede, custo e propriedade de dados que nao podem ser inferidas pelo projeto didatico.
