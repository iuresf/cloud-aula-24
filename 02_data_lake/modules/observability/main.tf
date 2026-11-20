resource "aws_sns_topic" "workflow_failures" {
  name = "${var.project}-workflow-failures"
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alert_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.workflow_failures.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_cloudwatch_event_rule" "glue_job_failure" {
  name        = "${var.project}-glue-job-failure"
  description = "Notifica falhas dos jobs Silver e Gold do Glue Workflow"
  event_pattern = jsonencode({
    source        = ["aws.glue"]
    "detail-type" = ["Glue Job Run Status"]
    detail = {
      jobName = var.job_names
      state   = ["FAILED", "STOPPED", "TIMEOUT", "ERROR"]
    }
  })
}

resource "aws_cloudwatch_event_target" "sns" {
  rule = aws_cloudwatch_event_rule.glue_job_failure.name
  arn  = aws_sns_topic.workflow_failures.arn
}

data "aws_iam_policy_document" "allow_eventbridge" {
  statement {
    sid       = "AllowEventBridgePublish"
    effect    = "Allow"
    actions   = ["SNS:Publish"]
    resources = [aws_sns_topic.workflow_failures.arn]

    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }

    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_cloudwatch_event_rule.glue_job_failure.arn]
    }
  }
}

resource "aws_sns_topic_policy" "allow_eventbridge" {
  arn    = aws_sns_topic.workflow_failures.arn
  policy = data.aws_iam_policy_document.allow_eventbridge.json
}

# A DLQ representa falha persistente da Lambda consumidora depois de tres tentativas.
resource "aws_cloudwatch_metric_alarm" "dlq_messages" {
  alarm_name          = "${var.project}-ingest-dlq-not-empty"
  alarm_description   = "Ha mensagens que exigem analise na DLQ de ingestao"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = var.dlq_name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.workflow_failures.arn]
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each            = toset(var.lambda_names)
  alarm_name          = "${each.value}-errors"
  alarm_description   = "Erros da Lambda; investigar logs e DLQ quando aplicavel"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = each.value }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.workflow_failures.arn]
}

resource "aws_cloudwatch_dashboard" "pipeline" {
  dashboard_name = "${var.project}-pipeline"
  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Fila de ingestao e DLQ"
          view   = "timeSeries"
          region = "${data.aws_region.current.name}"
          stat   = "Sum"
          period = 300
          metrics = [
            ["AWS/SQS", "NumberOfMessagesSent", "QueueName", var.queue_name],
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", var.queue_name],
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", var.dlq_name]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "Falhas dos jobs Glue"
          view    = "timeSeries"
          region  = "${data.aws_region.current.name}"
          stat    = "Sum"
          period  = 300
          metrics = [for job in var.job_names : ["Glue", "glue.driver.aggregate.numFailedTasks", "JobName", job]]
        }
      }
    ]
  })
}

data "aws_region" "current" {}
