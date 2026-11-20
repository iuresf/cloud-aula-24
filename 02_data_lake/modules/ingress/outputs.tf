output "ingestion_url" { value = "${trimsuffix(aws_apigatewayv2_stage.default.invoke_url, "/")}/ingestions" }
output "results_url" { value = "${trimsuffix(aws_apigatewayv2_stage.default.invoke_url, "/")}/results" }
output "lineage_url" { value = "${trimsuffix(aws_apigatewayv2_stage.default.invoke_url, "/")}/lineage" }
output "queue_name" { value = aws_sqs_queue.ingest.name }
output "dlq_name" { value = aws_sqs_queue.dlq.name }
output "lambda_names" {
  value = [
    aws_lambda_function.api_ingest.function_name,
    aws_lambda_function.queue_to_bronze.function_name,
    aws_lambda_function.results.function_name,
    aws_lambda_function.lineage.function_name,
  ]
}
output "queues" {
  value = {
    ingestion_url = aws_sqs_queue.ingest.url
    dlq_url       = aws_sqs_queue.dlq.url
  }
}
output "cognito" {
  value = var.enable_cognito_auth ? {
    user_pool_id = aws_cognito_user_pool.this[0].id
    client_id    = aws_cognito_user_pool_client.api[0].id
  } : null
}
