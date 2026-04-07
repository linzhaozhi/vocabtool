# Tests for vocab.is_valid_word and analyze_logic (with mocked resources).

import pytest

# Set up minimal vocab dict and mock NLP so tests run without Streamlit/NLTK
import resources
resources.VOCAB_DICT = {"run": 100, "running": 100, "hello": 500, "known": 50}
resources.FULL_DF = None


class MockLemminflect:
    @staticmethod
    def getLemma(word, upos="VERB"):
        # Simple mock: return [word] for common forms
        if word == "running":
            return ["run"]
        return [word]


@pytest.fixture(autouse=True)
def mock_nlp(monkeypatch):
    def fake_load_nlp():
        return (None, MockLemminflect())
    monkeypatch.setattr("vocab.load_nlp_resources", fake_load_nlp)


from vocab import is_valid_word, analyze_logic


def test_is_valid_word_length():
    assert is_valid_word("ab") is True
    assert is_valid_word("a") is False
    assert is_valid_word("") is False
    long_word = "a" * 26
    assert is_valid_word(long_word) is False
    # 25 varied chars (no 3+ repeat) is valid
    assert is_valid_word("abcdefghijklmnopqrstuvwxy"[:25]) is True


def test_is_valid_word_vowel():
    assert is_valid_word("abc") is True
    assert is_valid_word("bcdfg") is False  # no vowel
    assert is_valid_word("fly") is True   # y as vowel


def test_is_valid_word_repeated():
    assert is_valid_word("hello") is True
    assert is_valid_word("heeello") is False  # 3+ same char
    assert is_valid_word("success") is True   # cc is 2


def test_is_valid_word_acceptable():
    assert is_valid_word("word") is True
    assert is_valid_word("schedule") is True
    assert is_valid_word("don't") is True


def test_analyze_logic_uses_vocab_rank():
    text = "run running hello known"
    candidates, raw_count, stats = analyze_logic(text, current_level=200, target_level=1000, include_unknown=False)
    # known=50 < 200 (known), run/running=100 < 200 (known), hello=500 in range
    assert raw_count == 4
    words_in_range = [w for w, r in candidates]
    assert "hello" in words_in_range
    # run/running lemmatized might both be run; known is below current_level so not in target range
    assert "known" not in words_in_range or stats["coverage"] > 0


def test_analyze_logic_returns_stats():
    text = "run run run"
    _, raw_count, stats = analyze_logic(text, current_level=200, target_level=1000, include_unknown=False)
    assert raw_count == 3
    assert "coverage" in stats
    assert "target_density" in stats
    assert 0 <= stats["coverage"] <= 1
    assert 0 <= stats["target_density"] <= 1


def test_analyze_logic_sort_by_rank():
    text = "hello run known"
    candidates, _, _ = analyze_logic(text, current_level=10, target_level=2000, include_unknown=False)
    ranks = [r for _, r in candidates]
    assert ranks == sorted(ranks)
