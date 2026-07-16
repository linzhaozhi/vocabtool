"""Tests for preserving multiple examples in cloze cards."""

import os
import sqlite3
import zipfile

import anki_package
from anki_package import _build_cloze_example, _example_texts, generate_anki_package


def test_build_cloze_example_preserves_all_examples():
    source = "She was adamant about leaving.<br>The union remains adamant about the proposal."

    rendered = _build_cloze_example(source, "adamant")

    assert rendered.count("{{c1::adamant::a________}}") == 2
    assert "<br><br>" in rendered
    assert _example_texts(source) == [
        "She was adamant about leaving.",
        "The union remains adamant about the proposal.",
    ]


def test_definition_front_package_and_tts_keep_all_examples(monkeypatch, tmp_path):
    captured_tasks = []

    def capture_audio_tasks(tasks, concurrency, progress_callback):
        captured_tasks.extend(tasks)

    monkeypatch.setattr(anki_package, "run_async_batch", capture_audio_tasks)
    cards = [{
        "w": "adamant",
        "p": "",
        "m": "adj. | 坚定不移的 | refusing to change an opinion or decision",
        "e": "She was adamant about leaving.<br>The union remains adamant about the proposal.",
        "ec": "",
        "r": "",
    }]
    package_path = generate_anki_package(
        cards,
        "double-example-test",
        enable_tts=True,
        card_template="definition_front",
        tts_mode="word_and_example",
    )

    try:
        example_tasks = [task for task in captured_tasks if task["path"].endswith("_e.mp3")]
        assert len(example_tasks) == 1
        assert "She was adamant about leaving." in example_tasks[0]["text"]
        assert "The union remains adamant about the proposal." in example_tasks[0]["text"]

        database_path = tmp_path / "collection.anki2"
        with zipfile.ZipFile(package_path) as package:
            database_path.write_bytes(package.read("collection.anki2"))
        with sqlite3.connect(database_path) as connection:
            fields = connection.execute("SELECT flds FROM notes").fetchone()[0].split(chr(31))

        assert fields[11].count("{{c1::adamant::") == 2
        assert fields[12].count("<br><br>") == 1
    finally:
        if os.path.exists(package_path):
            os.remove(package_path)


def test_native_front_back_package_preserves_sides_without_cloze(monkeypatch, tmp_path):
    captured_tasks = []

    def capture_audio_tasks(tasks, concurrency, progress_callback):
        captured_tasks.extend(tasks)

    monkeypatch.setattr(anki_package, "run_async_batch", capture_audio_tasks)
    cards = [{
        "w": "adamant",
        "p": "",
        "m": "adjective | firmly unwilling to change a decision or opinion",
        "e": "She was adamant about staying.<br>The editor remained adamant about stronger evidence.",
        "ec": "",
        "r": "",
        "front": (
            "She was <b>adamant</b> about staying.<br>"
            "The editor remained <b>adamant</b> about stronger evidence."
        ),
        "back": (
            "<b>adamant</b> · adjective<br>firmly unwilling to change a decision or opinion"
            "<br><br><b>Pattern:</b> be adamant that…"
        ),
    }]
    package_path = generate_anki_package(
        cards,
        "native-front-back-test",
        enable_tts=True,
        card_template="front_back",
        tts_mode="word_and_example",
    )

    try:
        database_path = tmp_path / "front-back-collection.anki2"
        with zipfile.ZipFile(package_path) as package:
            database_path.write_bytes(package.read("collection.anki2"))
        with sqlite3.connect(database_path) as connection:
            fields = connection.execute("SELECT flds FROM notes").fetchone()[0].split(chr(31))
            model_json = connection.execute("SELECT models FROM col").fetchone()[0]

        assert fields[11] == cards[0]["front"]
        assert fields[12] == cards[0]["back"]
        assert "Pattern:" in fields[12]
        assert "{{c1::" not in fields[11]
        assert '"type": 0' in model_json or '"type":0' in model_json
        assert "Imported Front / Back" in model_json
        assert len(captured_tasks) == 2
        assert captured_tasks[0]["text"] == "adamant"
        assert captured_tasks[1]["text"] == (
            "She was adamant about staying. The editor remained adamant about stronger evidence."
        )
        assert "<b>" not in captured_tasks[1]["text"]
    finally:
        if os.path.exists(package_path):
            os.remove(package_path)
