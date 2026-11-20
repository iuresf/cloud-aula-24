terraform {
  required_version = ">= 1.5, < 2.0"
  required_providers {
    aws     = { source = "hashicorp/aws", version = "= 5.44.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.5" }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project            = var.project
      Environment        = var.environment
      DataClassification = var.data_classification
      ManagedBy          = "Terraform"
      Architecture       = "data-lake"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  database_name = replace(var.project, "-", "_")
  bucket_names = {
    for zone in ["bronze", "silver", "gold", "results"] :
    zone => "${var.project}-${zone}-${data.aws_caller_identity.current.account_id}-${var.region}"
  }
}

module "storage" {
  source             = "./modules/storage"
  bucket_names       = local.bucket_names
  region             = var.region
  manage_script_path = "${path.module}/scripts/manage_bucket.sh"
}

module "catalog" {
  source              = "./modules/catalog"
  database_name       = local.database_name
  bucket_names        = module.storage.bucket_names
  data_classification = var.data_classification
}

module "athena" {
  source         = "./modules/athena"
  project        = var.project
  results_bucket = module.storage.bucket_names["results"]

  depends_on = [module.storage]
}

module "etl" {
  source        = "./modules/etl"
  project       = var.project
  glue_role_arn = var.glue_role_arn
  account_id    = data.aws_caller_identity.current.account_id
  database_name = module.catalog.database_name
  bucket_names  = module.storage.bucket_names
  script_sources = {
    silver = "${path.module}/jobs/silver.py"
    gold   = "${path.module}/jobs/gold.py"
  }

  depends_on = [module.storage, module.catalog]
}

# Entrada de producao: API autenticada -> SQS/DLQ -> Lambda -> Bronze.
# A LabRole e reutilizada; este projeto nao cria roles ou politicas IAM.
module "ingress" {
  source                = "./modules/ingress"
  project               = var.project
  region                = var.region
  account_id            = data.aws_caller_identity.current.account_id
  execution_role_arn    = var.glue_role_arn
  bronze_bucket         = module.storage.bucket_names["bronze"]
  results_bucket        = module.storage.bucket_names["results"]
  workflow_name         = module.etl.workflow_name
  workflow_trigger_name = module.etl.triggers.start_silver
  database_name         = module.catalog.database_name
  workgroup_name        = module.athena.workgroup_name
  enable_cognito_auth   = var.enable_cognito_auth

  depends_on = [module.storage, module.catalog, module.athena, module.etl]
}

module "observability" {
  source       = "./modules/observability"
  project      = var.project
  alert_email  = var.alert_email
  job_names    = values(module.etl.job_names)
  queue_name   = module.ingress.queue_name
  dlq_name     = module.ingress.dlq_name
  lambda_names = module.ingress.lambda_names

  depends_on = [module.etl, module.ingress]
}

# Recriado quando a configuracao que alimenta o inventario ou seu renderizador muda.
resource "terraform_data" "render_resource_diagram" {
  triggers_replace = [
    filesha256("${path.module}/scripts/render_resources_png.py"),
    sha256(jsonencode({
      project   = var.project
      database  = module.catalog.database_name
      workgroup = module.athena.workgroup_name
      workflow  = module.etl.workflow_name
    })),
  ]

  input = {
    output_path = "${path.module}/diagramas/terraform-recursos.png"
    project     = var.project
    database    = module.catalog.database_name
    workgroup   = module.athena.workgroup_name
    workflow    = module.etl.workflow_name
  }

  depends_on = [module.storage, module.catalog, module.athena, module.etl, module.ingress, module.observability]

  provisioner "local-exec" {
    command = "python3 '${path.module}/scripts/render_resources_png.py' --output '${self.input.output_path}' --project '${self.input.project}' --database '${self.input.database}' --workgroup '${self.input.workgroup}' --workflow '${self.input.workflow}'"
  }
}

output "region" { value = var.region }
output "database" { value = module.catalog.database_name }
output "workgroup" { value = module.athena.workgroup_name }
output "buckets" { value = module.storage.bucket_names }
output "jobs" { value = module.etl.job_names }
output "workflow" { value = module.etl.workflow_name }
output "triggers" { value = module.etl.triggers }
output "resource_diagram" { value = "${path.module}/diagramas/terraform-recursos.png" }
output "ingestion_api_url" { value = module.ingress.ingestion_url }
output "results_api_url" { value = module.ingress.results_url }
output "lineage_api_url" { value = module.ingress.lineage_url }
output "cognito" { value = module.ingress.cognito }
output "queues" { value = module.ingress.queues }
output "alerts" { value = module.observability.alerts }
output "dashboard_url" { value = module.observability.dashboard_url }
