import os
import sqlite3
import zipfile

import pytest

from card_file_import import (
    CardFileParseError,
    cards_to_display_rows,
    display_rows_to_cards,
    display_rows_to_front_back_cards,
    front_back_cards_to_display_rows,
    parse_card_file,
    validate_imported_cards,
)


def test_parse_csv_with_separate_meaning_columns():
    raw = (
        "word,phonetic,part_of_speech,chinese_meaning,english_definition,example,"
        "example_translation,etymology\n"
        'apple,/ˈæpəl/,noun,苹果,"a round fruit","She ate an apple.",她吃了一个苹果。,古英语 æppel\n'
    )

    result = parse_card_file("cards.csv", raw.encode("utf-8"))

    assert result.format_name == "CSV"
    assert len(result.cards) == 1
    assert result.cards[0] == {
        "w": "apple",
        "p": "/ˈæpəl/",
        "m": "noun | 苹果 | a round fruit",
        "e": "She ate an apple.",
        "ec": "她吃了一个苹果。",
        "r": "古英语 æppel",
    }


def test_parse_csv_with_chinese_headers_and_bom():
    raw = "\ufeff单词,音标,释义,英文例句,例句翻译,词源\nram,/ræm/,公羊,The ram moved.,公羊移动了。,古英语\n"

    result = parse_card_file("中文卡片.csv", raw.encode("utf-8"))

    assert len(result.cards) == 1
    assert result.cards[0]["w"] == "ram"
    assert result.cards[0]["m"] == "公羊"
    assert result.cards[0]["e"] == "The ram moved."


def test_parse_headerless_csv_uses_six_field_order():
    raw = "wreck,/rek/,破坏,The storm wrecked it.,暴风雨毁了它。,来自古英语\n"

    result = parse_card_file("cards.csv", raw.encode("utf-8"))

    assert result.cards[0]["w"] == "wreck"
    assert result.cards[0]["p"] == "/rek/"
    assert result.cards[0]["r"] == "来自古英语"


def test_parse_triple_pipe_txt_inside_code_fence():
    raw = """```text
word ||| phonetic ||| meaning ||| example ||| example_translation ||| etymology
hectic ||| /ˈhektɪk/ ||| 忙乱的 ||| It was a hectic day. ||| 那是忙乱的一天。 ||| hect- + -ic
```"""

    result = parse_card_file("cards.txt", raw.encode("utf-8"))

    assert result.format_name == "分隔符 TXT"
    assert len(result.cards) == 1
    assert result.cards[0]["w"] == "hectic"
    assert result.cards[0]["ec"] == "那是忙乱的一天。"


def test_parse_markdown_table():
    raw = """
| Word | Meaning | Example | Etymology |
| --- | --- | --- | --- |
| altruism | 利他主义 | Altruism can inspire generosity. | alter + -ism |
"""

    result = parse_card_file("cards.txt", raw.encode("utf-8"))

    assert result.format_name == "Markdown 表格"
    assert len(result.cards) == 1
    assert result.cards[0]["w"] == "altruism"
    assert result.cards[0]["r"] == "alter + -ism"


def test_parse_labeled_ai_text_blocks():
    raw = """
Word: ram
Meaning: 公羊
Example: The ram stood by the gate.
Example translation: 那只公羊站在门边。
Etymology: 来自古英语

Word: wreck
Meaning: 破坏
Example: The wave wrecked the boat.
"""

    result = parse_card_file("cards.txt", raw.encode("utf-8"))

    assert result.format_name == "字段式 TXT"
    assert [card["w"] for card in result.cards] == ["ram", "wreck"]
    assert result.cards[0]["ec"] == "那只公羊站在门边。"


def test_parse_labeled_blocks_with_blank_lines_between_fields():
    raw = """
Word: ram

Meaning: 公羊

Example: The ram stood by the gate.

Word: wreck

Meaning: 破坏

Example: The wave wrecked the boat.
"""

    result = parse_card_file("cards.txt", raw.encode("utf-8"))

    assert [card["w"] for card in result.cards] == ["ram", "wreck"]
    assert result.cards[0]["e"] == "The ram stood by the gate."


def test_parse_tab_delimited_txt_with_alias_headers():
    raw = "Word/Phrase\tChinese Translation\tSentence EN\tSentence CN\nram\t公羊\tThe ram moved.\t公羊移动了。\n"

    result = parse_card_file("cards.txt", raw.encode("utf-8"))

    assert result.format_name == "制表符 TXT"
    assert result.cards[0]["w"] == "ram"
    assert result.cards[0]["m"] == "公羊"
    assert result.cards[0]["ec"] == "公羊移动了。"


