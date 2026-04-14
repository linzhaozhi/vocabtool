# Parse AI-generated text into structured Anki card data.

import re
from typing import Dict, List


def split_example_translation(example_field: str) -> tuple[str, str]:
    """Split 'English example (中文翻译)' into separate fields when possible."""
    example_field = example_field.strip()
    match = re.match(
        r"^(?P<example>.*?)[\(\（](?P<translation>[^()（）]*[\u4e00-\u9fff][^()（）]*)[\)\）]\s*$",
        example_field
    )
    if not match:
        return example_field, ""

    example = match.group("example").strip()
    translation = match.group("translation").strip()
    if not example or not re.search(r"[A-Za-z]", example):
        return example_field, ""
    return example, translation


def parse_anki_data(raw_text: str) -> List[Dict[str, str]]:
    """Parse AI-generated text into structured Anki card data."""
    parsed_cards = []
    text = raw_text.strip()

    code_blocks = re.findall(r'```(?:text|csv)?\s*(.*?)\s*```', text, re.DOTALL)

    if code_blocks:
        text = "\n".join(code_blocks)
    else:
        text = re.sub(r'^```.*$', '', text, flags=re.MULTILINE)

    lines = text.split('\n')
    seen_phrases = set()

    for line in lines:
        line = line.strip()
        if not line or "|||" not in line:
            continue

        parts = [part.strip() for part in line.split("|||")]
        if len(parts) < 2:
            continue

        phrase = parts[0]
        meaning = parts[1]
        example = parts[2] if len(parts) > 2 else ""
        example_translation = ""
        etymology = ""

        if len(parts) >= 5:
            example_translation = parts[3]
            etymology = " ||| ".join(parts[4:]).strip()
        elif len(parts) == 4:
            example, example_translation = split_example_translation(example)
            etymology = parts[3]
        else:
            example, example_translation = split_example_translation(example)

        if not phrase or not meaning:
            continue

        if phrase.lower() in seen_phrases:
            continue
        seen_phrases.add(phrase.lower())

        parsed_cards.append({
            'w': phrase,
            'm': meaning,
            'e': example,
            'ec': example_translation,
            'r': etymology
        })

    return parsed_cards
