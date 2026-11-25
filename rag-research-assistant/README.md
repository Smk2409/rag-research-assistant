# 📚 Cloud-Based AI Research Assistant using RAG and AWS  (v2 — "Ultra" edition)

> **Domain:** Artificial Intelligence · Generative AI · Cloud Computing
> **Idea:** Students upload study material (PDF/TXT/MD, even scanned PDFs) and chat with it. The system retrieves the most relevant passages using **hybrid search** and generates **document-grounded, cited answers** — then turns the same material into summaries, flashcards, quizzes and key-term lists.

---

## ✨ Feature Overview
| Area | Feature |
|---|---|
| **Ingestion** | PDF, TXT, Markdown · drag-and-drop · multi-file · upload progress bar · 20 MB limit enforced by S3 itself |
| **OCR** | Scanned PDFs automatically detected → **Amazon Textract** async OCR |
| **Retrieval** | **Hybrid search**: dense vectors (Titan V2) + **BM25** keywords → **Reciprocal Rank Fusion** → **MMR** diversification |
| **Generation** | Claude on **Amazon Bedrock** (Converse API); strict grounding prompt; "not found" fallback; prompt-injection guard |
| **Chat** | Persistent chat sessions · **conversation memory** · automatic **follow-up question rewriting** · 5 answer styles (balanced / concise / detailed / explain-simply / exam notes) |
| **Trust** | Numbered **clickable citations** `[1]` · source snippets · similarity score · **confidence badge** · open original PDF **at the cited page** |
| **Study Studio** | Structured **summary** (map-reduce), **flashcards** (flip cards), **practice quiz** (auto-graded), **key terms** — generated asynchronously |
| **Productivity** | Voice input 🎤 · read-aloud 🔊 · copy · export chat to Markdown · dark/light theme · 👍/👎 feedback |
| **Dashboard** | Usage stats, document library, CloudWatch dashboard + alarms (optional e-mail) |
| **Security** | Cognito JWT · per-user data isolation · private S3 · OAC CloudFront · security headers · least-privilege IAM · API throttling · XSS-safe rendering |
| **DevOps** | One-command IaC deploy (SAM) · teardown script · GitHub Actions CI · 21 unit tests · evaluation harness · X-Ray tracing |

## 1. Problem & Motivation
Students handle long textbooks and papers. Ctrl+F only finds exact words; general chatbots **hallucinate** and can't cite the student's own material. **Retrieval-Augmented Generation (RAG)** fixes this: the LLM may answer *only* from passages retrieved from the user's documents, and every claim is traceable to a page.

## 2. RAG in 60 seconds
1. **Index (once per file):** extract text → chunk (1000 chars, 200 overlap) → embed each chunk → store vectors.
2. **Retrieve (per question):** embed the question → find the most relevant chunks (vector similarity **and** keyword match).
3. **Generate:** give top chunks + question to the LLM: *"answer only from this context, cite [n]"*.

## 3. AWS Services
| Service | Role |
|---|---|
| **S3** | PDFs (`uploads/`), vector indexes (`vectors/`), frontend hosting |
| **Lambda** (6 functions) | documents API · process-document · ask · workspace · study API · study worker |
| **Bedrock — Titan Text Embeddings V2** | 512-d normalised embeddings |
| **Bedrock — Claude (Converse API)** | rewriting, answers, summaries, flashcards, quizzes |
| **Textract** | OCR for scanned PDFs |
| **API Gateway (HTTP API)** | 12 REST routes, JWT authorizer, throttling |
| **Cognito** | Sign-up, e-mail verification, sign-in, password reset, token refresh |
| **DynamoDB ×2** | `DocumentsTable` (metadata/status) · `ActivityTable` (single-table: chats, feedback, study jobs, TTL) |
| **CloudFront** | HTTPS, compression, security headers, private-bucket origin (OAC) |
| **CloudWatch + SNS + X-Ray** | Dashboard, error alarms, tracing |
| **SAM / CloudFormation** | Entire stack as code (`template.yaml`) |

## 4. Architecture
```
 Browser ──► CloudFront ──► S3 (static UI)
    │  sign-in
    ▼
 Cognito ──JWT──► API Gateway (authorizer · throttle)
                   │
   ┌───────────────┼───────────────┬───────────────┐
   ▼               ▼               ▼               ▼
documents         ask          workspace        study API ──async──► study-worker
(upload/list/    (hybrid RAG    (chats/stats/     │                      │
 delete/open)     + memory)      feedback)        ▼                      ▼
   │               │  │            │         ActivityTable          Bedrock/S3
   │ presigned     │  └► Bedrock (rewrite · embed · generate)
   ▼               ▼
  S3 ◄─ ObjectCreated ─► process-document ─► (Textract OCR?) ─► Titan embeddings ─► S3 vectors + DynamoDB
```
Mermaid versions: `docs/architecture.mmd`, `docs/sequence_ask.mmd`.

