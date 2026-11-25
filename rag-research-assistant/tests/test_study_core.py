import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pytest
from study_core import (sample_evenly, batch_texts, extract_json, validate_flashcards, validate_quiz, validate_terms)


def test_sample_evenly_covers_range():
    out = sample_evenly(list(range(100)), 5)
    assert len(out) == 5 and out[0] == 0 and out[-1] >= 80


def test_sample_small_list():
    assert sample_evenly([1, 2], 5) == [1, 2] and sample_evenly([], 3) == []


def test_batch_texts():
    b = batch_texts(["a" * 600] * 5, max_chars=1000)
    assert len(b) == 5 and all("a" in x for x in b)


def test_extract_json_handles_fences_and_chatter():
    assert extract_json('Sure!\n```json\n[{"q":"1","a":"2"}]\n```\nHope it helps') == [{"q": "1", "a": "2"}]


def test_extract_json_failure():
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_validators_drop_bad_items():
    assert len(validate_flashcards([{"q": "x", "a": "y"}, {"q": "", "a": "z"}, "bad"])) == 1
    good = {"question": "Q?", "options": ["a", "b", "c", "d"], "answerIndex": 2, "explanation": "e"}
    bad = {"question": "Q?", "options": ["a", "b"], "answerIndex": 5}
    assert len(validate_quiz([good, bad])) == 1
    assert len(validate_terms([{"term": "t", "definition": "d"}, {"term": "x"}])) == 1
