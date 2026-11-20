"""POST /ingestions: valida um lote e responde 202 depois de enfileira-lo."""
import base64
import binascii
import json
import os
import re
import uuid

import boto3

sqs = boto3.client("sqs")
MAX_DECODED_BYTES = 180_000  # SQS aceita no maximo 256 KiB por mensagem.
KEY_PATTERN = re.compile(r"^(pedidos|pagamentos|eventos)/[A-Za-z0-9._/-]+$")


def response(status, body):
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def handler(event, _context):
    try:
        payload = json.loads(event.get("body") or "{}")
        event_id = payload.get("event_id") or str(uuid.uuid4())
        uuid.UUID(event_id)
        key = payload["key"]
        encoded = payload["content_base64"]
        if not isinstance(key, str) or not KEY_PATTERN.fullmatch(key):
            raise ValueError("key deve iniciar com pedidos/, pagamentos/ ou eventos/")
        raw = base64.b64decode(encoded, validate=True)
        if not raw or len(raw) > MAX_DECODED_BYTES:
            raise ValueError("content_base64 deve conter entre 1 e 180000 bytes")
    except (KeyError, ValueError, TypeError, binascii.Error, json.JSONDecodeError) as exc:
        return response(400, {"error": str(exc)})

    sqs.send_message(
        QueueUrl=os.environ["QUEUE_URL"],
        MessageBody=json.dumps({"event_id": event_id, "key": key, "content_base64": encoded}),
    )
    return response(202, {"event_id": event_id, "status": "queued", "key": key})
