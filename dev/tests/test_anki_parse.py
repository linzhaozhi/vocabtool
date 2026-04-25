# Tests for anki_parse.parse_anki_data.

import pytest

from anki_parse import parse_anki_data


def test_parse_anki_data_empty():
    assert parse_anki_data("") == []
    assert parse_anki_data("   \n  ") == []


def test_parse_anki_data_single_line():
    raw = "hello ||| 你好 ||| Hello world. ||| 词源"
    result = parse_anki_data(raw)
    assert len(result) == 1
    assert result[0]["w"] == "hello"
    assert result[0]["m"] == "你好"
    assert result[0]["e"] == "Hello world."
    assert result[0]["ec"] == ""
    assert result[0]["r"] == "词源"


def test_parse_anki_data_two_fields():
    raw = "word ||| meaning only"
    result = parse_anki_data(raw)
    assert len(result) == 1
    assert result[0]["w"] == "word"
    assert result[0]["m"] == "meaning only"
    assert result[0]["e"] == ""
    assert result[0]["ec"] == ""
    assert result[0]["r"] == ""


def test_parse_anki_data_code_block():
    raw = """Some text before
```text
hectic ||| 忙乱的 ||| She has a hectic day. ||| hect- + -ic
altruism ||| 利他 ||| Motivated by altruism. ||| alter + -ism
```
After."""
    result = parse_anki_data(raw)
    assert len(result) == 2
    assert result[0]["w"] == "hectic"
    assert result[0]["m"] == "忙乱的"
    assert result[1]["w"] == "altruism"
    assert result[1]["m"] == "利他"


def test_parse_anki_data_deduplicates():
    raw = """word ||| meaning ||| ex ||| ety
word ||| other meaning ||| ex2 ||| ety2"""
    result = parse_anki_data(raw)
    assert len(result) == 1
    assert result[0]["m"] == "meaning"


def test_parse_anki_data_skips_invalid():
    raw = """ ||| meaning ||| ex ||| ety
word |||  ||| ex ||| ety
valid ||| ok ||| ex ||| ety"""
    result = parse_anki_data(raw)
    assert len(result) == 1
    assert result[0]["w"] == "valid"


def test_parse_anki_data_card_shape():
    raw = "phrase ||| def ||| example ||| etymology"
    result = parse_anki_data(raw)
    assert len(result) == 1
    card = result[0]
    assert set(card.keys()) == {"w", "p", "m", "e", "ec", "r"}
    assert card["w"] == "phrase"
    assert card["p"] == ""
    assert card["m"] == "def"
    assert card["e"] == "example"
    assert card["ec"] == ""
    assert card["r"] == "etymology"


def test_parse_anki_data_five_fields_with_translation():
    raw = "phrase ||| 定义 ||| This is an example. ||| 这是一个例句。 ||| 词源"
    result = parse_anki_data(raw)
    assert len(result) == 1
    assert result[0]["e"] == "This is an example."
    assert result[0]["ec"] == "这是一个例句。"
    assert result[0]["r"] == "词源"


def test_parse_anki_data_extracts_inline_example_translation():
    raw = "phrase ||| 定义 ||| This is an example. (这是一个例句。) ||| 词源"
    result = parse_anki_data(raw)
    assert len(result) == 1
    assert result[0]["e"] == "This is an example."
    assert result[0]["ec"] == "这是一个例句。"


def test_parse_anki_data_six_fields_with_phonetics():
    raw = (
        "hectic ||| 美 /ˈhektɪk/；英 /ˈhektɪk/ ||| 忙乱的 ||| "
        "She has a hectic day.<br>My week is hectic. ||| "
        "她今天很忙乱。<br>我的一周很忙乱。 ||| hect- + -ic"
    )
    result = parse_anki_data(raw)
    assert len(result) == 1
    assert result[0]["p"] == "美 /ˈhektɪk/；英 /ˈhektɪk/"
    assert result[0]["e"] == "She has a hectic day.<br>My week is hectic."
    assert result[0]["ec"] == "她今天很忙乱。<br>我的一周很忙乱。"


def test_parse_anki_data_supports_three_examples_without_translation():
    raw = (
        "word ||| 美 /wɜːrd/；英 /wɜːd/ ||| a unit of language ||| "
        "One word is enough.<br>This word is common.<br>I wrote the word. |||  ||| 来自古英语 word"
    )
    result = parse_anki_data(raw)
    assert len(result) == 1
    assert result[0]["m"] == "a unit of language"
    assert result[0]["e"].count("<br>") == 2
    assert result[0]["ec"] == ""
