output "job_names" { value = { for name, job in aws_glue_job.this : name => job.name } }
output "workflow_name" { value = aws_glue_workflow.this.name }
output "triggers" { value = { start_silver = aws_glue_trigger.start_silver.name } }
