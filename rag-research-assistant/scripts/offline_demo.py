#!/usr/bin/env python3
"""Understand RAG without AWS: chunk a PDF/TXT locally and retrieve passages with BM25.
Usage: python scripts/offline_demo.py path/to/file.pdf "your question"
(Requires: pip install pypdf)"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from rag_core import chunk_pages, text_to_pages, tokenize, bm25_scores

if len(sys.argv) < 3:
    sys.exit(__doc__)
path, question = sys.argv[1], " ".join(sys.argv[2:])
if path.lower().endswith(".pdf"):
    from pypdf import PdfReader
    pages = [(p.extract_text() or "") for p in PdfReader(path).pages]
else:
    pages = text_to_pages(open(path, encoding="utf-8", errors="ignore").read())
chunks = chunk_pages(pages)
print(f"{len(pages)} pages -> {len(chunks)} chunks")
scores = bm25_scores(question, [tokenize(c["text"]) for c in chunks])
for rank, i in enumerate(sorted(range(len(chunks)), key=lambda i: -scores[i])[:3], 1):
    print(f"\n#{rank}  page {chunks[i]['page']}  bm25={scores[i]:.2f}\n{chunks[i]['text'][:400]}...")
