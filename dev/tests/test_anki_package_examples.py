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
