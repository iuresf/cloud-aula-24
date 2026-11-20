resource "aws_athena_workgroup" "this" {
  name          = var.project
  force_destroy = true

  configuration {
    enforce_workgroup_configuration = true
    bytes_scanned_cutoff_per_query  = 104857600

    engine_version {
      selected_engine_version = "Athena engine version 3"
    }

    result_configuration {
      output_location = "s3://${var.results_bucket}/athena/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}
