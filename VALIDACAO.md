# Validação — Aula 24

Validação executada no AWS Academy em 17/11/2026, conta `795636653176`, região `us-east-1`, usando `LabRole`.

- `terraform validate` e `python3 -m py_compile` concluídos com sucesso.
- Deploy concluído: buckets, catálogo/tabelas, workgroup Athena, jobs Silver/Gold e Glue Workflow com trigger `ON_DEMAND` e trigger condicional Silver `SUCCEEDED` → Gold.
- Carga inicial validada no Athena: receita `129.90`, pagos `1`, cancelados `1`, sessões `2`, conversão `50.0%`.
- Delta validado no Athena: receita `0.00`, pagos `0`, cancelados `1`, sessões `2`, conversão `0.0%`.
- Workflow do delta `wr_14249c01e4495f9fbdaa717b2bab18bf569900fb66b7ece69afa249d0188675f` terminou em `COMPLETED`; Silver e Gold terminaram em `SUCCEEDED`.
- Manifestos Bronze, Silver e Gold foram gravados em `results/manifestos/`.

O ambiente será removido após esta validação com `terraform plan -destroy` revisado e `terraform apply` do plano de destruição.
