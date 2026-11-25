# Viva / Interview Questions & Answers

## A. Concepts
1. **What is RAG?** Retrieve relevant passages from a knowledge source at query time and give them to an LLM so its answer is grounded in them.
2. **Why RAG rather than fine-tuning?** Cheaper; no retraining per document; instantly updatable; private data stays out of model weights; answers are traceable.
3. **What is an embedding?** A numeric vector representing meaning; semantically similar texts are close in vector space.
4. **What is cosine similarity?** Cosine of the angle between two vectors; with normalised vectors it equals the dot product.
5. **What is a hallucination and how do you reduce it?** Fluent but unsupported output. Reduced by grounding prompt, low temperature, retrieval gate, citations, refusal phrase.
6. **What is chunking and why overlap?** Splitting text into pieces that fit retrieval/LLM context; overlap keeps facts at boundaries intact.
7. **Why 1000 chars / 200 overlap?** Trade-off: big enough for context, small enough for precise retrieval; tunable.
8. **What is top-K?** Number of passages sent to the LLM (default 5).
9. **What is BM25?** Probabilistic keyword ranking using term frequency, inverse document frequency and length normalisation.
10. **Why hybrid search?** Vectors capture meaning but can miss exact terms/acronyms; BM25 does the opposite; combining improves recall.
11. **What is Reciprocal Rank Fusion?** Merges rankings using `Σ 1/(k+rank)`; needs no score normalisation.
12. **What is MMR?** Maximal Marginal Relevance: picks passages that are relevant yet different from those already chosen.
13. **What is query rewriting?** Turning a follow-up ("what about its limits?") into a standalone query using chat history.
14. **What is a context window?** Max tokens an LLM can read; why we send only top chunks.
15. **What is temperature?** Randomness control; 0.2 here for factual answers.
16. **What is prompt injection?** Malicious text in documents that tries to override instructions; mitigated by treating context as untrusted and never executing it.
17. **What is OCR?** Converting images of text to text; done with Amazon Textract for scanned PDFs.
18. **What is map-reduce summarisation?** Summarise parts independently (map), then combine (reduce) to handle documents longer than the context window.
19. **What does the confidence badge mean?** A heuristic based on the best cosine similarity; guidance, not a guarantee.
20. **What is the retrieval gate?** If no chunk passes relevance checks we return "not found" without calling the LLM.

## B. AWS
21. **Why serverless?** No server management, automatic scaling, pay-per-use, near-zero idle cost.
22. **Role of S3?** Stores PDFs, vector indexes and static website.
23. **Why presigned POST?** Browser uploads directly to S3; avoids API/Lambda payload limits; S3 enforces type and size.
24. **What triggers processing?** S3 `ObjectCreated` event invokes the process Lambda.
25. **Why is processing timeout 900 s?** OCR and embedding of big files can take minutes (Lambda maximum 15 min).
26. **Why Bedrock?** Managed access to foundation models (Claude, Titan) without hosting; pay per token; data not used to train base models.
27. **What is the Converse API?** A unified Bedrock chat API (system prompt, messages, inference config) across models.
28. **Which embedding model and dimension?** Titan Text Embeddings V2, 512 dims, normalised.
29. **Why Cognito?** Managed sign-up/sign-in, e-mail verification, JWT tokens integrated with API Gateway.
30. **How is the API protected?** HTTP API JWT authorizer validates Cognito ID token before Lambda runs.
31. **How is multi-user isolation enforced?** `userId` (token claim) is part of every DynamoDB key and S3 path; clients never supply it.
32. **Why two DynamoDB tables?** Documents are a simple entity; activity uses single-table design for chats/feedback/jobs with TTL.
33. **What is single-table design?** Multiple entity types in one table using composite sort keys (`SESSION#`, `MSG#`, `JOB#`).
34. **Why async study jobs?** API Gateway HTTP API timeout is 30 s; long LLM jobs run in a worker and the UI polls.
35. **What is CloudFront OAC?** Lets CloudFront read a private S3 bucket using signed requests; bucket stays non-public.
36. **How is the infrastructure deployed?** AWS SAM (CloudFormation) from `template.yaml`; `deploy.sh` automates it.
37. **How do you monitor it?** CloudWatch dashboard/alarms, Lambda logs, X-Ray tracing, SNS e-mail alerts.
38. **How do you control cost?** Pay-per-request services, small embeddings, cheap model, limits on file size/chunks, AWS Budgets.
39. **What IAM approach is used?** Least privilege per Lambda (e.g. ask can read only `vectors/*`).
40. **What happens if Bedrock throttles?** Adaptive retries in boto3; user can retry; alarms notify on repeated errors.

## C. Design & trade-offs
41. **Why not OpenSearch/Pinecone?** Cost/complexity at student scale; S3 + in-Lambda search is nearly free. Retrieval is isolated in `rag_core.py` for easy replacement.
42. **Scalability limit of your approach?** Linear scan; fine for thousands of chunks per user; beyond that use a vector database/ANN index (HNSW).
43. **Why cache vectors in Lambda memory?** Avoids repeated S3 reads on warm invocations.
44. **Cold start impact?** First request loads vectors from S3 (a second or two); subsequent are fast.
45. **How do you handle encrypted PDFs?** Try empty-password decrypt; otherwise fails with message.
46. **How do you handle scanned PDFs?** Detect near-empty text, fall back to Textract async OCR.
47. **How do text files get "pages"?** Split into virtual sections (~3000 chars) so citations still work.
48. **How is the user's question protected from abuse?** Max length 1000, API throttling, JWT required.
49. **Why show similarity scores and snippets?** Transparency; users can verify the evidence.
50. **How do you evaluate quality?** `eval/evaluate.py`: keyword recall, citation rate, refusal accuracy, latency; plus unit tests for retrieval logic.
51. **What would you improve first?** Cross-encoder re-ranking and Bedrock Guardrails, then a vector database.
52. **How would you support multiple languages?** Multilingual embeddings (Titan V2 supports many languages), language-aware tokenisation, Amazon Translate.
53. **How would you add streaming?** Lambda response streaming or WebSocket API with `converse_stream`.
54. **How do you prevent the model using outside knowledge?** System prompt rule + low temperature + only context passages provided + refusal phrase.
55. **Privacy?** Documents in private S3 per user; Bedrock does not use inputs to train base models; delete removes file, vectors and metadata.
