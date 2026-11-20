"""Consome SQS, grava Bronze de modo idempotente e inicia o Glue Workflow."""
import base64
import hashlib
import json
import os
import time
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

s3 = boto3.client("s3")
ddb = boto3.client("dynamodb")
glue = boto3.client("glue")


def already_processed(event_id):
    try:
        ddb.put_item(
            TableName=os.environ["IDEMPOTENCY_TABLE"],
            Item={
                "event_id": {"S": event_id},
                "expires_at": {"N": str(int(time.time()) + 30 * 24 * 3600)},
            },
            ConditionExpression="attribute_not_exists(event_id)",
        )
        return False
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return True
        raise


def workflow_is_running():
    runs = glue.get_workflow_runs(Name=os.environ["WORKFLOW_NAME"], MaxResults=10).get("Runs", [])
    return any(run.get("Status") in {"RUNNING", "STOPPING"} for run in runs)


def handler(event, _context):
    failures = []
    accepted = 0
    for record in event.get("Records", []):
        try:
            message = json.loads(record["body"])
            event_id, key = message["event_id"], message["key"]
            if already_processed(event_id):
                continue
            body = base64.b64decode(message["content_base64"], validate=True)
            dataset, object_name = key.split("/", 1)
            ingestion_date = datetime.now(timezone.utc).date().isoformat()
            partitioned_key = f"{dataset}/ingestion_date={ingestion_date}/{object_name}"
            content_sha256 = hashlib.sha256(body).hexdigest()
            put_result = s3.put_object(
                Bucket=os.environ["BRONZE_BUCKET"],
                Key=partitioned_key,
                Body=body,
                Metadata={
                    "event-id": event_id,
                    "ingestion": "api-sqs",
                    "ingestion-date": ingestion_date,
                    "content-sha256": content_sha256,
                },
            )
            manifest = {
                "schema_version": "1.0",
                "layer": "bronze",
                "event_id": event_id,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "source": {"type": "api-gateway", "key": key},
                "output": {
                    "bucket": os.environ["BRONZE_BUCKET"],
                    "key": partitioned_key,
                    "uri": f"s3://{os.environ['BRONZE_BUCKET']}/{partitioned_key}",
                    "version_id": put_result.get("VersionId"),
                    "etag": put_result.get("ETag", "").strip('"'),
                    "size_bytes": len(body),
                    "sha256": content_sha256,
                    "partition": {"ingestion_date": ingestion_date},
                },
                "producer": {"component": "queue-to-bronze", "code_sha256": os.environ["CODE_SHA256"]},
            }
            s3.put_object(
                Bucket=os.environ["RESULTS_BUCKET"],
                Key=f"manifestos/bronze/event_id={event_id}.json",
                Body=json.dumps(manifest, ensure_ascii=False).encode("utf-8"),
                ContentType="application/json",
            )
            accepted += 1
        except Exception:
            failures.append({"itemIdentifier": record["messageId"]})

    # Uma invocacao consome ate dez eventos ou aguarda 30 s. Se o Workflow ja
    # estiver ativo, os objetos permanecem imutaveis na Bronze para a proxima rodada.
    if accepted and not workflow_is_running():
        glue.start_trigger(Name=os.environ["WORKFLOW_TRIGGER_NAME"])
    return {"batchItemFailures": failures}
