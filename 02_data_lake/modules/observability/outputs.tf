output "alerts" {
  value = {
    sns_topic_arn      = aws_sns_topic.workflow_failures.arn
    email_subscription = var.alert_email == "" ? "nao configurada" : "confirme o e-mail enviado pelo SNS"
    eventbridge_rule   = aws_cloudwatch_event_rule.glue_job_failure.name
    dlq_alarm          = aws_cloudwatch_metric_alarm.dlq_messages.alarm_name
  }
}
output "dashboard_url" {
  value = "https://${data.aws_region.current.name}.console.aws.amazon.com/cloudwatch/home?region=${data.aws_region.current.name}#dashboards:name=${aws_cloudwatch_dashboard.pipeline.dashboard_name}"
}
