import os, sys, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from rag_core import (chunk_page, chunk_pages, text_to_pages, dot, tokenize, bm25_scores, rrf, hybrid_search,
                      confidence_label, build_user_prompt, build_rewrite_prompt, normalize_history, system_prompt, NOT_FOUND)


def unit(v):
    n = math.sqrt(sum(x * x for x in v)); return [x / n for x in v]


def test_chunk_empty():
    assert chunk_page("   ") == []


def test_chunk_size_and_overlap():
    chunks = chunk_page("Sentence number one is here. " * 100, size=300, overlap=60)
    assert len(chunks) > 3 and all(len(c) <= 300 for c in chunks)


def test_page_numbers():
    assert [c["page"] for c in chunk_pages(["alpha beta", "", "gamma delta"])] == [1, 3]


def test_text_to_pages_sections():
    pages = text_to_pages(("para " * 200 + "\n\n") * 6, size=1500)
    assert len(pages) > 1


def test_tokenize_drops_stopwords():
    assert tokenize("What is the Capital of France?") == ["capital", "france"]


def test_bm25_prefers_matching_doc():
    docs = [tokenize("photosynthesis converts light energy"), tokenize("the stock market fell sharply")]
    s = bm25_scores("how does photosynthesis work", docs)
    assert s[0] > s[1] == 0


def test_rrf_combines_rankings():
    fused = rrf([[2, 1, 0], [2, 0, 1]])
    assert max(fused, key=fused.get) == 2


def test_hybrid_keyword_rescues_weak_vector():
    items = [
        {"text": "Gradient descent minimises the loss", "embedding": unit([1, 0, 0]), "n": "a"},
        {"text": "Backpropagation computes gradients", "embedding": unit([0, 1, 0]), "n": "b"},
        {"text": "Unrelated cooking recipe", "embedding": unit([0, 0, 1]), "n": "c"},
    ]
    # vector points at 'a', but the keyword 'backpropagation' only appears in 'b'
    res = hybrid_search("backpropagation", unit([1, 0.05, 0]), items, k=2)
    names = [r["item"]["n"] for r in res]
    assert "a" in names and "b" in names and "c" not in names


def test_hybrid_mmr_avoids_duplicates():
    dup = unit([1, 0.01, 0])
    items = [{"text": "alpha topic", "embedding": dup, "n": 1}, {"text": "alpha topic", "embedding": dup, "n": 2},
             {"text": "alpha other aspect", "embedding": unit([0.8, 0.6, 0]), "n": 3}]
    res = hybrid_search("alpha", unit([1, 0.1, 0]), items, k=2, mmr_lambda=0.5)
    assert {r["item"]["n"] for r in res} != {1, 2}


def test_hybrid_nothing_relevant():
    items = [{"text": "cats", "embedding": unit([1, 0]), "n": 1}]
    assert hybrid_search("quantum", unit([0, 1]), items) == []


def test_confidence_labels():
    assert [confidence_label(x) for x in (0.7, 0.4, 0.2)] == ["high", "medium", "low"]


def test_prompt_contains_citation_info():
    p = build_user_prompt("What?", [{"filename": "x.pdf", "page": 4, "text": "hello"}])
    assert "[1]" in p and "x.pdf" in p and "page 4" in p


def test_system_prompt_guards():
    sp = system_prompt("concise")
    assert NOT_FOUND in sp and "untrusted" in sp and "3 sentences" in sp


def test_normalize_history():
    msgs = [{"role": "assistant", "text": "x"}, {"role": "user", "text": "q1"}, {"role": "assistant", "text": "a1"},
            {"role": "user", "text": "q2"}]
    out = normalize_history(msgs)
    assert [m["role"] for m in out] == ["user", "assistant"]


def test_rewrite_prompt():
    p = build_rewrite_prompt([{"role": "user", "text": "What is CNN?"}, {"role": "assistant", "text": "A network"}], "its layers?")
    assert "its layers?" in p and "CNN" in p
