"""Tests for preserving multiple examples and their matching audio."""

import os
import sqlite3
import zipfile

import anki_package
from anki_package import (
    _build_cloze_example,
    _completed_audio_card_count,
    _example_texts,
    _render_examples_with_audio,
    generate_anki_package,
)


def test_build_cloze_example_preserves_all_examples():
    source = "She was adamant about leaving.<br>The union remains adamant about the proposal."

    rendered = _build_cloze_example(source, "adamant")

    assert rendered.count("{{c1::adamant::a________}}") == 2
    assert "<br><br>" in rendered
    assert _example_texts(source) == [
        "She was adamant about leaving.",
        "The union remains adamant about the proposal.",
    ]


def test_render_examples_places_each_audio_below_its_example():
    rendered = _render_examples_with_audio(
        ["First <b>example</b>.", "Second <b>example</b>."],
        ["[sound:first.mp3]", "[sound:second.mp3]"],
    )

    assert rendered.count('class="example-audio-pair"') == 2
    assert rendered.count('class="example-audio-control"') == 2
    assert rendered.index("First <b>example</b>.") < rendered.index("[sound:first.mp3]")
    assert rendered.index("[sound:first.mp3]") < rendered.index("Second <b>example</b>.")
    assert rendered.index("Second <b>example</b>.") < rendered.index("[sound:second.mp3]")


def test_audio_progress_counts_only_cards_with_all_requested_audio(tmp_path):
    complete_word = tmp_path / "complete-word.mp3"
    complete_example = tmp_path / "complete-example.mp3"
    partial_word = tmp_path / "partial-word.mp3"
    for path in (complete_word, complete_example, partial_word):
        path.write_bytes(b"audio" * 30)

    prepared_cards = [
        {
            "phrase_audio_path": str(complete_word),
            "example_audio_items": [{"path": str(complete_example)}],
        },
        {
            "phrase_audio_path": str(partial_word),
            "example_audio_items": [{"path": str(tmp_path / "missing-example.mp3")}],
        },
        {
            "phrase_audio_path": "",
            "example_audio_items": [],
        },
    ]

    assert _completed_audio_card_count(prepared_cards) == 2


def test_definition_front_package_and_tts_keep_all_examples(monkeypatch, tmp_path):
    captured_tasks = []
    cache_dir = tmp_path / "tts-cache"
    cache_dir.mkdir()

    def capture_audio_tasks(tasks, concurrency, progress_callback):
        captured_tasks.extend(tasks)

    monkeypatch.setattr(anki_package, "run_async_batch", capture_audio_tasks)
    monkeypatch.setattr(anki_package, "TTS_AUDIO_CACHE_DIR", str(cache_dir))
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
        example_tasks = [task for task in captured_tasks if task["text"] != "adamant"]
        assert len(example_tasks) == 2
        assert [task["text"] for task in example_tasks] == [
            "She was adamant about leaving.",
            "The union remains adamant about the proposal.",
        ]
        assert all(os.path.dirname(task["path"]) == str(cache_dir) for task in captured_tasks)

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
    cache_dir = tmp_path / "tts-cache"
    cache_dir.mkdir()

    def capture_audio_tasks(tasks, concurrency, progress_callback):
        captured_tasks.extend(tasks)
        for task in tasks:
            with open(task["path"], "wb") as audio_file:
                audio_file.write(b"audio" * 30)

    monkeypatch.setattr(anki_package, "run_async_batch", capture_audio_tasks)
    monkeypatch.setattr(anki_package, "TTS_AUDIO_CACHE_DIR", str(cache_dir))
    audio_report = {}
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
        audio_report=audio_report,
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
        assert len(captured_tasks) == 3
        assert captured_tasks[0]["text"] == "adamant"
        assert [task["text"] for task in captured_tasks[1:]] == [
            "She was adamant about staying.",
            "The editor remained adamant about stronger evidence.",
        ]
        audio_html = fields[14]
        first_audio_index = audio_html.index("[sound:")
        second_audio_index = audio_html.index("[sound:", first_audio_index + 1)
        assert audio_html.count('class="example-audio-pair"') == 2
        assert audio_html.count('class="example-audio-control"') == 2
        assert audio_html.count("[sound:") == 2
        assert audio_html.index("She was <b>adamant</b> about staying.") < first_audio_index
        assert first_audio_index < audio_html.index("The editor remained <b>adamant</b>")
        assert audio_html.index("The editor remained <b>adamant</b>") < second_audio_index
        assert "{{#Audio_Example}}" in model_json
        assert "{{^Audio_Example}}" in model_json
        assert all("<b>" not in task["text"] for task in captured_tasks[1:])
        assert audio_report == {"requested": 3, "succeeded": 3, "failed": 0}
    finally:
        if os.path.exists(package_path):
            os.remove(package_path)


