"""GET /lineage: expõe os manifestos imutáveis de rastreabilidade do pipeline."""
import json
import os

import boto3

s3 = boto3.client("s3")


def handler(_event, _context):
    manifests = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=os.environ["RESULTS_BUCKET"], Prefix="manifestos/"):
        for item in page.get("Contents", []):
            if item["Key"].endswith(".json"):
                manifests.append({
                    "key": item["Key"],
                    "size_bytes": item["Size"],
                    "last_modified": item["LastModified"].isoformat(),
                })
    manifests.sort(key=lambda item: item["key"])
    return {
        "statusCode": 200,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"manifests": manifests}, ensure_ascii=False),
    }
