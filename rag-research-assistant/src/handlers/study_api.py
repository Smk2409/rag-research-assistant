"""POST /study (start async job) and GET /study/{jobId} (poll) for the Study Studio."""
import json
import time
import uuid

from common import ID_RE, activity, lambda_client, now_iso, parse_body, response, table, user_id
from study_core import MODES
import os



def start(event):
    uid, b = user_id(event), parse_body(event)
    mode, doc_id = b.get("mode"), str(b.get("docId", ""))
    if mode not in MODES or not ID_RE.match(doc_id):
        return response(400, {"error": f"mode must be one of {MODES} and docId is required"})
    doc = table.get_item(Key={"userId": uid, "docId": doc_id}).get("Item")
    if not doc or doc.get("status") != "READY":
        return response(400, {"error": "Document not found or not ready."})
    count = max(3, min(int(b.get("count", 10) or 10), 25))

    job_id = uuid.uuid4().hex
    activity.put_item(Item={"userId": uid, "sk": f"JOB#{job_id}", "status": "PENDING", "mode": mode,
                            "docId": doc_id, "filename": doc["filename"], "createdAt": now_iso(),
                            "ttl": int(time.time()) + 7 * 86400})
    lambda_client.invoke(FunctionName=os.environ["WORKER_NAME"], InvocationType="Event",
                         Payload=json.dumps({"uid": uid, "jobId": job_id, "docId": doc_id, "mode": mode,
                                             "count": count}).encode())
    return response(202, {"jobId": job_id})


def poll(event):
    job_id = event["pathParameters"]["jobId"]
    if not ID_RE.match(job_id):
        return response(400, {"error": "Invalid job"})
    job = activity.get_item(Key={"userId": user_id(event), "sk": f"JOB#{job_id}"}).get("Item")
    if not job:
        return response(404, {"error": "Job not found"})
    out = {"jobId": job_id, "status": job["status"], "mode": job["mode"], "filename": job.get("filename")}
    if job["status"] == "DONE":
        out["result"] = json.loads(job["result"])
    if job["status"] == "FAILED":
        out["error"] = job.get("error", "Job failed")
    return response(200, out)


def handler(event, context):
    return start(event) if event["routeKey"] == "POST /study" else poll(event)