### Upload & indexing flow
1. `POST /documents/upload-url` → record created (`UPLOADING`) + **presigned POST** (type & size enforced by S3).
2. Browser uploads **directly to S3** (no Lambda payload limits).
3. S3 event → `process-document`: `PROCESSING` → extract text (pypdf; **Textract if scanned**) → chunk with page numbers → parallel embeddings → `vectors/<user>/<doc>.json` → `READY` (or `FAILED` with a readable reason).
4. UI polls every 5 s and shows status badges.

### Question flow (`POST /ask`)
1. Load the last 3 turns of the chat → **rewrite** follow-ups into a standalone query (*"what about its limits?"* → *"What are the limitations of gradient descent?"*).
2. Embed query → load the user's vectors (cached while Lambda is warm).
3. **Hybrid search:** cosine similarity ranking + BM25 ranking → **RRF** fusion → **MMR** to avoid near-duplicate passages → top-K.
4. If nothing relevant: return *"I could not find this in the uploaded documents."* (**no LLM call → zero hallucination**).
5. Otherwise Claude answers with citations; response includes sources, confidence, latency and token usage; chat is stored.

### Study Studio flow (async)
API Gateway has a hard 30 s limit, so `POST /study` creates a job and **invokes a worker asynchronously**; the UI polls `GET /study/{jobId}`. Summaries use **map-reduce** (chunk batches → partial summaries in parallel → final structured summary), flashcards/quiz/key-terms sample chunks evenly across the document and parse validated JSON.

## 5. Project Structure
```
rag-research-assistant/
├── template.yaml            # all AWS resources (IaC)
├── deploy.sh / destroy.sh   # one-command deploy & teardown
├── Makefile · samconfig.toml.example · .gitignore
├── .github/workflows/ci.yml # tests + sam validate on every push
├── src/                     # Lambda code
│   ├── common.py            # clients, Titan embed, Bedrock generate, helpers
│   ├── rag_core.py          # chunking, BM25, RRF, MMR, hybrid search, prompts   (pure, tested)
│   ├── study_core.py        # sampling, batching, JSON parsing/validation        (pure, tested)
│   └── handlers/
│       ├── documents.py        # upload-url · list · delete · open-original
│       ├── process_document.py # S3 trigger: extract/OCR → chunk → embed → index
│       ├── ask.py              # memory + rewrite + hybrid RAG + generation
│       ├── workspace.py        # chats · feedback · stats
│       ├── study_api.py        # start / poll study jobs
│       └── study_worker.py     # async summary / flashcards / quiz / key terms
├── frontend/ index.html · styles.css · app.js · config.js
├── tests/ test_rag_core.py · test_study_core.py   (21 tests)
├── scripts/ offline_demo.py (RAG without AWS) · get_token.py
├── eval/ evaluate.py · questions.sample.json      (quality evaluation)
└── docs/ PROJECT_REPORT.md · VIVA_QA.md · DEMO_SCRIPT.md · architecture.mmd · sequence_ask.mmd
```

## 6. Prerequisites
- AWS account · AWS CLI v2 (`aws configure`) · AWS SAM CLI · Python 3.12 · Node not required
- **Bedrock → Model access:** enable *Titan Text Embeddings V2* and a *Claude* model in your deployment region
- Textract available in the region (e.g. `us-east-1`)

## 7. Deploy (step by step)
```bash
unzip rag-research-assistant.zip && cd rag-research-assistant
pip install pytest pypdf          # for the pre-deploy tests
./deploy.sh us-east-1 rag-research-assistant
# optional: ALERT_EMAIL=me@x.com MODEL_ID=<bedrock-model-id> ENABLE_OCR=false ./deploy.sh
```
The script: runs tests → `sam build` → `sam deploy` → writes `frontend/config.js` → syncs UI to S3 → prints the **CloudFront URL**.

**Model ID note:** if the default Claude ID is unavailable/not enabled (newer models may need an *inference profile ID* like `us.anthropic.…`), copy the ID from Bedrock → Model catalog and set `MODEL_ID`.

**Try without deploying anything:** `python scripts/offline_demo.py mynotes.pdf "what is overfitting"` (BM25 retrieval locally), and `pytest tests -q`.

**Local UI testing:** after deploying once, `make serve` and open http://localhost:8080 (API allows any origin; protected by JWT).

**Teardown:** `./destroy.sh us-east-1 rag-research-assistant`

