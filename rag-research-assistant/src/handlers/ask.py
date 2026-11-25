"""POST /ask  -> conversational, hybrid-retrieval, citation-grounded answering.

Pipeline: validate -> load chat history -> rewrite follow-up question -> embed ->
hybrid search (vector + BM25 + RRF + MMR) -> grounded generation -> persist chat."""
import json
import time
import uuid

from boto3.dynamodb.conditions import Key

from common import (ID_RE, TOP_K, activity, assistant_msg, embed_text, generate, load_vector_chunks, now_iso,
                    parse_body, response, table, ts_key, user_id, user_msg)
from rag_core import (NOT_FOUND, STYLES, build_rewrite_prompt, build_user_prompt, confidence_label,
                      hybrid_search, normalize_history, REWRITE_SYSTEM, system_prompt, tokenize)

_cache = {}   # vector files stay in memory while the Lambda container is warm


def _chunks(uid, doc_id):
    key = (uid, doc_id)
    if key not in _cache:
        if len(_cache) > 15:
            _cache.clear()
        data = load_vector_chunks(uid, doc_id)
        for c in data:
            c["_tokens"] = tokenize(c["text"])
        _cache[key] = data
    return _cache[key]


def _history(uid, sid, limit=6):
    r = activity.query(KeyConditionExpression=Key("userId").eq(uid) & Key("sk").begins_with(f"MSG#{sid}#"),
                       ScanIndexForward=False, Limit=limit)
    msgs = [{"role": i["role"], "text": i["text"]} for i in reversed(r["Items"])]
    return normalize_history(msgs)


def _persist(uid, sid, question, answer, sources, confidence, is_new):
    t_user, t_bot = ts_key(), None
    activity.put_item(Item={"userId": uid, "sk": f"MSG#{sid}#{t_user}", "role": "user", "text": question})
    t_bot = ts_key()
    activity.put_item(Item={"userId": uid, "sk": f"MSG#{sid}#{t_bot}", "role": "assistant", "text": answer,
                            "sources": json.dumps(sources), "confidence": confidence})
    activity.update_item(
        Key={"userId": uid, "sk": f"SESSION#{sid}"},
        UpdateExpression="SET title = if_not_exists(title, :t), updatedAt = :u",
        ExpressionAttributeValues={":t": question[:60], ":u": now_iso()})
    return t_bot


def handler(event, context):
    t0 = time.time()
    uid = user_id(event)
    body = parse_body(event)
    question = str(body.get("question", "")).strip()
    if not question or len(question) > 1000:
        return response(400, {"error": "Provide a question (max 1000 characters)."})
    style = body.get("style") if body.get("style") in STYLES else "balanced"
    sid = body.get("sessionId") if ID_RE.match(str(body.get("sessionId", ""))) else uuid.uuid4().hex

    docs = [d for d in table.query(KeyConditionExpression=Key("userId").eq(uid))["Items"]
            if d.get("status") == "READY"]
    if body.get("docIds"):
        docs = [d for d in docs if d["docId"] in body["docIds"]]
    if not docs:
        return response(400, {"error": "No processed documents available. Upload a document first."})

    history = _history(uid, sid)
    usage = {"inputTokens": 0, "outputTokens": 0}

    standalone = question
    if history:                                   # resolve "what about its limitations?" etc.
        standalone, u = generate(REWRITE_SYSTEM, [user_msg(build_rewrite_prompt(history, question))],
                                 max_tokens=120, temperature=0)
        standalone = standalone.strip() or question
        for k in usage:
            usage[k] += u.get(k, 0)

    q_vec = embed_text(standalone)
    pool = [{**c, "docId": d["docId"], "filename": d["filename"]} for d in docs for c in _chunks(uid, d["docId"])]
    hits = hybrid_search(standalone, q_vec, pool, k=TOP_K)

    if not hits:
        answer, sources, confidence = NOT_FOUND, [], "none"
    else:
        passages = [{"filename": h["item"]["filename"], "page": h["item"]["page"], "text": h["item"]["text"]}
                    for h in hits]
        messages = [{"role": m["role"], "content": [{"text": m["text"]}]} for m in history]
        messages.append(user_msg(build_user_prompt(question, passages)))
        answer, u = generate(system_prompt(style), messages, max_tokens=1024, temperature=0.2)
        for k in usage:
            usage[k] += u.get(k, 0)
        sources = [{"ref": i, "docId": h["item"]["docId"], "filename": h["item"]["filename"],
                    "page": h["item"]["page"], "score": round(h["vec"], 3), "keyword": round(h["bm25"], 2),
                    "snippet": h["item"]["text"][:300]} for i, h in enumerate(hits, start=1)]
        confidence = confidence_label(max(h["vec"] for h in hits))

    message_id = _persist(uid, sid, question, answer, sources, confidence, not history)
    return response(200, {"sessionId": sid, "messageId": message_id, "answer": answer, "sources": sources,
                          "confidence": confidence, "rewrittenQuestion": standalone, "usage": usage,
                          "latencyMs": int((time.time() - t0) * 1000)})