def test_front_back_without_headword_still_generates_each_example_audio(monkeypatch, tmp_path):
    captured_tasks = []
    cache_dir = tmp_path / "tts-cache"
    cache_dir.mkdir()

    def capture_audio_tasks(tasks, concurrency, progress_callback):
        captured_tasks.extend(tasks)
        for task in tasks:
            with open(task["path"], "wb") as audio_file:
                audio_file.write(b"audio" * 30)

    monkeypatch.setattr(anki_package, "run_async_batch", capture_audio_tasks)
    monkeypatch.setattr(anki_package, "TTS_AUDIO_CACHE_DIR", str(cache_dir))
    cards = [{
        "w": "",
        "p": "",
        "m": "",
        "e": "What is the capital of France?<br>Which city contains the Eiffel Tower?",
        "ec": "",
        "r": "",
        "front": "What is the capital of France?<br>Which city contains the Eiffel Tower?",
        "back": "Paris answers both questions.",
    }]
    package_path = generate_anki_package(
        cards,
        "headword-free-front-back-test",
        enable_tts=True,
        card_template="front_back",
        tts_mode="word_and_example",
    )

    try:
        database_path = tmp_path / "headword-free-collection.anki2"
        with zipfile.ZipFile(package_path) as package:
            database_path.write_bytes(package.read("collection.anki2"))
        with sqlite3.connect(database_path) as connection:
            fields = connection.execute("SELECT flds FROM notes").fetchone()[0].split(chr(31))

        assert [task["text"] for task in captured_tasks] == [
            "What is the capital of France?",
            "Which city contains the Eiffel Tower?",
        ]
        assert all(os.path.dirname(task["path"]) == str(cache_dir) for task in captured_tasks)
        assert fields[13] == ""
        assert fields[14].count("[sound:") == 2
        assert fields[14].count('class="example-audio-pair"') == 2
    finally:
        if os.path.exists(package_path):
            os.remove(package_path)


def test_package_retry_reuses_completed_tts_cache(monkeypatch, tmp_path):
    cache_dir = tmp_path / "tts-cache"
    cache_dir.mkdir()
    batches = []

    def first_pass(tasks, concurrency, progress_callback):
        batches.append(list(tasks))
        for task in tasks:
            with open(task["path"], "wb") as audio_file:
                audio_file.write(b"audio" * 30)

    monkeypatch.setattr(anki_package, "TTS_AUDIO_CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(anki_package, "run_async_batch", first_pass)
    cards = [{
        "w": "adamant",
        "p": "",
        "m": "adj. | 坚定不移的 | refusing to change an opinion or decision",
        "e": "She was adamant about leaving.",
        "ec": "",
        "r": "",
    }]

    first_package = generate_anki_package(
        cards,
        "cache-first-pass",
        enable_tts=True,
        tts_mode="word_and_example",
    )
    try:
        first_paths = [task["path"] for task in batches[0]]
        assert len(first_paths) == 2
        assert all(os.path.isfile(path) for path in first_paths)
    finally:
        if os.path.exists(first_package):
            os.remove(first_package)

    def retry_pass(tasks, concurrency, progress_callback):
        batches.append(list(tasks))
        assert all(os.path.isfile(task["path"]) for task in tasks)

    monkeypatch.setattr(anki_package, "run_async_batch", retry_pass)
    retry_package = generate_anki_package(
        cards,
        "cache-retry-pass",
        enable_tts=True,
        tts_mode="word_and_example",
    )
    try:
        assert [task["path"] for task in batches[1]] == first_paths
        with zipfile.ZipFile(retry_package) as package:
            media_members = [name for name in package.namelist() if name.isdigit()]
        assert len(media_members) == 2
    finally:
        if os.path.exists(retry_package):
            os.remove(retry_package)
