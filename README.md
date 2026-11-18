# Aula 24 — Data Lake no AWS S3 / Glue Workflow / Athena

**Projeto independente:** apenas o código e os dados desta aula. Não depende dos projetos das aulas 23 e 26.

## Preparação e execução

1. Configure AWS CLI e credenciais temporárias, e confirme a conta com `aws sts get-caller-identity`.
2. Instale Python >=3.10, Terraform >=1.5 e `python -m pip install -r requirements.txt`. No AWS Academy, use o provider AWS 5.44.0 fixado pelo lockfile: versões posteriores podem tentar ler Object Lock, API bloqueada pela SCP do laboratório.
3. Inicie o Learner Lab e configure `terraform.tfvars` com o ARN da `LabRole`; sem criar novas roles ou políticas IAM.
4. Execute a partir da raiz desta aula:

```bash
cd 02_data_lake
cp terraform.tfvars.example terraform.tfvars
# Configure o ARN real da role e a região
terraform init
terraform fmt -check
terraform validate
terraform plan -out=aula24.tfplan
terraform apply aula24.tfplan
terraform output
cd ..
python runner.py initial
python runner.py verify
python runner.py delta
python runner.py verify
# Data Lake: consultar indicadores no Athena
```

Os arquivos `dados/inicial/` são carregados para o S3 Bronze; o delta posterior atualiza o resultado do pagamento. O runner inicia o Glue Workflow sob demanda: Silver roda primeiro e o trigger condicional só dispara Gold quando Silver termina em `SUCCEEDED`. Evidências da execução são gravadas em `02_data_lake/evidencias/`.

## Recursos e limitações

- Terraform cria recursos próprios com prefixo `a24-lake`, quatro buckets separados e um Glue Workflow.
- O projeto não faz streaming/CDC e precisa de envio manual pelo runner.
- O Silver/Gold é reprocessado em Parquet por sobrescrita, sem versionamento transacional das tabelas.
- Verifique IAM, Glue, S3, Athena, Lake Formation e custos; o código não garante elegibilidade no AWS Academy.
- O job usa a `LabRole` existente como role de execução do Glue. A identidade temporária do Learner Lab também precisa de `iam:PassRole` sobre ela.
- Consulte `02_data_lake/README.md` para o roteiro detalhado.

## Encerramento

```bash
python runner.py cleanup
cd 02_data_lake
terraform plan -destroy
terraform destroy
```

O S3 usa `force_destroy=true`, exclusivamente para este laboratório isolado.
