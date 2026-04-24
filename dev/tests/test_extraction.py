# Tests for extraction.clean_anki_field and parse_anki_txt_export.

from io import BytesIO

import pytest

from extraction import (
    clean_anki_field,
    extract_text_from_url,
    get_extraction_error_message,
    is_extraction_error_text,
    make_extraction_error,
    parse_anki_txt_export,
    validate_article_url,
)


def test_clean_anki_field_plain():
    assert clean_anki_field("hello") == "hello"
    assert clean_anki_field("  word  ") == "word"


def test_clean_anki_field_cloze():
    assert clean_anki_field("{{c1::answer}}") == "answer"
    assert clean_anki_field("{{c2::word::hint}}") == "word"


def test_clean_anki_field_html():
    # Tags removed and result stripped
    assert clean_anki_field("<b>bold</b>") == "bold"
    assert clean_anki_field("<div>text</div>") == "text"


def test_clean_anki_field_sound():
    assert clean_anki_field("[sound:file.mp3]") == ""
    assert clean_anki_field("word [sound:a.mp3]") == "word"


def test_clean_anki_field_unescape():
    assert "&" in clean_anki_field("a & b")
    # After unescape we get "a & b" (single char for &)


def test_parse_anki_txt_export_simple_tsv():
    content = b"word1\nword2\nword3"
    f = BytesIO(content)
    f.name = "export.txt"
    result = parse_anki_txt_export(f)
    lines = result.strip().split("\n")
    assert len(lines) == 3
    assert "word1" in lines and "word2" in lines and "word3" in lines


def test_parse_anki_txt_export_skips_short():
    content = b"a\nab\nabc"
    f = BytesIO(content)
    f.name = "export.txt"
    result = parse_anki_txt_export(f)
    lines = [x for x in result.strip().split("\n") if x]
    assert "a" not in lines
    assert "ab" in lines
    assert "abc" in lines


def test_parse_anki_txt_export_skips_comments():
    content = b"# comment\nword1\nword2"
    f = BytesIO(content)
    f.name = "export.txt"
    result = parse_anki_txt_export(f)
    assert "comment" not in result
    assert "word1" in result


def test_extraction_error_marker_roundtrip():
    result = make_extraction_error("读取失败")
    assert is_extraction_error_text(result)
    assert get_extraction_error_message(result) == "读取失败"


@pytest.mark.parametrize(
    "url",
    [
        "not-a-url",
        "ftp://example.com/file.txt",
        "http://localhost:8501",
        "http://127.0.0.1:8501",
        "http://192.168.1.10/article",
    ],
)
def test_validate_article_url_rejects_unsafe_urls(url):
    is_valid, _ = validate_article_url(url)
    assert is_valid is False


def test_extract_text_from_url_rejects_before_network():
    result = extract_text_from_url("http://127.0.0.1:8501")
    assert is_extraction_error_text(result)
    assert "URL" in get_extraction_error_message(result) or "IP" in get_extraction_error_message(result)
