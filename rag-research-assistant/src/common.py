"""Shared AWS clients and helpers for all Lambda handlers."""
import json
import os
import re
import time
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from botocore.config import Config

REGION = os.environ.get("AWS_REGION", "us-east-1")
BUCKET = os.environ.get("BUCKET_NAME", "")
TABLE_NAME = os.environ.get("TABLE_NAME", "")
ACTIVITY_TABLE = os.environ.get("ACTIVITY_TABLE", "")
EMBEDDING_MODEL_ID = os.environ.get("EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")
GENERATION_MODEL_ID = os.environ.get("GENERATION_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
TOP_K = int(os.environ.get("TOP_K", "5"))
ENABLE_OCR = os.environ.get("ENABLE_OCR", "true").lower() == "true"
EMBED_DIMENSIONS = 512
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ID_RE = re.compile(r"^[0-9a-f]{32}$")

s3 = boto3.client("s3", endpoint_url=f"https://s3.{REGION}.amazonaws.com",
                  config=Config(region_name=REGION, signature_version="s3v4",
                                retries={"max_attempts": 5, "mode": "standard"}))
bedrock = boto3.client("bedrock-runtime",
                       config=Config(region_name=REGION, read_timeout=120,
                                     retries={"max_attempts": 8, "mode": "adaptive"}))
textract = boto3.client("textract", config=Config(region_name=REGION))
lambda_client = boto3.client("lambda", config=Config(region_name=REGION))
_ddb = boto3.resource("dynamodb")
table = _ddb.Table(TABLE_NAME)           # documents
activity = _ddb.Table(ACTIVITY_TABLE)    # chats, feedback, study jobs


def _default(o):
    if isinstance(o, Decimal):
        return int(o) if o % 1 == 0 else float(o)
    raise TypeError


def response(status, body):
    return {"statusCode": status, "headers": {"Content-Type": "application/json"},
            "body": json.dumps(body, default=_default)}


def user_id(event):
    """Cognito 'sub' claim, already verified by the API Gateway JWT authorizer."""
    return event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]


def parse_body(event):
    try:
        return json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return {}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def ts_key():
    """Sortable nanosecond timestamp used inside sort keys."""
    return f"{time.time_ns():020d}"


def embed_text(text):
    """Titan Text Embeddings V2 -> normalised 512-d vector."""
    resp = bedrock.invoke_model(
        modelId=EMBEDDING_MODEL_ID, contentType="application/json", accept="application/json",
        body=json.dumps({"inputText": text[:8000], "dimensions": EMBED_DIMENSIONS, "normalize": True}))
    return json.loads(resp["body"].read())["embedding"]


def user_msg(text):
    return {"role": "user", "content": [{"text": text}]}


def assistant_msg(text):
    return {"role": "assistant", "content": [{"text": text}]}


def generate(system, messages, max_tokens=1024, temperature=0.2):
    """Bedrock Converse API. Returns (text, usage-dict)."""
    r = bedrock.converse(modelId=GENERATION_MODEL_ID, system=[{"text": system}], messages=messages,
                         inferenceConfig={"maxTokens": max_tokens, "temperature": temperature})
    return r["output"]["message"]["content"][0]["text"], r.get("usage", {})


def load_vector_chunks(uid, doc_id):
    key = f"vectors/{uid}/{doc_id}.json"
    return json.loads(s3.get_object(Bucket=BUCKET, Key=key)["Body"].read())["chunks"]