def test_parse_rich_front_back_vocabulary_txt():
    raw = (
        "Front\tBack\n"
        "Despite repeated requests, the editor remained <b>adamant</b> that the article needed stronger evidence."
        "<br>She was <b>adamant</b> about keeping the public park open to local residents.\t"
        "<b>adamant</b> · adjective<br>firmly unwilling to change a decision or opinion"
        "<br><br><b>Pattern:</b> be adamant that…\n"
        "The researcher was dismissed after she <b>falsified</b> data in several reports."
        "<br>Anyone who <b>falsifies</b> official records may face criminal charges.\t"
        "<b>falsify</b> · verb<br>to alter or invent information in order to deceive\n"
    )

    result = parse_card_file("front_back_cards.txt", raw.encode("utf-8"))

    assert result.format_name == "制表符 TXT"
    assert result.warnings == []
    assert result.card_template == "front_back"
    assert result.cards == [
        {
            "w": "adamant",
            "p": "",
            "m": "adjective | firmly unwilling to change a decision or opinion",
            "e": (
                "Despite repeated requests, the editor remained adamant that the article needed stronger evidence."
                "<br>She was adamant about keeping the public park open to local residents."
            ),
            "ec": "",
            "r": "",
            "front": (
                "Despite repeated requests, the editor remained <b>adamant</b> that the article needed stronger evidence."
                "<br>She was <b>adamant</b> about keeping the public park open to local residents."
            ),
            "back": (
                "<b>adamant</b> · adjective<br>firmly unwilling to change a decision or opinion"
                "<br><br><b>Pattern:</b> be adamant that…"
            ),
        },
        {
            "w": "falsify",
            "p": "",
            "m": "verb | to alter or invent information in order to deceive",
            "e": (
                "The researcher was dismissed after she falsified data in several reports."
                "<br>Anyone who falsifies official records may face criminal charges."
            ),
            "ec": "",
            "r": "",
            "front": (
                "The researcher was dismissed after she <b>falsified</b> data in several reports."
                "<br>Anyone who <b>falsifies</b> official records may face criminal charges."
            ),
            "back": "<b>falsify</b> · verb<br>to alter or invent information in order to deceive",
        },
    ]
    assert validate_imported_cards(result.cards, require_examples=True) == []


def test_plain_front_back_txt_keeps_existing_two_column_behavior():
    raw = "Front\tBack\napple\t苹果\n"

    result = parse_card_file("plain_front_back.txt", raw.encode("utf-8"))

    assert result.cards[0]["w"] == "apple"
    assert result.cards[0]["m"] == "苹果"
    assert result.card_template == "word_front"


def test_front_back_display_rows_preserve_native_sides():
    raw = (
        "Front\tBack\n"
        "The team kept its <b>morale</b> high.<br>Good news raised <b>morale</b>.\t"
        "<b>morale</b> · noun<br>the confidence and enthusiasm of a group"
    )
    result = parse_card_file("front_back.txt", raw.encode("utf-8"))

    rows = front_back_cards_to_display_rows(result.cards)
    restored = display_rows_to_front_back_cards(rows)

    assert restored == result.cards
    assert "{{c1::" not in restored[0]["front"]


def test_front_back_html_drops_executable_markup():
    raw = (
        "Front\tBack\n"
        "A <b>safe</b> sentence.<script>alert('bad')</script>\t"
        "<b>safe</b> · adjective<br>not likely to cause harm<iframe>bad</iframe>\n"
    )

    result = parse_card_file("safe_front_back.txt", raw.encode("utf-8"))

    assert result.cards[0]["front"] == "A <b>safe</b> sentence."
    assert result.cards[0]["back"] == "<b>safe</b> · adjective<br>not likely to cause harm"


def test_rich_front_back_accepts_proper_noun():
    raw = (
        "Front\tBack\n"
        "Lawmakers returned to the <b>Capitol</b> for an emergency vote."
        "<br>Visitors can tour the <b>Capitol</b> when Congress is not in session.\t"
        "<b>Capitol</b> · proper noun<br>the building where the U.S. Congress meets<br>美国国会大厦\n"
    )

    result = parse_card_file("proper_noun_front_back.txt", raw.encode("utf-8"))

    assert result.card_template == "front_back"
    assert result.cards[0]["w"] == "Capitol"
    assert result.cards[0]["m"] == "proper noun | the building where the U.S. Congress meets"
    assert result.cards[0]["e"].count("<br>") == 1
    assert validate_imported_cards(result.cards, require_examples=True) == []


