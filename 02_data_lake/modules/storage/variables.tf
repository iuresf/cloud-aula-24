variable "bucket_names" {
  type        = map(string)
  description = "Nomes das zonas Bronze, Silver, Gold e Results."
}

variable "region" {
  type = string
}

variable "manage_script_path" {
  type        = string
  description = "Caminho absoluto ou relativo para o script de gerenciamento S3."
}
