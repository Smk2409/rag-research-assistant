"""Document management API.
POST /documents/upload-url | GET /documents | DELETE /documents/{docId} | GET /documents/{docId}/url"""
import re
import uuid

from boto3.dynamodb.conditions import Key

from common import (BUCKET, ID_RE, MAX_UPLOAD_BYTES, now_iso, parse_body, response, s3, table, user_id)

ALLOWED = {"pdf": "application/pdf", "txt": "text/plain", "md": "text/markdown"}


def upload_url(event):
    uid = user_id(event)
    filename = re.sub(r"[^\w.\- ]", "_", str(parse_body(event).get("filename", ""))[:200])
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED:
        return response(400, {"error": "Supported file types: PDF, TXT, MD."})

    doc_id = uuid.uuid4().hex
    key = f"uploads/{uid}/{doc_id}/source.{ext}"       # never contains user-supplied text
    table.put_item(Item={"userId": uid, "docId": doc_id, "filename": filename, "ext": ext, "key": key,
                         "status": "UPLOADING", "createdAt": now_iso()})
    post = s3.generate_presigned_post(
        Bucket=BUCKET, Key=key, Fields={"Content-Type": ALLOWED[ext]},
        Conditions=[{"Content-Type": ALLOWED[ext]}, ["content-length-range", 1, MAX_UPLOAD_BYTES]],
        ExpiresIn=300)
    return response(200, {"docId": doc_id, "upload": post})


def list_documents(event):
    items = table.query(KeyConditionExpression=Key("userId").eq(user_id(event)))["Items"]
    items.sort(key=lambda i: i.get("createdAt", ""), reverse=True)
    fields = ("docId", "filename", "ext", "status", "pages", "chunks", "ocr", "createdAt", "error")
    return response(200, {"documents": [{k: i.get(k) for k in fields} for i in items]})


def _get_doc(event):
    doc_id = event["pathParameters"]["docId"]
    if not ID_RE.match(doc_id):
        return None
    return table.get_item(Key={"userId": user_id(event), "docId": doc_id}).get("Item")


def delete_document(event):
    item = _get_doc(event)
    if not item:                      # key includes userId, so other users' docs are unreachable
        return response(404, {"error": "Document not found."})
    uid = item["userId"]
    s3.delete_object(Bucket=BUCKET, Key=item["key"])
    s3.delete_object(Bucket=BUCKET, Key=f"vectors/{uid}/{item['docId']}.json")
    table.delete_item(Key={"userId": uid, "docId": item["docId"]})
    return response(200, {"deleted": item["docId"]})


def document_url(event):
    item = _get_doc(event)
    if not item:
        return response(404, {"error": "Document not found."})
    url = s3.generate_presigned_url(
        "get_object", ExpiresIn=300,
        Params={"Bucket": BUCKET, "Key": item["key"], "ResponseContentType": ALLOWED[item["ext"]],
                "ResponseContentDisposition": "inline"})
    return response(200, {"url": url, "filename": item["filename"], "ext": item["ext"]})


ROUTES = {
    "POST /documents/upload-url": upload_url,
    "GET /documents": list_documents,
    "DELETE /documents/{docId}": delete_document,
    "GET /documents/{docId}/url": document_url,
}


def handler(event, context):
    fn = ROUTES.get(event["routeKey"])
    return fn(event) if fn else response(404, {"error": "Not found"})
