terraform {
  required_version = ">= 1.5, < 2.0"
  required_providers {
    # O provider 6 consulta Object Lock ao ler buckets; o SCP do AWS Academy
    # nega essa API. A linha 5.x e compativel com os recursos deste laboratorio.
    aws = { source = "hashicorp/aws", version = "= 5.44.0" }
  }
}
provider "aws" { region = var.region }
variable "region" {
  type    = string
  default = "us-east-1"
}
variable "project" {
  type    = string
  default = "a24-lake"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,25}$", var.project))
    error_message = "Use 3 a 26 caracteres minusculos, numeros ou hifen."
  }
}
data "aws_caller_identity" "current" {}
locals { db = replace(var.project, "-", "_") }
locals {
  bucket_names = {
    for zone in ["bronze", "silver", "gold", "results"] :
    zone => "${var.project}-${zone}-${data.aws_caller_identity.current.account_id}-${var.region}"
  }
}

# A SCP do AWS Academy nega s3:GetBucketObjectLockConfiguration. O resource
# aws_s3_bucket sempre le essa configuracao; estes comandos evitam a leitura
# negada e ainda tornam o apply/destroy idempotente para este laboratorio.
resource "terraform_data" "zones" {
  for_each = local.bucket_names
  input = {
    bucket      = each.value
    region      = var.region
    script_path = "${path.module}/scripts/manage_bucket.sh"
  }

  provisioner "local-exec" {
    command = "bash ${self.input.script_path} create ${self.input.bucket} ${self.input.region}"
  }
  provisioner "local-exec" {
    when    = destroy
    command = "bash ${self.input.script_path} destroy ${self.input.bucket} ${self.input.region}"
  }
}
resource "aws_glue_catalog_database" "db" { name = local.db }
resource "aws_athena_workgroup" "lab" {
  name          = var.project
  force_destroy = true
  depends_on    = [terraform_data.zones]
  configuration {
    enforce_workgroup_configuration = true
    bytes_scanned_cutoff_per_query  = 104857600
    engine_version { selected_engine_version = "Athena engine version 3" }
    result_configuration {
      output_location = "s3://${local.bucket_names["results"]}/athena/"
      encryption_configuration { encryption_option = "SSE_S3" }
    }
  }
}
output "region" { value = var.region }
output "database" { value = aws_glue_catalog_database.db.name }
output "workgroup" { value = aws_athena_workgroup.lab.name }
output "buckets" { value = local.bucket_names }

variable "glue_role_arn" {
  type        = string
  description = "ARN exato de role existente autorizada ao Glue. Nao cria IAM."
  validation {
    condition     = can(regex("^arn:aws:iam::[0-9]{12}:role/", var.glue_role_arn))
    error_message = "Informe o ARN de uma role existente, por exemplo a LabRole, se autorizada."
  }
}
resource "aws_s3_object" "scripts" {
  for_each   = toset(["silver.py", "gold.py"])
  depends_on = [terraform_data.zones]
  bucket     = local.bucket_names["results"]
  key        = "scripts/${each.value}"
  source     = "${path.module}/jobs/${each.value}"
  etag       = filemd5("${path.module}/jobs/${each.value}")
}
resource "aws_glue_job" "etl" {
  for_each          = toset(["silver", "gold"])
  name              = "${var.project}-${each.key}"
  role_arn          = var.glue_role_arn
  glue_version      = "5.0"
  worker_type       = "G.1X"
  number_of_workers = 2
  timeout           = 10
  max_retries       = 0
  execution_property { max_concurrent_runs = 1 }
  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_object.scripts["${each.key}.py"].bucket}/${aws_s3_object.scripts["${each.key}.py"].key}"
    python_version  = "3"
  }
  default_arguments = {
    "--job-language"                     = "python"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--BRONZE"                           = local.bucket_names["bronze"]
    "--SILVER"                           = local.bucket_names["silver"]
    "--GOLD"                             = local.bucket_names["gold"]
    "--RESULTS"                          = local.bucket_names["results"]
    "--DATABASE"                         = aws_glue_catalog_database.db.name

  }
}
output "jobs" { value = { for k, v in aws_glue_job.etl : k => v.name } }

