variable "region" {
  type    = string
  default = "us-east-1"
}

variable "environment" {
  type        = string
  default     = "lab"
  description = "Ambiente isolado. Em empresa, use dev, hml ou prod com state/backend separados."

  validation {
    condition     = contains(["lab", "dev", "hml", "prod"], var.environment)
    error_message = "environment deve ser lab, dev, hml ou prod."
  }
}

variable "data_classification" {
  type        = string
  default     = "internal"
  description = "Classificacao aplicada como tag e metadado do Glue Catalog."
}

variable "project" {
  type    = string
  default = "a24-lake"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,25}$", var.project))
    error_message = "Use 3 a 26 caracteres minusculos, numeros ou hifen."
  }
}

variable "glue_role_arn" {
  type        = string
  description = "ARN exato de role existente autorizada ao Glue. Nao cria IAM."

  validation {
    condition     = can(regex("^arn:aws:iam::[0-9]{12}:role/", var.glue_role_arn))
    error_message = "Informe o ARN de uma role existente, por exemplo a LabRole, se autorizada."
  }
}

variable "enable_cognito_auth" {
  type        = bool
  default     = true
  description = "Protege a API HTTP com JWT do Cognito. Desative somente para diagnostico temporario no Lab."
}

variable "alert_email" {
  type        = string
  default     = ""
  description = "E-mail que recebera falhas dos jobs Glue. Vazio cria o topico SNS sem inscricao."

  validation {
    condition     = var.alert_email == "" || can(regex("^[^@[:space:]]+@[^@[:space:]]+\\.[^@[:space:]]+$", var.alert_email))
    error_message = "Informe um e-mail valido ou deixe alert_email vazio."
  }
}
