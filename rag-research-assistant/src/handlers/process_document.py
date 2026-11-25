"""S3 trigger: file -> text (pypdf, or Textract OCR if scanned) -> chunks -> embeddings -> index."""
import json
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import unquote_plus

from pypdf import PdfReader

from common import BUCKET, ENABLE_OCR, embed_text, s3, table, textract
from rag_core import chunk_pages, text_to_pages

MAX_CHUNKS = 2000


def _set_status(uid, doc_id, status, **extra):
    names, values, expr = {"#s": "status"}, {":s": status}, "SET #s = :s"
    for i, (k, v) in enumerate(extra.items()):
        names[f"#k{i}"], values[f":v{i}"] = k, v
        expr += f", #k{i} = :v{i}"
    table.update_item(Key={"userId": uid, "docId": doc_id}, UpdateExpression=expr,
                      ExpressionAttributeNames=names, ExpressionAttributeValues=values)


def _ocr_pdf(key):
    """Amazon Textract asynchronous text detection (handles multi-page scanned PDFs)."""
    job = textract.start_document_text_detection(
        DocumentLocation={"S3Object": {"Bucket": BUCKET, "Name": key}})["JobId"]
    deadline = time.time() + 600
    while True:
        r = textract.get_document_text_detection(JobId=job)
        if r["JobStatus"] == "SUCCEEDED":
            break
        if r["JobStatus"] == "FAILED" or time.time() > deadline:
            raise RuntimeError("OCR failed or timed out")
        time.sleep(3)
    pages, token = {}, None
    while True:
        r = textract.get_document_text_detection(JobId=job, **({"NextToken": token} if token else {}))
        for b in r["Blocks"]:
            if b["BlockType"] == "LINE":
                pages.setdefault(b.get("Page", 1), []).append(b["Text"])
        token = r.get("NextToken")
        if not token:
            break
    return ["\n".join(pages.get(p, [])) for p in range(1, max(pages, default=0) + 1)]


def _extract(local, ext, key):
    """Returns (pages: list[str], used_ocr: bool)."""
    if ext in ("txt", "md"):
        with open(local, "rb") as fh:
            return text_to_pages(fh.read().decode("utf-8", "ignore")), False
    reader = PdfReader(local)
    if reader.is_encrypted:
        reader.decrypt("")
    pages = [(p.extract_text() or "") for p in reader.pages]
    scanned = sum(len(p.strip()) for p in pages) < 30 * max(len(pages), 1)
    if scanned and ENABLE_OCR:
        return _ocr_pdf(key), True
    return pages, False


def _process(uid, doc_id, key, ext):
    local = f"/tmp/{doc_id}.{ext}"
    s3.download_file(BUCKET, key, local)
    pages, used_ocr = _extract(local, ext, key)

    chunks = chunk_pages(pages)
    if not chunks:
        raise ValueError("No extractable text found (is the file empty or an unreadable scan?).")
    if len(chunks) > MAX_CHUNKS:
        raise ValueError(f"Document too large ({len(chunks)} chunks, limit {MAX_CHUNKS}).")

    with ThreadPoolExecutor(max_workers=6) as pool:
        vectors = list(pool.map(lambda c: embed_text(c["text"]), chunks))

    records = [{"id": i, "page": c["page"], "text": c["text"], "embedding": [round(x, 5) for x in v]}
               for i, (c, v) in enumerate(zip(chunks, vectors))]
    s3.put_object(Bucket=BUCKET, Key=f"vectors/{uid}/{doc_id}.json",
                  Body=json.dumps({"docId": doc_id, "chunks": records}), ContentType="application/json")
    _set_status(uid, doc_id, "READY", pages=len(pages), chunks=len(records), ocr=used_ocr)


def handler(event, context):
    for rec in event["Records"]:
        key = unquote_plus(rec["s3"]["object"]["key"])
        parts = key.split("/")                      # uploads/<userId>/<docId>/source.<ext>
        if len(parts) != 4 or parts[0] != "uploads" or not parts[3].startswith("source."):
            continue
        _, uid, doc_id, fname = parts
        ext = fname.split(".", 1)[1]
        try:
            _set_status(uid, doc_id, "PROCESSING")
            _process(uid, doc_id, key, ext)
        except Exception as exc:
            traceback.print_exc()
            _set_status(uid, doc_id, "FAILED", error=str(exc)[:300])
