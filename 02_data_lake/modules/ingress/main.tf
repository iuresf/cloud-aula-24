data "archive_file" "api_ingest" {
  type        = "zip"
  source_file = "${path.module}/files/api_ingest.py"
  output_path = "${path.module}/.build/api_ingest.zip"
}

data "archive_file" "queue_to_bronze" {
  type        = "zip"
  source_file = "${path.module}/files/queue_to_bronze.py"
  output_path = "${path.module}/.build/queue_to_bronze.zip"
}

data "archive_file" "results" {
  type        = "zip"
  source_file = "${path.module}/files/results.py"
  output_path = "${path.module}/.build/results.zip"
}

data "archive_file" "lineage" {
  type        = "zip"
  source_file = "${path.module}/files/lineage.py"
  output_path = "${path.module}/.build/lineage.zip"
}

resource "aws_sqs_queue" "dlq" {
  name                      = "${var.project}-ingest-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "ingest" {
  name                       = "${var.project}-ingest"
  visibility_timeout_seconds = 180
  receive_wait_time_seconds  = 20
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })
}

# Retencao de idempotencia por 30 dias. Uma reentrega SQS nao cria novo objeto Bronze.
resource "aws_dynamodb_table" "idempotency" {
  name         = "${var.project}-ingest-events"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "event_id"

  attribute {
    name = "event_id"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}

resource "aws_cloudwatch_log_group" "api_ingest" {
  name              = "/aws/lambda/${var.project}-api-ingest"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "queue_to_bronze" {
  name              = "/aws/lambda/${var.project}-queue-to-bronze"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "results" {
  name              = "/aws/lambda/${var.project}-results"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "lineage" {
  name              = "/aws/lambda/${var.project}-lineage"
  retention_in_days = 7
}

resource "aws_lambda_function" "api_ingest" {
  function_name    = "${var.project}-api-ingest"
  role             = var.execution_role_arn
  handler          = "api_ingest.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.api_ingest.output_path
  source_code_hash = data.archive_file.api_ingest.output_base64sha256
  timeout          = 15
  memory_size      = 256

  environment {
    variables = { QUEUE_URL = aws_sqs_queue.ingest.url }
  }

  depends_on = [aws_cloudwatch_log_group.api_ingest]

  lifecycle {
    precondition {
      condition     = can(regex("^arn:aws:iam::${var.account_id}:role/", var.execution_role_arn))
      error_message = "A role das Lambdas deve pertencer a mesma conta AWS do Terraform."
    }
  }
}

resource "aws_lambda_function" "queue_to_bronze" {
  function_name    = "${var.project}-queue-to-bronze"
  role             = var.execution_role_arn
  handler          = "queue_to_bronze.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.queue_to_bronze.output_path
  source_code_hash = data.archive_file.queue_to_bronze.output_base64sha256
  timeout          = 60
  memory_size      = 512

  environment {
    variables = {
      BRONZE_BUCKET         = var.bronze_bucket
      RESULTS_BUCKET        = var.results_bucket
      IDEMPOTENCY_TABLE     = aws_dynamodb_table.idempotency.name
      WORKFLOW_NAME         = var.workflow_name
      WORKFLOW_TRIGGER_NAME = var.workflow_trigger_name
      CODE_SHA256           = data.archive_file.queue_to_bronze.output_base64sha256
    }
  }

  depends_on = [aws_cloudwatch_log_group.queue_to_bronze]
}

resource "aws_lambda_function" "results" {
  function_name    = "${var.project}-results"
  role             = var.execution_role_arn
  handler          = "results.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.results.output_path
  source_code_hash = data.archive_file.results.output_base64sha256
  timeout          = 30
  memory_size      = 256

  environment {
    variables = {
      DATABASE       = var.database_name
      WORKGROUP      = var.workgroup_name
      RESULTS_BUCKET = var.results_bucket
    }
  }

  depends_on = [aws_cloudwatch_log_group.results]
}

resource "aws_lambda_function" "lineage" {
  function_name    = "${var.project}-lineage"
  role             = var.execution_role_arn
  handler          = "lineage.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.lineage.output_path
  source_code_hash = data.archive_file.lineage.output_base64sha256
  timeout          = 15
  memory_size      = 256

  environment {
    variables = { RESULTS_BUCKET = var.results_bucket }
  }

  depends_on = [aws_cloudwatch_log_group.lineage]
}

resource "aws_lambda_event_source_mapping" "queue" {
  event_source_arn                   = aws_sqs_queue.ingest.arn
  function_name                      = aws_lambda_function.queue_to_bronze.arn
  batch_size                         = 10
  maximum_batching_window_in_seconds = 30
  function_response_types            = ["ReportBatchItemFailures"]
}

resource "aws_cognito_user_pool" "this" {
  count = var.enable_cognito_auth ? 1 : 0
  name  = "${var.project}-api-users"

  auto_verified_attributes = ["email"]
  username_attributes      = ["email"]

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 7
  }
}

resource "aws_cognito_user_pool_client" "api" {
  count        = var.enable_cognito_auth ? 1 : 0
  name         = "${var.project}-api-client"
  user_pool_id = aws_cognito_user_pool.this[0].id

  generate_secret                      = false
  prevent_user_existence_errors        = "ENABLED"
  explicit_auth_flows                  = ["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
  allowed_oauth_flows_user_pool_client = false
}

resource "aws_apigatewayv2_api" "this" {
  name          = "${var.project}-ingestion-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_headers = ["authorization", "content-type"]
    allow_methods = ["GET", "OPTIONS", "POST"]
    allow_origins = ["*"]
  }
}

resource "aws_apigatewayv2_authorizer" "cognito" {
  count            = var.enable_cognito_auth ? 1 : 0
  api_id           = aws_apigatewayv2_api.this.id
  name             = "cognito-jwt"
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]

  jwt_configuration {
    audience = [aws_cognito_user_pool_client.api[0].id]
    issuer   = "https://cognito-idp.${var.region}.amazonaws.com/${aws_cognito_user_pool.this[0].id}"
  }
}

resource "aws_apigatewayv2_integration" "api_ingest" {
  api_id                 = aws_apigatewayv2_api.this.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api_ingest.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_integration" "results" {
  api_id                 = aws_apigatewayv2_api.this.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.results.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_integration" "lineage" {
  api_id                 = aws_apigatewayv2_api.this.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.lineage.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "ingestions" {
  api_id             = aws_apigatewayv2_api.this.id
  route_key          = "POST /ingestions"
  target             = "integrations/${aws_apigatewayv2_integration.api_ingest.id}"
  authorization_type = var.enable_cognito_auth ? "JWT" : "NONE"
  authorizer_id      = var.enable_cognito_auth ? aws_apigatewayv2_authorizer.cognito[0].id : null
}

resource "aws_apigatewayv2_route" "results" {
  api_id             = aws_apigatewayv2_api.this.id
  route_key          = "GET /results"
  target             = "integrations/${aws_apigatewayv2_integration.results.id}"
  authorization_type = var.enable_cognito_auth ? "JWT" : "NONE"
  authorizer_id      = var.enable_cognito_auth ? aws_apigatewayv2_authorizer.cognito[0].id : null
}

resource "aws_apigatewayv2_route" "lineage" {
  api_id             = aws_apigatewayv2_api.this.id
  route_key          = "GET /lineage"
  target             = "integrations/${aws_apigatewayv2_integration.lineage.id}"
  authorization_type = var.enable_cognito_auth ? "JWT" : "NONE"
  authorizer_id      = var.enable_cognito_auth ? aws_apigatewayv2_authorizer.cognito[0].id : null
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.this.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "api_ingest" {
  statement_id  = "AllowApiGatewayInvokeIngest"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api_ingest.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.this.execution_arn}/*/*"
}

resource "aws_lambda_permission" "results" {
  statement_id  = "AllowApiGatewayInvokeResults"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.results.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.this.execution_arn}/*/*"
}

resource "aws_lambda_permission" "lineage" {
  statement_id  = "AllowApiGatewayInvokeLineage"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.lineage.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.this.execution_arn}/*/*"
}
