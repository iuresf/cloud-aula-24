resource "aws_s3_object" "scripts" {
  for_each = var.script_sources
  bucket   = var.bucket_names["results"]
  key      = "scripts/${each.key}.py"
  source   = each.value
  etag     = filemd5(each.value)
}

resource "aws_glue_job" "this" {
  for_each          = var.script_sources
  name              = "${var.project}-${each.key}"
  role_arn          = var.glue_role_arn
  glue_version      = "5.0"
  worker_type       = "G.1X"
  number_of_workers = 2
  timeout           = 10
  max_retries       = 0

  lifecycle {
    precondition {
      condition     = can(regex("^arn:aws:iam::${var.account_id}:role/", var.glue_role_arn))
      error_message = "glue_role_arn deve ser uma role da mesma conta AWS que executa o Terraform. Use a LabRole desta conta."
    }
  }

  execution_property {
    max_concurrent_runs = 1
  }

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_object.scripts[each.key].bucket}/${aws_s3_object.scripts[each.key].key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--BRONZE"                           = var.bucket_names["bronze"]
    "--SILVER"                           = var.bucket_names["silver"]
    "--GOLD"                             = var.bucket_names["gold"]
    "--RESULTS"                          = var.bucket_names["results"]
    "--DATABASE"                         = var.database_name
    "--SCRIPT_SHA256"                    = filesha256(each.value)
  }
}

resource "aws_glue_workflow" "this" {
  name = "${var.project}-workflow"

  default_run_properties = {
    project = var.project
    modelo  = "bronze-silver-gold"
  }
}

resource "aws_glue_trigger" "start_silver" {
  name          = "${var.project}-start-silver"
  type          = "ON_DEMAND"
  workflow_name = aws_glue_workflow.this.name

  actions {
    job_name = aws_glue_job.this["silver"].name
  }
}

resource "aws_glue_trigger" "silver_succeeded_starts_gold" {
  name          = "${var.project}-silver-succeeded-gold"
  type          = "CONDITIONAL"
  workflow_name = aws_glue_workflow.this.name

  predicate {
    conditions {
      job_name         = aws_glue_job.this["silver"].name
      state            = "SUCCEEDED"
      logical_operator = "EQUALS"
    }
  }

  actions {
    job_name = aws_glue_job.this["gold"].name
  }
}
