resource "aws_glue_catalog_database" "this" {
  name = var.database_name
  parameters = {
    "data.classification" = var.data_classification
    "data.owner"          = "data-platform"
    "retention.policy"    = "defined-by-environment"
  }
}

locals {
  parquet_format = {
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"
    serde         = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
  }

  tables = {
    pedidos = {
      zone = "silver"
      columns = [
        { name = "pedido_id", type = "string" },
        { name = "data", type = "date" },
        { name = "valor", type = "decimal(12,2)" },
        { name = "status", type = "string" },
        { name = "canal", type = "string" },
      ]
    }
    pagamentos = {
      zone = "silver"
      columns = [
        { name = "pedido_id", type = "string" },
        { name = "resultado", type = "string" },
        { name = "atualizado_em", type = "timestamp" },
      ]
    }
    eventos = {
      zone = "silver"
      columns = [
        { name = "evento_id", type = "string" },
        { name = "sessao", type = "string" },
        { name = "evento", type = "string" },
        { name = "pedido_id", type = "string" },
        { name = "data", type = "date" },
        { name = "canal", type = "string" },
      ]
    }
    indicadores = {
      zone = "gold"
      columns = [
        { name = "canal", type = "string" },
        { name = "receita", type = "decimal(14,2)" },
        { name = "pagos", type = "bigint" },
        { name = "cancelados", type = "bigint" },
        { name = "sessoes", type = "bigint" },
        { name = "conversao", type = "double" },
      ]
      # A coluna de partição pertence ao catálogo, não ao schema Parquet.
      # O job Gold grava objetos em indicadores/data=YYYY-MM-DD/.
      partition_keys = [
        { name = "data", type = "string" },
      ]
    }
  }
}

resource "aws_glue_catalog_table" "this" {
  for_each      = local.tables
  name          = each.key
  database_name = aws_glue_catalog_database.this.name
  table_type    = "EXTERNAL_TABLE"
  parameters = {
    EXTERNAL              = "TRUE"
    classification        = "parquet"
    "data.classification" = var.data_classification
    "quality.contract"    = "enforced-by-glue-job"
    "lineage.manifest"    = "s3-results/manifestos"
  }

  storage_descriptor {
    location      = "s3://${var.bucket_names[each.value.zone]}/${each.key}/"
    input_format  = local.parquet_format.input_format
    output_format = local.parquet_format.output_format

    ser_de_info {
      serialization_library = local.parquet_format.serde
      parameters            = { "field.delim" = ",", "serialization.format" = "," }
    }

    dynamic "columns" {
      for_each = each.value.columns
      content {
        name = columns.value.name
        type = columns.value.type
      }
    }
  }

  dynamic "partition_keys" {
    for_each = try(each.value.partition_keys, [])
    content {
      name = partition_keys.value.name
      type = partition_keys.value.type
    }
  }
}
