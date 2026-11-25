"""Async worker: builds summaries, flashcards, quizzes and key-term lists from a document."""
import json
import traceback
from concurrent.futures import ThreadPoolExecutor

from common import activity, generate, load_vector_chunks, user_msg
from study_core import (FLASHCARD_SYSTEM, KEYTERMS_SYSTEM, MAP_SYSTEM, QUIZ_SYSTEM, REDUCE_SYSTEM, batch_texts,
                        extract_json, sample_evenly, tag_chunks, validate_flashcards, validate_quiz,
                        validate_terms)


def _summary(chunks, count):
    texts = [f"(p.{c['page']}) {c['text']}" for c in chunks]
    batches = sample_evenly(batch_texts(texts, 12000), 8)
    with ThreadPoolExecutor(max_workers=4) as pool:
        partials = list(pool.map(lambda b: generate(MAP_SYSTEM, [user_msg(b)], 600)[0], batches))
    final, _ = generate(REDUCE_SYSTEM, [user_msg("\n\n".join(partials))], 1400)
    return {"markdown": final, "sections": len(batches)}


def _json_task(system, chunks, n_chunks, instruction, validator):
    picked = sample_evenly(chunks, n_chunks)
    text, _ = generate(system, [user_msg(f"{instruction}\n\nTEXT:\n{tag_chunks(picked)}")], 3000, 0.4)
    return validator(extract_json(text))


def _run(mode, chunks, count):
    if mode == "summary":
        return _summary(chunks, count)
    if mode == "flashcards":
        return {"cards": _json_task(FLASHCARD_SYSTEM, chunks, max(6, count), f"Create {count} flashcards.", validate_flashcards)}
    if mode == "quiz":
        return {"questions": _json_task(QUIZ_SYSTEM, chunks, max(6, count), f"Create {count} questions.", validate_quiz)}
    return {"terms": _json_task(KEYTERMS_SYSTEM, chunks, 15, f"Extract up to {count + 5} key terms.", validate_terms)}


def _update(uid, job_id, status, **extra):
    names, values, expr = {"#s": "status"}, {":s": status}, "SET #s = :s"
    for i, (k, v) in enumerate(extra.items()):
        names[f"#k{i}"], values[f":v{i}"] = k, v
        expr += f", #k{i} = :v{i}"
    activity.update_item(Key={"userId": uid, "sk": f"JOB#{job_id}"}, UpdateExpression=expr,
                         ExpressionAttributeNames=names, ExpressionAttributeValues=values)


def handler(event, context):
    uid, job_id = event["uid"], event["jobId"]
    try:
        _update(uid, job_id, "RUNNING")
        chunks = load_vector_chunks(uid, event["docId"])
        result = _run(event["mode"], chunks, int(event.get("count", 10)))
        _update(uid, job_id, "DONE", result=json.dumps(result))
    except Exception as exc:
        traceback.print_exc()
        _update(uid, job_id, "FAILED", error=str(exc)[:300])
