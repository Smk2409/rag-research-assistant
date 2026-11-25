#!/usr/bin/env python3
"""Evaluate the deployed RAG API on a question set.

Metrics: keyword recall, citation rate, correct 'not found' refusals (hallucination guard), latency, tokens.
Usage:
  python eval/evaluate.py --api https://xxxx.execute-api.us-east-1.amazonaws.com --token $(python scripts/get_token.py ...) \
      --questions eval/questions.sample.json --out eval/report.md
Each question: {"question": str, "expected_keywords": [str], "expect_not_found": bool}"""
import argparse, json, statistics, time, urllib.request

NOT_FOUND = "could not find this in the uploaded documents"


def call(api, token, q):
    req = urllib.request.Request(api + "/ask", data=json.dumps({"question": q}).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": token})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    data["wall"] = time.time() - t0
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True); ap.add_argument("--token", required=True)
    ap.add_argument("--questions", required=True); ap.add_argument("--out", default="eval/report.md")
    a = ap.parse_args()
    rows, lat = [], []
    for item in json.load(open(a.questions)):
        d = call(a.api, a.token, item["question"])
        ans = d["answer"].lower()
        refused = NOT_FOUND in ans
        if item.get("expect_not_found"):
            ok, recall = refused, None
        else:
            kws = item.get("expected_keywords", [])
            recall = sum(k.lower() in ans for k in kws) / len(kws) if kws else None
            ok = (recall is None or recall >= 0.5) and not refused
        lat.append(d["wall"])
        rows.append((item["question"], ok, recall, bool(d["sources"]), d.get("confidence"), d["wall"]))
    passed = sum(r[1] for r in rows)
    lines = ["# RAG evaluation report", "", f"- Questions: {len(rows)}", f"- Passed: {passed} ({passed/len(rows):.0%})",
             f"- Citation rate: {sum(r[3] for r in rows)/len(rows):.0%}",
             f"- Median latency: {statistics.median(lat):.1f}s  |  p90: {sorted(lat)[int(len(lat)*0.9)-1]:.1f}s", "",
             "| Question | Pass | Keyword recall | Cited | Confidence | Latency |", "|---|---|---|---|---|---|"]
    for q, ok, rec, cited, conf, w in rows:
        lines.append(f"| {q[:60]} | {'✅' if ok else '❌'} | {'-' if rec is None else f'{rec:.0%}'} | {cited} | {conf} | {w:.1f}s |")
    open(a.out, "w").write("\n".join(lines)); print("\n".join(lines))


if __name__ == "__main__":
    main()
