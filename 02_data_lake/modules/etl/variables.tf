variable "project" { type = string }
variable "glue_role_arn" { type = string }
variable "account_id" { type = string }
variable "database_name" { type = string }
variable "bucket_names" { type = map(string) }

variable "script_sources" {
  type        = map(string)
  description = "Mapa etapa -> caminho local do script Glue."

  validation {
    condition     = contains(keys(var.script_sources), "silver") && contains(keys(var.script_sources), "gold")
    error_message = "Os scripts silver e gold sao obrigatorios."
  }
}
