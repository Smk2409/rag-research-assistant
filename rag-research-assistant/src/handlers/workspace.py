"""Chat history, feedback and usage statistics.
GET /chats | GET /chats/{sessionId} | DELETE /chats/{sessionId} | POST /feedback | GET /stats"""
import json

from boto3.dynamodb.conditions import Key

from common import ID_RE, activity, now_iso, parse_body, response, table, ts_key, user_id


def list_chats(event):
    r = activity.query(KeyConditionExpression=Key("userId").eq(user_id(event)) & Key("sk").begins_with("SESSION#"))
    chats = sorted(({"sessionId": i["sk"].split("#", 1)[1], "title": i.get("title", "Chat"),
                     "updatedAt": i.get("updatedAt", "")} for i in r["Items"]),
                   key=lambda c: c["updatedAt"], reverse=True)
    return response(200, {"chats": chats[:50]})


def _valid_sid(event):
    sid = event["pathParameters"]["sessionId"]
    return sid if ID_RE.match(sid) else None


def get_chat(event):
    sid = _valid_sid(event)
    if not sid:
        return response(400, {"error": "Invalid session"})
    r = activity.query(KeyConditionExpression=Key("userId").eq(user_id(event)) & Key("sk").begins_with(f"MSG#{sid}#"))
    msgs = [{"messageId": i["sk"].rsplit("#", 1)[1], "role": i["role"], "text": i["text"],
             "sources": json.loads(i.get("sources", "[]")), "confidence": i.get("confidence")} for i in r["Items"]]
    return response(200, {"sessionId": sid, "messages": msgs})


def delete_chat(event):
    sid, uid = _valid_sid(event), user_id(event)
    if not sid:
        return response(400, {"error": "Invalid session"})
    r = activity.query(KeyConditionExpression=Key("userId").eq(uid) & Key("sk").begins_with(f"MSG#{sid}#"),
                       ProjectionExpression="sk")
    keys = [i["sk"] for i in r["Items"]] + [f"SESSION#{sid}"]
    with activity.batch_writer() as batch:
        for sk in keys:
            batch.delete_item(Key={"userId": uid, "sk": sk})
    return response(200, {"deleted": sid})


def feedback(event):
    b = parse_body(event)
    if b.get("rating") not in ("up", "down") or not ID_RE.match(str(b.get("sessionId", ""))):
        return response(400, {"error": "Invalid feedback"})
    activity.put_item(Item={"userId": user_id(event), "sk": f"FB#{ts_key()}", "sessionId": b["sessionId"],
                            "messageId": str(b.get("messageId", ""))[:40], "rating": b["rating"],
                            "comment": str(b.get("comment", ""))[:500], "createdAt": now_iso()})
    return response(200, {"ok": True})


def stats(event):
    uid = user_id(event)
    docs = table.query(KeyConditionExpression=Key("userId").eq(uid))["Items"]
    total = {"Select": "COUNT"}
    questions = activity.query(KeyConditionExpression=Key("userId").eq(uid) & Key("sk").begins_with("MSG#"),
                               FilterExpression="#r = :u", ExpressionAttributeNames={"#r": "role"},
                               ExpressionAttributeValues={":u": "user"}, **total)["Count"]
    fb = activity.query(KeyConditionExpression=Key("userId").eq(uid) & Key("sk").begins_with("FB#"))["Items"]
    ready = [d for d in docs if d.get("status") == "READY"]
    return response(200, {
        "documents": len(docs), "ready": len(ready),
        "pages": sum(int(d.get("pages", 0)) for d in ready), "chunks": sum(int(d.get("chunks", 0)) for d in ready),
        "ocrDocuments": sum(1 for d in ready if d.get("ocr")), "questions": questions,
        "thumbsUp": sum(1 for f in fb if f["rating"] == "up"), "thumbsDown": sum(1 for f in fb if f["rating"] == "down")})


ROUTES = {"GET /chats": list_chats, "GET /chats/{sessionId}": get_chat, "DELETE /chats/{sessionId}": delete_chat,
          "POST /feedback": feedback, "GET /stats": stats}


def handler(event, context):
    fn = ROUTES.get(event["routeKey"])
    return fn(event) if fn else response(404, {"error": "Not found"})