# O Workflow e seus triggers fazem a orquestracao: Gold so inicia depois do
# sucesso de Silver. Nenhuma role ou politica IAM e criada pelo projeto.
resource "aws_glue_workflow" "etl" {
  name = "${var.project}-workflow"
  default_run_properties = {
    project = var.project
    modelo  = "bronze-silver-gold"
  }
}

resource "aws_glue_trigger" "start_silver" {
  name          = "${var.project}-start-silver"
  type          = "ON_DEMAND"
  workflow_name = aws_glue_workflow.etl.name

  actions {
    job_name = aws_glue_job.etl["silver"].name
  }
}

resource "aws_glue_trigger" "silver_succeeded_starts_gold" {
  name          = "${var.project}-silver-succeeded-gold"
  type          = "CONDITIONAL"
  workflow_name = aws_glue_workflow.etl.name

  predicate {
    conditions {
      job_name         = aws_glue_job.etl["silver"].name
      state            = "SUCCEEDED"
      logical_operator = "EQUALS"
    }
  }

  actions {
    job_name = aws_glue_job.etl["gold"].name
  }
}

output "workflow" { value = aws_glue_workflow.etl.name }
output "triggers" {
  value = {
    start_silver = aws_glue_trigger.start_silver.name
  }
}

resource "aws_glue_catalog_table" "pedidos" {
  name          = "pedidos"
  database_name = aws_glue_catalog_database.db.name
  table_type    = "EXTERNAL_TABLE"
  parameters    = { EXTERNAL = "TRUE", classification = "parquet" }
  storage_descriptor {
    location      = "s3://${local.bucket_names["silver"]}/pedidos/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"
    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters            = { "field.delim" = ",", "serialization.format" = "," }
    }
    columns {
      name = "pedido_id"
      type = "string"
    }
    columns {
      name = "data"
      type = "date"
    }
    columns {
      name = "valor"
      type = "decimal(12,2)"
    }
    columns {
      name = "status"
      type = "string"
    }
    columns {
      name = "canal"
      type = "string"
    }
  }
}

resource "aws_glue_catalog_table" "pagamentos" {
  name          = "pagamentos"
  database_name = aws_glue_catalog_database.db.name
  table_type    = "EXTERNAL_TABLE"
  parameters    = { EXTERNAL = "TRUE", classification = "parquet" }
  storage_descriptor {
    location      = "s3://${local.bucket_names["silver"]}/pagamentos/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"
    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters            = { "field.delim" = ",", "serialization.format" = "," }
    }
    columns {
      name = "pedido_id"
      type = "string"
    }
    columns {
      name = "resultado"
      type = "string"
    }
    columns {
      name = "atualizado_em"
      type = "timestamp"
    }
  }
}

resource "aws_glue_catalog_table" "eventos" {
  name          = "eventos"
  database_name = aws_glue_catalog_database.db.name
  table_type    = "EXTERNAL_TABLE"
  parameters    = { EXTERNAL = "TRUE", classification = "parquet" }
  storage_descriptor {
    location      = "s3://${local.bucket_names["silver"]}/eventos/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"
    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters            = { "field.delim" = ",", "serialization.format" = "," }
    }
    columns {
      name = "evento_id"
      type = "string"
    }
    columns {
      name = "sessao"
      type = "string"
    }
    columns {
      name = "evento"
      type = "string"
    }
    columns {
      name = "pedido_id"
      type = "string"
    }
    columns {
      name = "data"
      type = "date"
    }
    columns {
      name = "canal"
      type = "string"
    }
  }
}

resource "aws_glue_catalog_table" "indicadores" {
  name          = "indicadores"
  database_name = aws_glue_catalog_database.db.name
  table_type    = "EXTERNAL_TABLE"
  parameters    = { EXTERNAL = "TRUE", classification = "parquet" }
  storage_descriptor {
    location      = "s3://${local.bucket_names["gold"]}/indicadores/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"
    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters            = { "field.delim" = ",", "serialization.format" = "," }
    }
    columns {
      name = "data"
      type = "date"
    }
    columns {
      name = "canal"
      type = "string"
    }
    columns {
      name = "receita"
      type = "decimal(14,2)"
    }
    columns {
      name = "pagos"
      type = "bigint"
    }
    columns {
      name = "cancelados"
      type = "bigint"
    }
    columns {
      name = "sessoes"
      type = "bigint"
    }
    columns {
      name = "conversao"
      type = "double"
    }
  }
}