## 8. API Reference (header `Authorization: <Cognito ID token>`)
| Method & path | Body | Returns |
|---|---|---|
| `POST /documents/upload-url` | `{filename}` | `{docId, upload:{url,fields}}` |
| `GET /documents` | – | documents with status/pages/chunks/ocr |
| `DELETE /documents/{docId}` | – | `{deleted}` |
| `GET /documents/{docId}/url` | – | short-lived URL of the original file |
| `POST /ask` | `{question, docIds?, sessionId?, style?}` | `{answer, sources[], confidence, sessionId, messageId, rewrittenQuestion, usage, latencyMs}` |
| `GET /chats` · `GET /chats/{id}` · `DELETE /chats/{id}` | – | chat list / messages / delete |
| `POST /feedback` | `{sessionId, messageId, rating:"up"|"down"}` | `{ok}` |
| `POST /study` | `{docId, mode:"summary|flashcards|quiz|keyterms", count}` | `202 {jobId}` |
| `GET /study/{jobId}` | – | `{status, result}` |
| `GET /stats` | – | usage statistics |

## 9. Design Decisions
| Decision | Why |
|---|---|
| Serverless everywhere | No servers, pay-per-use, scales to zero |
| Presigned POST uploads | Bypass API/Lambda size limits; S3 enforces type + 20 MB |
| Vectors in S3 + in-Lambda search | ~$0 idle cost vs OpenSearch Serverless (~$170+/mo minimum); fine for thousands of chunks/user. Retrieval is isolated in `rag_core.py` → swap for OpenSearch/pgvector later |
| Hybrid (vector + BM25) + RRF | Dense search misses exact terms/acronyms; BM25 misses paraphrases; fusion gets both without score-scale tuning |
| MMR | Overlapping chunks produce near-duplicates; MMR gives diverse evidence |
| Query rewriting | Makes multi-turn chat retrieve correctly |
| Retrieval gate (no LLM when nothing relevant) | Cheapest and safest anti-hallucination measure |
| Async study jobs | Beats API Gateway 30 s limit |
| Single-table DynamoDB for activity | One table serves chats, feedback, jobs; TTL auto-expires jobs |
| Titan V2 @ 512 dims, normalised | Small index; cosine = dot product |

## 10. Security
JWT-verified identity (user id from claims, never from input) · keys contain `userId` → row-level isolation · IDs validated by regex · S3 keys never contain user text · private encrypted buckets · CloudFront OAC + security-headers policy · least-privilege IAM per function · API throttling · prompts treat document text as untrusted (prompt-injection mitigation) · answers rendered with escape-first Markdown (XSS-safe) · presigned URLs expire in 5 min · PITR on documents table.
*Hardening ideas:* restrict CORS to your CloudFront domain, AWS WAF, Bedrock Guardrails, custom domain + ACM.

## 11. Cost (light student use)
Everything is pay-per-request. Typical monthly cost: **a few dollars or less** (Bedrock embeddings ≈ cents per million tokens; Haiku-class answers ≈ fractions of a cent; Textract ≈ $1.50 per 1,000 OCR pages — only for scanned PDFs; Lambda/API/DynamoDB/S3 ≈ free tier; Cognito free < 10k MAU). Set an **AWS Budget alert**.

## 12. Testing & Evaluation
- **Unit tests (21):** chunking, BM25, RRF, hybrid search (keyword rescue, MMR de-duplication, no-hit), history normalisation, JSON extraction/validation.
- **Evaluation harness:** `python eval/evaluate.py --api <url> --token <idtoken> --questions eval/questions.sample.json` → keyword recall, citation rate, correct refusals on unanswerable questions, median/p90 latency (Markdown report).
- **Manual E2E:** see `docs/DEMO_SCRIPT.md`.
- **Observability:** CloudWatch dashboard `<stack>-dashboard`, alarms, X-Ray traces, Lambda logs.

## 13. Troubleshooting
| Symptom | Fix |
|---|---|
| Bedrock `AccessDeniedException` | Enable model access in that region / correct `MODEL_ID` |
| Doc `FAILED: No extractable text` | Empty/unreadable file; for scans make sure `ENABLE_OCR=true` and Textract exists in region |
| `/ask` 504 | Very large corpus or throttling; reduce selected docs or `TopK` |
| 403 on upload | URL expired (5 min), wrong type or > 20 MB |
| Bucket exists | Change `ProjectName` (globally unique) |

## 14. Limitations
Brute-force search (limit ≈ 2,000 chunks/doc); tables/figures aren't interpreted; Textract OCR adds time/cost; answers stream-less (non-streaming); English-centric BM25 stop-words.

## 15. Future Work
OpenSearch Serverless / Aurora pgvector / Bedrock Knowledge Bases · cross-encoder re-ranking · Bedrock Guardrails · streaming responses · multilingual support (Translate) · image/table understanding with multimodal models · shared class workspaces · RAGAS-style automated evaluation · spaced-repetition scheduling for flashcards.

## 16. Documentation Index
`docs/PROJECT_REPORT.md` (full academic report) · `docs/VIVA_QA.md` (50+ viva questions) · `docs/DEMO_SCRIPT.md` (live demo flow & sample questions).

##Off Campus code
6GJZES
