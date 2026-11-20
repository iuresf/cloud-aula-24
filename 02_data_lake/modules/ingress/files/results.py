"""GET /results: executa a consulta Gold e devolve a ultima visao analitica."""
import json
import os
import time

import boto3

athena = boto3.client("athena")
SQL = """
SELECT data, canal, receita, pagos, cancelados, sessoes,
       ROUND(100 * conversao, 1) AS conversao_pct
FROM indicadores
ORDER BY data, canal
"""


def handler(_event, _context):
    execution_id = athena.start_query_execution(
        QueryString=SQL,
        QueryExecutionContext={"Database": os.environ["DATABASE"]},
        WorkGroup=os.environ["WORKGROUP"],
    )["QueryExecutionId"]
    for _ in range(12):
        result = athena.get_query_execution(QueryExecutionId=execution_id)["QueryExecution"]
        state = result["Status"]["State"]
        if state == "SUCCEEDED":
            rows = athena.get_query_results(QueryExecutionId=execution_id)["ResultSet"]["Rows"]
            values = [[column.get("VarCharValue") for column in row["Data"]] for row in rows]
            return {"statusCode": 200, "headers": {"content-type": "application/json"}, "body": json.dumps({"query_execution_id": execution_id, "rows": values})}
        if state in {"FAILED", "CANCELLED"}:
            return {"statusCode": 500, "headers": {"content-type": "application/json"}, "body": json.dumps({"query_execution_id": execution_id, "error": result["Status"].get("StateChangeReason", state)})}
        time.sleep(2)
    return {"statusCode": 202, "headers": {"content-type": "application/json"}, "body": json.dumps({"query_execution_id": execution_id, "status": "running"})}