def test_parse_anki_cloze_txt_export():
    raw = (
        "#separator:Tab\n"
        "#html:false\n"
        "#columns:Text\tWord\tPartOfSpeech\tDefinition\tChinese\tTags\n"
        "#tags column:6\n"
        "She remained {{c1::adamant::a_______}} about the decision.\tadamant\tadj.\t"
        "refusing to change an opinion or decision\t坚定不移的\tcore_vocab batch_01\n"
        "I {{c1::tune out::t___ o__}} during dull meetings.\ttune out\tphrase\t"
        "stop paying attention to something\t不再理会\tcore_vocab batch_01\n"
    )

    result = parse_card_file("anki_export.txt", raw.encode("utf-8"))

    assert result.format_name == "制表符 TXT"
    assert result.card_template == "definition_front"
    assert result.warnings == []
    assert len(result.cards) == 2
    assert result.cards[0] == {
        "w": "adamant",
        "p": "",
        "m": "adj. | 坚定不移的 | refusing to change an opinion or decision",
        "e": "She remained adamant about the decision.",
        "ec": "",
        "r": "",
    }
    assert result.cards[1]["e"] == "I tune out during dull meetings."
    assert validate_imported_cards(result.cards, require_examples=True) == []


def test_parse_anki_cloze_txt_export_with_numbered_examples():
    raw = (
        "#separator:Tab\n"
        "#html:false\n"
        "#columns:Text1\tText2\tWord\tPartOfSpeech\tDefinition\tChinese\tTags\n"
        "#tags column:7\n"
        "She was {{c1::adamant::a______}} about leaving.\t"
        "The union remains {{c1::adamant::a______}} about the proposal.\t"
        "adamant\tadj.\trefusing to change an opinion or decision\t坚定不移的\tcore_vocab\n"
    )

    result = parse_card_file("anki_double_examples.txt", raw.encode("utf-8"))

    assert result.warnings == []
    assert len(result.cards) == 1
    assert result.cards[0]["e"] == (
        "She was adamant about leaving.<br>"
        "The union remains adamant about the proposal."
    )
    assert validate_imported_cards(result.cards, require_examples=True) == []


def test_parse_json_stored_in_txt():
    raw = '[{"word":"apple","meaning":"苹果","examples":["One apple.","Two apples."]}]'

    result = parse_card_file("cards.txt", raw.encode("utf-8"))

    assert result.format_name == "JSON 文本"
    assert result.cards[0]["e"] == "One apple.<br>Two apples."


def test_display_rows_round_trip():
    cards = [{"w": "apple", "p": "", "m": "苹果", "e": "An apple.", "ec": "", "r": ""}]

    rows = cards_to_display_rows(cards)
    restored = display_rows_to_cards(rows)

    assert restored == cards


def test_validation_requires_structure_but_not_target_word_in_example():
    cards = [
        {"w": "apple", "p": "", "m": "苹果", "e": "He left early.", "ec": "", "r": ""},
        {"w": "Apple", "p": "", "m": "苹果", "e": "Another sentence.", "ec": "", "r": ""},
    ]

    issues = validate_imported_cards(cards, require_examples=True)

    assert len(issues) == 1
    assert "重复" in issues[0]
    assert not any("目标词" in issue for issue in issues)


def test_validation_requires_example_only_when_requested():
    cards = [{"w": "apple", "p": "", "m": "苹果", "e": "", "ec": "", "r": ""}]

    assert validate_imported_cards(cards, require_examples=False) == []
    assert "缺少英文例句" in validate_imported_cards(cards, require_examples=True)[0]


def test_rejects_empty_or_unsupported_files():
    with pytest.raises(CardFileParseError):
        parse_card_file("cards.csv", b"")
    with pytest.raises(CardFileParseError):
        parse_card_file("cards.xlsx", b"word,meaning\nhello,hi")


@pytest.mark.parametrize("card_template", ["word_front", "example_front", "definition_front"])
def test_package_contains_exactly_one_note_per_imported_row(tmp_path, card_template):
    from anki_package import generate_anki_package

    cards = [
        {
            "w": f"word{index}",
            "p": "",
            "m": "noun | 含义 | an English definition",
            "e": f"This is example sentence {index}.",
            "ec": "",
            "r": "",
        }
        for index in range(12)
    ]
    package_path = generate_anki_package(
        cards,
        f"import-count-{card_template}",
        enable_tts=False,
        card_template=card_template,
        tts_mode="none",
    )

    try:
        database_path = tmp_path / "collection.anki2"
        with zipfile.ZipFile(package_path) as package:
            database_path.write_bytes(package.read("collection.anki2"))
        with sqlite3.connect(database_path) as connection:
            note_count = connection.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        assert note_count == len(cards)
    finally:
        if os.path.exists(package_path):
            os.remove(package_path)
