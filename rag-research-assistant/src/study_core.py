"""Pure helpers for the Study Studio (summary, flashcards, quiz, key terms)."""
import json
import re

MODES = ("summary", "flashcards", "quiz", "keyterms")


def sample_evenly(items, n):
    """Pick up to n items evenly spread across the list (keeps document coverage)."""
    if n <= 0 or not items:
        return []
    if len(items) <= n:
        return list(items)
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


def batch_texts(texts, max_chars=12000):
    batches, buf, size = [], [], 0
    for t in texts:
        if size + len(t) > max_chars and buf:
            batches.append("\n\n".join(buf))
            buf, size = [], 0
        buf.append(t)
        size += len(t)
    if buf:
        batches.append("\n\n".join(buf))
    return batches


def extract_json(text):
    """Pull the first JSON array/object out of an LLM reply (handles ``` fences and chatter)."""
    text = re.sub(r"```(?:json)?", "", text or "").strip()
    starts = [i for i in (text.find("["), text.find("{")) if i != -1]
    if not starts:
        raise ValueError("No JSON found in model output")
    start = min(starts)
    closer = "]" if text[start] == "[" else "}"
    end = text.rfind(closer)
    if end <= start:
        raise ValueError("Unterminated JSON in model output")
    return json.loads(text[start:end + 1])


MAP_SYSTEM = ("Summarise this part of a document in 5-8 concise bullet points. Keep important "
              "definitions, numbers and names. Use only the text given.")
REDUCE_SYSTEM = ("You are given partial summaries of one document in order. Write a final study summary in "
                 "Markdown with these sections: '## Overview' (3-4 sentences), '## Key Points' (bullets), "
                 "'## Important Terms' (bullets, term: meaning), '## Conclusion'. Use only the given content.")
FLASHCARD_SYSTEM = ("Create study flashcards from the text. Return ONLY a JSON array of objects "
                    '{"q": "...", "a": "...", "page": <int>}. Questions must be answerable from the text.')
QUIZ_SYSTEM = ("Create multiple-choice questions from the text. Return ONLY a JSON array of objects "
               '{"question": "...", "options": ["A","B","C","D"], "answerIndex": 0-3, "explanation": "...", '
               '"page": <int>}. Exactly 4 options; one correct; plausible distractors.')
KEYTERMS_SYSTEM = ("Extract the most important key terms from the text. Return ONLY a JSON array of objects "
                   '{"term": "...", "definition": "...", "page": <int>} using definitions from the text.')


def tag_chunks(chunks):
    return "\n\n".join(f"[page {c['page']}] {c['text']}" for c in chunks)


def validate_flashcards(data):
    return [{"q": str(x["q"]), "a": str(x["a"]), "page": x.get("page")}
            for x in data if isinstance(x, dict) and x.get("q") and x.get("a")]


def validate_quiz(data):
    out = []
    for x in data:
        try:
            opts = [str(o) for o in x["options"]]
            idx = int(x["answerIndex"])
            if len(opts) == 4 and 0 <= idx < 4 and x.get("question"):
                out.append({"question": str(x["question"]), "options": opts, "answerIndex": idx,
                            "explanation": str(x.get("explanation", "")), "page": x.get("page")})
        except (KeyError, TypeError, ValueError):
            continue
    return out


def validate_terms(data):
    return [{"term": str(x["term"]), "definition": str(x["definition"]), "page": x.get("page")}
            for x in data if isinstance(x, dict) and x.get("term") and x.get("definition")]
