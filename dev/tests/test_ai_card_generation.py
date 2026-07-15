"""Tests for template-specific AI card prompts and batching."""

import ai
from ui import cards as cards_ui


def _prompt_input_items(user_prompt: str) -> list[str]:
    payload = user_prompt.split("Input items:\n", 1)[1].split("\n\nOUTPUT CONTRACT", 1)[0]
    return payload.splitlines()


def test_definition_front_prompt_uses_meticulous_contract():
    system_prompt, user_prompt = ai._build_definition_front_prompts("adamant\nflammable")

    assert system_prompt == "You are a meticulous Anki vocabulary card generator."
    assert _prompt_input_items(user_prompt) == ["adamant", "flammable"]
    assert "Every line must contain exactly 6 fields separated by exactly 5 occurrences of |||." in user_prompt
    assert "Fields 2, 5, and 6 must be empty." in user_prompt
    assert "Keep the definition to a maximum of 14 words." in user_prompt
    assert "Include the exact target word or phrase exactly once." in user_prompt
    assert "MANDATORY ANSWERABILITY TEST" in user_prompt
    assert "The target is clearly the best expected answer after clozing." in user_prompt
    assert user_prompt.endswith("- Nothing appears outside the text code block.")


def test_definition_front_ai_requests_use_batches_of_five(monkeypatch):
    calls = []
    progress = []

    monkeypatch.setattr(ai, "get_ai_model", lambda: "test-model")

    def fake_completion(model_name, messages, temperature):
        calls.append((model_name, messages, temperature))
        return {"content": "```text\nresult\n```"}

    monkeypatch.setattr(ai, "_call_ai_chat_completion", fake_completion)
    words = [f"word{index}" for index in range(11)]

    result = ai.process_ai_in_batches(
        words,
        card_template="definition_front",
        progress_callback=lambda current, total: progress.append((current, total)),
    )

    assert result
    assert [_prompt_input_items(call[1][1]["content"]) for call in calls] == [
        words[:5],
        words[5:10],
        words[10:],
    ]
    assert all(call[1][0]["content"] == "You are a meticulous Anki vocabulary card generator." for call in calls)
    assert all(call[2] == 0.4 for call in calls)
    assert progress == [(5, 11), (10, 11), (11, 11)]


def test_definition_front_page_queue_uses_batches_of_five(monkeypatch):
    requested_words = [f"word{index}" for index in range(11)]
    batches = []

    def fake_process(batch, **_kwargs):
        batches.append(list(batch))
        lines = [
            f"{word} ||| ||| n. | test item ||| The label identifies {word} clearly. ||| |||"
            for word in batch
        ]
        return "```text\n" + "\n".join(lines) + "\n```"

    class Status:
        def text(self, _message):
            pass

    class Progress:
        def progress(self, _ratio):
            pass

    monkeypatch.setattr(cards_ui, "process_ai_in_batches", fake_process)

    cards, missing_words = cards_ui._generate_complete_cards_with_queue(
        requested_words,
        example_count=1,
        definition_language="中文",
        translate_examples=False,
        card_template="definition_front",
        content_status=Status(),
        content_progress_bar=Progress(),
    )

    assert batches == [requested_words[:5], requested_words[5:10], requested_words[10:]]
    assert [card["w"] for card in cards] == requested_words
    assert missing_words == []
