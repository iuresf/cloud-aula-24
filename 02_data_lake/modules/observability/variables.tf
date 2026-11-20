variable "project" { type = string }
variable "alert_email" { type = string }
variable "job_names" { type = list(string) }
variable "queue_name" { type = string }
variable "dlq_name" { type = string }
variable "lambda_names" { type = list(string) }
