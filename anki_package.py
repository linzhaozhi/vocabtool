# Anki package (.apkg) generation with optional TTS.

import html
import hashlib
import logging
import os
import random
import shutil
import tempfile
import time
import zlib
import re
from typing import Dict, List, Optional

import constants
from errors import ProgressCallback
from resources import get_genanki
from tts import run_async_batch
from utils import safe_str_clean

logger = logging.getLogger(__name__)
APKG_TEMP_DIR = os.path.join(tempfile.gettempdir(), constants.APKG_TEMP_SUBDIR)
# Keep completed audio outside an individual package's TemporaryDirectory.  If a
# browser reconnects or a TTS request is interrupted, the next click can reuse
# every valid file already made instead of starting the entire deck over.
TTS_AUDIO_CACHE_DIR = os.path.join(APKG_TEMP_DIR, "tts_cache")

CARD_TEMPLATE_MODEL_OFFSETS = {
    "word_front": 21,
    "example_front": 22,
    "definition_front": 23,
    "front_back": 24,
}
INTERNAL_CARD_TEMPLATE_LABELS = {
    "front_back": "Imported Front / Back",
}


def _normalize_card_template(card_template: str) -> str:
    if card_template in CARD_TEMPLATE_MODEL_OFFSETS:
        return card_template
    return constants.DEFAULT_CARD_TEMPLATE


def _audio_file_is_valid(path: str) -> bool:
    if not path:
        return False
    try:
        return os.path.isfile(path) and os.path.getsize(path) > constants.MIN_AUDIO_FILE_SIZE
    except OSError:
        return False


def _cached_tts_audio_path(text: str, voice: str) -> str:
    """Return a stable audio-cache path for an exact voice/text request."""
    request_key = f"v1\0{voice}\0{text}".encode("utf-8")
    digest = hashlib.sha256(request_key).hexdigest()
    return os.path.join(TTS_AUDIO_CACHE_DIR, f"tts_{digest}.mp3")


def _stage_cached_audio(source_path: str, destination_path: str) -> bool:
    """Copy one validated cached file into the package's short-lived media dir."""
    if not _audio_file_is_valid(source_path):
        return False
    try:
        shutil.copyfile(source_path, destination_path)
    except OSError as exc:
        logger.warning("Could not stage cached TTS audio %s: %s", source_path, exc)
        return False
    return _audio_file_is_valid(destination_path)


def _first_letter_hint(phrase: str) -> str:
    tokens = re.findall(r"[A-Za-z]+", phrase)
    return " ".join(
        f'<span class="hint-token"><span class="hint-letter">{html.escape(token[0].lower())}</span><span class="hint-line"></span></span>'
        for token in tokens
        if token
    )


def _plain_first_letter_hint(phrase: str) -> str:
    tokens = re.findall(r"[A-Za-z]+", phrase)
    if not tokens:
        return "________"
    return " ".join(
        f"{token[0].lower()}{'_' * 8}"
        for token in tokens
        if token
    )


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


TARGET_TERM_STOPWORDS = {
    "a", "an", "the", "to", "of", "in", "on", "at", "for", "with",
    "by", "from", "and", "or", "be", "is", "are", "was", "were",
}


def _target_term_variants(phrase: str) -> set[str]:
    """Build simple target variants so the front definition does not leak the answer."""
    variants: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", phrase.lower()):
        if token in TARGET_TERM_STOPWORDS:
            continue
        variants.add(token)
        if token.endswith("y") and len(token) > 2:
            variants.add(f"{token[:-1]}ies")
            variants.add(f"{token[:-1]}ied")
        if token.endswith("e") and len(token) > 2:
            variants.add(f"{token[:-1]}ing")
        if (
            len(token) >= 3
            and token[-1] not in "aeiouwxy"
            and token[-2] in "aeiou"
            and token[-3] not in "aeiou"
        ):
            variants.add(f"{token}{token[-1]}ed")
            variants.add(f"{token}{token[-1]}ing")
        variants.update({
            f"{token}s",
            f"{token}es",
            f"{token}ed",
            f"{token}ing",
        })
    return variants


def _definition_contains_target_term(definition: str, phrase: str) -> bool:
    """Return True when the card-front definition gives away the target term."""
    definition_tokens = set(re.findall(r"[a-z0-9]+", definition.lower()))
    target_tokens = _target_term_variants(phrase)
    return bool(target_tokens and any(token in definition_tokens for token in target_tokens))


def _fallback_definition(part_of_speech: str) -> str:
    normalized = part_of_speech.lower().replace(".", "").strip()
    if normalized in {"verb", "v", "phrasal verb"}:
        return "to do the described action"
    if normalized in {"adjective", "adj"}:
        return "having the described quality"
    if normalized in {"adverb", "adv"}:
        return "in the described manner"
    if normalized in {"phrase", "idiom"}:
        return "a common expression with this meaning"
    return "a person, thing, event, or idea"


def _sanitize_front_definition(definition: str, phrase: str, part_of_speech: str) -> str:
    """Remove answer-leaking target terms from the template-3 front definition."""
    cleaned = _english_only_fragment(definition)
    if not cleaned:
        return _fallback_definition(part_of_speech)

    removed_target = False
    for token in sorted(_target_term_variants(phrase), key=len, reverse=True):
        cleaned, count = re.subn(
            rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )
        removed_target = removed_target or count > 0

    if removed_target:
        cleaned = re.sub(r"\b(?:and|or)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.;:-|")

    if (
        len(re.findall(r"[A-Za-z]+", cleaned)) < 3
        or _contains_cjk(cleaned)
        or _definition_contains_target_term(cleaned, phrase)
    ):
        return _fallback_definition(part_of_speech)
    return cleaned


def _looks_like_part_of_speech(text: str) -> bool:
    normalized = text.strip().lower().replace(".", "")
    abbreviations = {"n", "v", "adj", "adv", "prep", "conj", "pron", "interj", "det", "aux"}
    keywords = {
        "noun", "verb", "adjective", "adverb", "preposition", "conjunction",
        "pronoun", "interjection", "determiner", "article", "auxiliary", "modal",
        "phrase", "idiom", "expression", "abbreviation", "acronym", "initialism",
        "particle", "prefix", "suffix", "numeral", "number", "exclamation",
        "contraction", "symbol", "term",
    }
    english_words = re.findall(r"[a-z]+", normalized)
    chinese_pos = ("名词", "动词", "形容词", "副词", "介词", "连词", "代词", "感叹词", "短语", "习语")
    return (
        normalized in abbreviations
        or bool(english_words and len(english_words) <= 6 and any(word in keywords for word in english_words))
        or any(pos in text for pos in chinese_pos)
    )


def _english_only_fragment(text: str) -> str:
    if not re.search(r"[A-Za-z]", text):
        return ""
    cleaned = re.sub(r"[\u4e00-\u9fff]+", " ", text)
    cleaned = re.sub(r"[（）()；;，,、。]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip(" -|")


def _pick_meaning_parts(parts: list[str]) -> tuple[str, str]:
    chinese_meaning = ""
    english_definition = ""

    for part in parts:
        if not chinese_meaning and _contains_cjk(part):
            chinese_meaning = part
        if not english_definition:
            english_candidate = _english_only_fragment(part)
            if english_candidate and not _looks_like_part_of_speech(english_candidate):
                english_definition = english_candidate

    if not chinese_meaning and parts:
        chinese_meaning = parts[0]

    return chinese_meaning, english_definition


def _split_structured_meaning(meaning: str) -> tuple[str, str, str]:
    parts = [part.strip() for part in meaning.split("|") if part.strip()]
    if len(parts) >= 2 and _looks_like_part_of_speech(parts[0]):
        chinese_meaning, english_definition = _pick_meaning_parts(parts[1:])
        if english_definition and not any(_contains_cjk(part) for part in parts[1:]):
            chinese_meaning = ""
        return parts[0], chinese_meaning, english_definition
    if len(parts) >= 2:
        chinese_meaning, english_definition = _pick_meaning_parts(parts)
        return "", chinese_meaning, english_definition
    return "", meaning, ""


def _format_part_of_speech(part_of_speech: str) -> str:
    normalized = part_of_speech.strip().lower().replace(".", "")
    pos_map = {
        "noun": "n.",
        "n": "n.",
        "proper noun": "proper n.",
        "proper n": "proper n.",
        "determiner": "det.",
        "det": "det.",
        "auxiliary verb": "aux. v.",
        "modal verb": "modal v.",
        "verb": "v.",
        "v": "v.",
        "adjective": "adj.",
        "adj": "adj.",
        "adverb": "adv.",
        "adv": "adv.",
        "preposition": "prep.",
        "prep": "prep.",
        "conjunction": "conj.",
        "conj": "conj.",
        "pronoun": "pron.",
        "pron": "pron.",
        "interjection": "interj.",
        "phrase": "phrase",
        "phrasal verb": "phr. v.",
        "idiom": "idiom",
    }
    return pos_map.get(normalized, part_of_speech.strip())


def _example_texts(example: str) -> list[str]:
    examples = []
    for item in re.split(r"<br\s*/?>", example, flags=re.IGNORECASE):
        cleaned = re.sub(r"<[^>]+>", "", item.strip())
        cleaned = html.unescape(re.sub(r"\s+", " ", cleaned).strip())
        if cleaned:
            examples.append(cleaned)
    return examples


def _completed_audio_card_count(prepared_cards: list[dict]) -> int:
    """Count cards whose requested word and example audio files all exist."""
    completed = 0
    for prepared_card in prepared_cards:
        required_paths = []
        phrase_audio_path = str(prepared_card.get('phrase_audio_path', ''))
        if phrase_audio_path:
            required_paths.append(phrase_audio_path)
        required_paths.extend(
            str(audio_item.get('path', ''))
            for audio_item in prepared_card.get('example_audio_items', [])
            if audio_item.get('path')
        )
        if all(_audio_file_is_valid(path) for path in required_paths):
            completed += 1
    return completed


def _imported_front_example_fragments(imported_front: str, example_texts: list[str]) -> list[str]:
    """Split imported Front HTML into one rich fragment per recognized example."""
    normalized = re.sub(r"<(?:div|p)\b[^>]*>", "", imported_front, flags=re.IGNORECASE)
    normalized = re.sub(r"</(?:div|p)\s*>", "<br>", normalized, flags=re.IGNORECASE)
    fragments = [
        fragment.strip()
        for fragment in re.split(r"(?:\s*<br\s*/?>\s*)+", normalized, flags=re.IGNORECASE)
        if fragment.strip()
    ]
    if len(fragments) == len(example_texts):
        return fragments
    return [html.escape(example) for example in example_texts]


def _render_examples_with_audio(example_fragments: list[str], audio_tags: list[str]) -> str:
    """Place each available audio control directly below its matching example."""
    if not any(audio_tags):
        return ""

    rendered = []
    for index, fragment in enumerate(example_fragments):
        audio_tag = audio_tags[index] if index < len(audio_tags) else ""
        audio_control = (
            f'<div class="example-audio-control">{audio_tag}</div>'
            if audio_tag
            else ""
        )
        rendered.append(
            '<div class="example-audio-pair">'
            f'<div class="example-audio-text">{fragment}</div>'
            f'{audio_control}'
            '</div>'
        )
    return "".join(rendered)


def _first_example_text(example: str) -> str:
    examples = _example_texts(example)
    return examples[0] if examples else ""


def _front_example_text(example: str) -> str:
    return _first_example_text(example)


def _highlight_target_in_example(example: str, phrase: str) -> str:
    first_example = _first_example_text(example)
    if not first_example:
        return html.escape(phrase)
    if not phrase:
        return html.escape(first_example)

    pattern = re.compile(rf"(?<![A-Za-z])({re.escape(phrase)})(?![A-Za-z])", re.IGNORECASE)
    match = pattern.search(first_example)
    if not match:
        return html.escape(first_example)
    return (
        html.escape(first_example[:match.start()])
        + f"<strong>{html.escape(match.group(0))}</strong>"
        + html.escape(first_example[match.end():])
    )


def _build_cloze_example(example: str, phrase: str) -> str:
    example_texts = _example_texts(example)
    if len(example_texts) > 1:
        return "<br><br>".join(_build_cloze_example(item, phrase) for item in example_texts)

    first_example = example_texts[0] if example_texts else ""
    hint = _plain_first_letter_hint(phrase)

    if not first_example:
        return f"{{{{c1::{html.escape(phrase)}::{html.escape(hint)}}}}}"

    def render_all_matches(pattern: re.Pattern[str]) -> str:
        pieces = []
        last_end = 0
        match_count = 0
        for match in pattern.finditer(first_example):
            pieces.append(html.escape(first_example[last_end:match.start()]))
            pieces.append(f"{{{{c1::{html.escape(match.group(0))}::{html.escape(hint)}}}}}")
            last_end = match.end()
            match_count += 1
        if not match_count:
            return ""
        pieces.append(html.escape(first_example[last_end:]))
        return "".join(pieces)

    patterns = [
        re.compile(rf"(?<![A-Za-z0-9])({re.escape(phrase)})(?![A-Za-z0-9])", re.IGNORECASE)
    ]
    target_tokens = re.findall(r"[A-Za-z]+", phrase)
    if len(target_tokens) == 1:
        for variant in sorted(_target_term_variants(phrase), key=len, reverse=True):
            patterns.append(
                re.compile(rf"(?<![A-Za-z0-9])({re.escape(variant)})(?![A-Za-z0-9])", re.IGNORECASE)
            )

    for pattern in patterns:
        clozed = render_all_matches(pattern)
        if clozed:
            return clozed

    return (
        f"{html.escape(first_example)}<br>"
        f'<span class="cloze-fallback">{{{{c1::{html.escape(phrase)}::{html.escape(hint)}}}}}</span>'
    )


def _get_template(card_template: str) -> Dict[str, str]:
    templates = {
        "word_front": {
            "name": "1. Word Front",
            "qfmt": '''
                <div class="phrase">{{Phrase}}</div>
                <div>{{Audio_Phrase}}</div>
            ''',
            "afmt": '''
            {{FrontSide}}
            <hr>
            <div class="meaning">{{Meaning}}</div>
            {{#EnglishDefinition}}<div class="definition">{{EnglishDefinition}}</div>{{/EnglishDefinition}}
            <div class="example">
                <div>{{Example}}</div>
                {{#Example_Translation}}<div class="example-translation">译：{{Example_Translation}}</div>{{/Example_Translation}}
            </div>
            <div>{{Audio_Example}}</div>
            {{#Etymology}}<div class="etymology">🌱 词源: {{Etymology}}</div>{{/Etymology}}
            ''',
        },
        "example_front": {
            "name": "2. Example Front",
            "qfmt": '''
                <div class="front-example">{{ExampleFront}}</div>
                <div>{{Audio_Example}}</div>
            ''',
            "afmt": '''
            {{FrontSide}}
            <hr>
            <div class="phrase">{{Phrase}}</div>
            <div class="meaning">{{Meaning}}</div>
            {{#EnglishDefinition}}<div class="definition">{{EnglishDefinition}}</div>{{/EnglishDefinition}}
            <div class="example">
                <div>{{Example}}</div>
                {{#Example_Translation}}<div class="example-translation">译：{{Example_Translation}}</div>{{/Example_Translation}}
            </div>
            ''',
        },
        "definition_front": {
            "name": "3. Cloze Example Front",
            "qfmt": '''
                <div class="cloze-front">{{cloze:ExampleCloze}}</div>
            ''',
            "afmt": '''
            <div class="cloze-back">
                <div class="cloze-back-head">
                    <div class="cloze-back-word">{{Phrase}}</div>
                    {{#Audio_Phrase}}<div class="cloze-audio">{{Audio_Phrase}}</div>{{/Audio_Phrase}}
                </div>
                {{#EnglishDefinition}}<div class="cloze-back-definition">
                    {{#PartOfSpeech}}{{PartOfSpeech}} {{/PartOfSpeech}}{{EnglishDefinition}}
                </div>{{/EnglishDefinition}}
                {{#ExampleOne}}
                <div class="cloze-back-examples">
                    <div class="cloze-example-row">
                        <div class="cloze-example-text">{{ExampleOne}}</div>
                        {{#Audio_Example}}<div class="cloze-audio">{{Audio_Example}}</div>{{/Audio_Example}}
                    </div>
                </div>
                {{/ExampleOne}}
            </div>
            ''',
        },
        "front_back": {
            "name": "Imported Front / Back",
            "qfmt": '''
                {{#Audio_Example}}<div class="imported-front imported-front-with-audio">{{Audio_Example}}</div>{{/Audio_Example}}
                {{^Audio_Example}}<div class="imported-front">{{ImportedFront}}</div>{{/Audio_Example}}
            ''',
            "afmt": '''
                {{FrontSide}}
                <hr>
                <div class="imported-back">{{ImportedBack}}</div>
                {{#Audio_Phrase}}<div class="imported-audio">{{Audio_Phrase}}</div>{{/Audio_Phrase}}
            ''',
        },
    }
    return templates[_normalize_card_template(card_template)]


def cleanup_old_apkg_files(max_age_seconds: int = constants.APKG_CLEANUP_MAX_AGE_SECONDS) -> None:
    """Remove stale packages and resumable TTS cache files from our temp subdir."""
    if not os.path.isdir(APKG_TEMP_DIR):
        return
    now = time.time()
    try:
        for name in os.listdir(APKG_TEMP_DIR):
            if not name.endswith((".apkg", ".json", ".tmp")):
                continue
            path = os.path.join(APKG_TEMP_DIR, name)
            if os.path.isfile(path) and (now - os.path.getmtime(path)) > max_age_seconds:
                try:
                    os.remove(path)
                except OSError:
                    pass
    except OSError:
        pass

    if not os.path.isdir(TTS_AUDIO_CACHE_DIR):
        return
    try:
        for name in os.listdir(TTS_AUDIO_CACHE_DIR):
            if not name.endswith((".mp3", ".part")):
                continue
            path = os.path.join(TTS_AUDIO_CACHE_DIR, name)
            if os.path.isfile(path) and (now - os.path.getmtime(path)) > max_age_seconds:
                try:
                    os.remove(path)
                except OSError:
                    pass
    except OSError:
        pass


def generate_anki_package(
    cards_data: List[Dict[str, str]],
    deck_name: str,
    enable_tts: bool = False,
    tts_voice: str = "en-US-JennyNeural",
    progress_callback: Optional[ProgressCallback] = None,
    card_template: str = constants.DEFAULT_CARD_TEMPLATE,
    tts_mode: str = constants.DEFAULT_CARD_AUDIO_MODE,
    audio_report: Optional[Dict[str, int]] = None,
) -> str:
    """Generate Anki package (.apkg) file with optional TTS audio."""
    genanki, tempfile_mod = get_genanki()
    media_files = []
    if audio_report is not None:
        audio_report.clear()
        audio_report.update(requested=0, succeeded=0, failed=0)
    card_template = _normalize_card_template(card_template)
    if tts_mode not in constants.CARD_AUDIO_MODES:
        tts_mode = constants.DEFAULT_CARD_AUDIO_MODE
    if card_template == "definition_front" and tts_mode == "word":
        tts_mode = "word_and_example"

    CSS = """
    .card { font-family: 'Arial', sans-serif; font-size: 20px; text-align: center; color: #333; background-color: white; padding: 20px; }
    .phrase { font-size: 28px; font-weight: 700; color: #0056b3; margin-bottom: 20px; }
    .nightMode .phrase { color: #66b0ff; }
    .phrase-row { display: flex; align-items: center; justify-content: center; gap: 10px; margin-bottom: 16px; }
    .phrase-row .phrase { margin-bottom: 0; }
    .phrase-audio { display: inline-flex; align-items: center; }
    .phonetic { font-size: 18px; color: #475569; margin-bottom: 14px; text-align: left; }
    .nightMode .phonetic { color: #cbd5e1; }
    hr { border: 0; height: 1px; background-image: linear-gradient(to right, rgba(0, 0, 0, 0), rgba(0, 0, 0, 0.2), rgba(0, 0, 0, 0)); margin-bottom: 15px; }
    .meaning { font-size: 20px; font-weight: bold; color: #222; margin-bottom: 15px; text-align: left; }
    .nightMode .meaning { color: #e0e0e0; }
    .example {
        background: #f7f9fa;
        padding: 15px;
        border-left: 5px solid #0056b3;
        border-radius: 4px;
        color: #444;
        font-style: italic;
        font-size: 24px;
        line-height: 1.5;
        text-align: left;
        margin-bottom: 15px;
    }
    .example-audio { margin-top: -6px; margin-bottom: 12px; text-align: left; }
    .nightMode .example { background: #383838; color: #ccc; border-left-color: #66b0ff; }
    .example-translation {
        margin-top: 10px;
        font-size: 18px;
        color: #1f2937;
        font-style: normal;
    }
    .nightMode .example-translation { color: #e5e7eb; }
    .front-example { font-size: 25px; line-height: 1.55; text-align: left; color: #243041; }
    .front-example strong { color: #0f766e; font-weight: 800; }
    .front-definition { font-size: 25px; line-height: 1.45; color: #243041; margin-bottom: 12px; }
    .cloze-front { font-size: 26px; line-height: 1.55; text-align: left; color: #243041; }
    .cloze { font-weight: 800; color: #0f766e; }
    .cloze-fallback { display: inline-block; margin-top: 10px; }
    .cloze-back { text-align: left; color: #243041; }
    .cloze-back-head { display: flex; align-items: center; gap: 12px; margin-bottom: 24px; }
    .cloze-back-word { font-size: 32px; font-weight: 800; color: #0056b3; }
    .cloze-audio { display: inline-flex; align-items: center; flex: 0 0 auto; }
    .cloze-back-definition { font-size: 24px; line-height: 1.5; color: #222; margin-bottom: 26px; padding-bottom: 18px; border-bottom: 1px solid #dbe4ee; }
    .cloze-back-examples { display: grid; gap: 16px; }
    .cloze-example-row { display: grid; grid-template-columns: 1fr auto; gap: 12px; align-items: center; padding: 14px 0; border-bottom: 1px solid #edf2f7; }
    .cloze-example-row:last-child { border-bottom: 0; }
    .cloze-example-text { font-size: 25px; line-height: 1.55; color: #444; }
    .meta { display: inline-block; font-size: 15px; color: #526071; background: #eef6f8; border: 1px solid #cfe4ea; border-radius: 999px; padding: 3px 10px; margin: 4px 0 10px; }
    .hint { display: inline-block; font-size: 18px; line-height: 1.35; letter-spacing: 0; color: #0f766e; background: #eefbf7; border: 1px solid #b7ead8; border-radius: 8px; padding: 6px 12px; margin-top: 8px; }
    .hint-token { display: inline-block; margin-right: 0.65em; white-space: nowrap; }
    .hint-letter { font-weight: 700; }
    .hint-line { display: inline-block; width: 2.6em; height: 0.72em; margin-left: 2px; border-bottom: 2px solid currentColor; vertical-align: baseline; }
    .definition { font-size: 19px; color: #435060; margin-bottom: 14px; text-align: left; }
    .etymology { display: block; font-size: """ + str(constants.ANKI_ETYMOLOGY_FONT_SIZE_PX) + """px; line-height: 1.6; color: #555; background-color: #fffdf5; padding: 10px; border-radius: 6px; margin-bottom: 5px; border: 1px solid #fef3c7; }
    .nightMode .etymology { background-color: #333; color: #aaa; border-color: #444; }
    .nightMode .front-example, .nightMode .front-definition, .nightMode .cloze-front, .nightMode .cloze-back { color: #e5e7eb; }
    .nightMode .cloze { color: #99f6e4; }
    .nightMode .cloze-back-word { color: #66b0ff; }
    .nightMode .cloze-back-definition { color: #e5e7eb; border-bottom-color: #334155; }
    .nightMode .cloze-example-row { border-bottom-color: #253244; }
    .nightMode .cloze-example-text { color: #e5e7eb; }
    .nightMode .definition { color: #cbd5e1; }
    .nightMode .meta { background: #263241; color: #cbd5e1; border-color: #3f4f63; }
    .nightMode .hint { background: #12312f; color: #99f6e4; border-color: #1f5f58; }
    .imported-front, .imported-back { font-size: 24px; line-height: 1.65; text-align: left; color: #243041; }
    .imported-front b, .imported-front strong, .imported-back b, .imported-back strong { color: #0f766e; font-weight: 800; }
    .imported-audio { margin-top: 16px; text-align: left; }
    .example-audio-pair { padding: 0 0 18px; margin: 0 0 18px; border-bottom: 1px solid #dbe4ee; }
    .example-audio-pair:last-child { padding-bottom: 0; margin-bottom: 0; border-bottom: 0; }
    .example-audio-text { display: block; }
    .example-audio-control { display: block; min-height: 32px; margin-top: 8px; }
    .example-audio-item { display: inline-flex; align-items: center; }
    .nightMode .imported-front, .nightMode .imported-back { color: #e5e7eb; }
    .nightMode .example-audio-pair { border-bottom-color: #334155; }
    .nightMode .imported-front b, .nightMode .imported-front strong,
    .nightMode .imported-back b, .nightMode .imported-back strong { color: #99f6e4; }
    """

    DECK_ID = zlib.adler32(deck_name.encode('utf-8'))
    model_id = constants.ANKI_MODEL_ID_BASE + CARD_TEMPLATE_MODEL_OFFSETS[card_template]
    model_label = (
        constants.CARD_TEMPLATES[card_template]["label"]
        if card_template in constants.CARD_TEMPLATES
        else INTERNAL_CARD_TEMPLATE_LABELS[card_template]
    )

    model_type = 0
    if card_template == "definition_front":
        model_type = getattr(genanki.Model, "CLOZE", 1)

    field_defs = [
        {'name': 'Phrase'}, {'name': 'Phonetic'}, {'name': 'Meaning'},
        {'name': 'Example'}, {'name': 'Example_Translation'}, {'name': 'Etymology'},
        {'name': 'PartOfSpeech'}, {'name': 'ChineseMeaning'},
        {'name': 'EnglishDefinition'}, {'name': 'Hint'}, {'name': 'ExampleFront'},
    ]
    if card_template == "definition_front":
        field_defs.extend([{'name': 'ExampleCloze'}, {'name': 'ExampleOne'}])
    elif card_template == "front_back":
        field_defs.extend([{'name': 'ImportedFront'}, {'name': 'ImportedBack'}])
    field_defs.extend([{'name': 'Audio_Phrase'}, {'name': 'Audio_Example'}])

    model = genanki.Model(
        model_id,
        f'VocabFlow {model_label}',
        fields=field_defs,
        templates=[_get_template(card_template)],
        css=CSS,
        model_type=model_type,
    )

    deck = genanki.Deck(DECK_ID, deck_name)

    with tempfile_mod.TemporaryDirectory() as tmp_dir:
        notes_buffer = []
        audio_tasks = []
        queued_audio_paths = set()
        requested_audio_count = 0
        prepared_cards = []

        def queue_audio_task(text: str) -> str:
            """Queue one cache-backed audio request once, even if cards repeat it."""
            cache_path = _cached_tts_audio_path(text, tts_voice)
            if cache_path not in queued_audio_paths:
                queued_audio_paths.add(cache_path)
                audio_tasks.append({
                    'text': text,
                    'path': cache_path,
                    'voice': tts_voice,
                })
            return cache_path

        for idx, card in enumerate(cards_data):
            phrase = safe_str_clean(card.get('w', ''))
            phonetic = safe_str_clean(card.get('p', ''))
            meaning = safe_str_clean(card.get('m', ''))
            example = safe_str_clean(card.get('e', ''))
            example_translation = safe_str_clean(card.get('ec', ''))
            etymology = safe_str_clean(card.get('r', ''))
            imported_front = safe_str_clean(card.get('front', ''))
            imported_back = safe_str_clean(card.get('back', ''))
            note_id = card.get('id')
            part_of_speech, chinese_meaning, english_definition = _split_structured_meaning(meaning)
            if not chinese_meaning and card_template != "definition_front":
                chinese_meaning = meaning
            if not english_definition:
                english_definition = meaning if not re.search(r"[\u4e00-\u9fff]", meaning) else ""
            if card_template == "definition_front":
                english_definition = _sanitize_front_definition(english_definition, phrase, part_of_speech)
            part_of_speech = _format_part_of_speech(part_of_speech)
            example_texts = _example_texts(example)
            example_one = example_texts[0] if example_texts else ""
            if card_template == "definition_front" and not example_one:
                raise RuntimeError(f"卡片结构不完整：{phrase} 缺少英文例句。")
            if card_template == "front_back" and (not imported_front or not imported_back):
                raise RuntimeError(f"卡片结构不完整：{phrase or f'第 {idx + 1} 行'} 缺少正面或背面。")
            example_back = "<br><br>".join(html.escape(item) for item in example_texts)
            hint = _first_letter_hint(phrase)
            example_front = _highlight_target_in_example(example, phrase)
            example_cloze = _build_cloze_example(example, phrase)

            audio_phrase_field = ""
            audio_example_field = ""
            prepared_card = {
                'phrase': phrase,
                'phonetic': phonetic,
                'meaning': meaning,
                'example': example,
                'example_translation': example_translation,
                'etymology': etymology,
                'part_of_speech': part_of_speech,
                'chinese_meaning': chinese_meaning,
                'english_definition': english_definition,
                'hint': hint,
                'example_front': example_front,
                'example_cloze': example_cloze,
                'example_one': example_back,
                'example_texts': example_texts,
                'imported_front': imported_front,
                'imported_back': imported_back,
                'note_id': note_id,
                'audio_phrase_field': audio_phrase_field,
                'audio_example_field': audio_example_field,
                'phrase_audio_path': "",
                'phrase_audio_filename': "",
                'example_audio_items': [],
            }

            if enable_tts and tts_mode != "none":
                safe_phrase = re.sub(r'[^a-zA-Z0-9]', '_', phrase)[:20] or f"card_{idx + 1}"
                unique_id = int(time.time() * 1000) + random.randint(0, 9999)

                if phrase:
                    phrase_filename = f"tts_{safe_phrase}_{unique_id}_p.mp3"
                    prepared_card['phrase_audio_path'] = queue_audio_task(phrase)
                    prepared_card['phrase_audio_filename'] = phrase_filename
                    requested_audio_count += 1

                if tts_mode == "word_and_example":
                    for example_index, example_text in enumerate(example_texts, start=1):
                        if len(example_text) <= 3:
                            continue
                        example_filename = f"tts_{safe_phrase}_{unique_id}_e{example_index}.mp3"
                        prepared_card['example_audio_items'].append({
                            'example_index': example_index - 1,
                            'path': queue_audio_task(example_text),
                            'filename': example_filename,
                        })
                        requested_audio_count += 1

            prepared_cards.append(prepared_card)

        if audio_tasks:
            if audio_report is not None:
                audio_report["requested"] = requested_audio_count

            def completed_card_ratio() -> float:
                if not prepared_cards:
                    return 1.0
                return _completed_audio_card_count(prepared_cards) / len(prepared_cards)

            if progress_callback:
                cached_audio_count = sum(
                    1 for task in audio_tasks
                    if _audio_file_is_valid(str(task.get('path', '')))
                )
                cache_message = (
                    f"已复用 {cached_audio_count}/{len(audio_tasks)} 个此前完成的音频；"
                    if cached_audio_count else ""
                )
                progress_callback(
                    completed_card_ratio(),
                    f"🎙️ {cache_message}正在准备 {len(audio_tasks)} 个音频任务...",
                )

            def internal_progress(_ratio: float, msg: str) -> None:
                if progress_callback:
                    progress_callback(completed_card_ratio(), f"🎙️ {msg}")

            run_async_batch(audio_tasks, concurrency=constants.TTS_CONCURRENCY, progress_callback=internal_progress)

            successful_audio_count = 0
            for prepared_card in prepared_cards:
                phrase_audio_path = prepared_card.get('phrase_audio_path', '')
                if (
                    phrase_audio_path
                    and _audio_file_is_valid(phrase_audio_path)
                ):
                    phrase_package_path = os.path.join(
                        tmp_dir,
                        prepared_card['phrase_audio_filename'],
                    )
                    if _stage_cached_audio(phrase_audio_path, phrase_package_path):
                        prepared_card['audio_phrase_field'] = f"[sound:{prepared_card['phrase_audio_filename']}]"
                        media_files.append(phrase_package_path)
                        successful_audio_count += 1

                example_texts = prepared_card.get('example_texts', [])
                example_audio_tags = [""] * len(example_texts)
                for example_audio in prepared_card.get('example_audio_items', []):
                    example_audio_path = example_audio.get('path', '')
                    if (
                        example_audio_path
                        and _audio_file_is_valid(example_audio_path)
                    ):
                        example_package_path = os.path.join(
                            tmp_dir,
                            example_audio['filename'],
                        )
                        if _stage_cached_audio(example_audio_path, example_package_path):
                            example_index = int(example_audio.get('example_index', 0))
                            example_audio_tags[example_index] = (
                                '<span class="example-audio-item">'
                                f"[sound:{example_audio['filename']}]"
                                '</span>'
                            )
                            media_files.append(example_package_path)
                            successful_audio_count += 1
                if card_template == "front_back":
                    example_fragments = _imported_front_example_fragments(
                        prepared_card.get('imported_front', ''),
                        example_texts,
                    )
                    prepared_card['audio_example_field'] = _render_examples_with_audio(
                        example_fragments,
                        example_audio_tags,
                    )
                else:
                    prepared_card['audio_example_field'] = "".join(example_audio_tags)

            missing_audio_count = requested_audio_count - successful_audio_count
            if audio_report is not None:
                audio_report.update(
                    succeeded=successful_audio_count,
                    failed=missing_audio_count,
                )
            if missing_audio_count:
                logger.warning("TTS generated %s/%s audio files; continuing without %s files.", successful_audio_count, requested_audio_count, missing_audio_count)
                if progress_callback:
                    progress_callback(
                        completed_card_ratio(),
                        f"🎙️ 音频恢复结束：成功 {successful_audio_count}/{requested_audio_count}，"
                        f"仍有 {missing_audio_count} 个失败；正在继续打包。",
                    )
            elif progress_callback:
                progress_callback(
                    completed_card_ratio(),
                    f"🎙️ 全部 {successful_audio_count} 个音频已生成，正在打包。",
                )
        elif progress_callback:
            progress_callback(1.0, "🎙️ 未启用语音，已跳过音频生成。")

        for prepared_card in prepared_cards:
            fields = [
                prepared_card['phrase'],
                prepared_card['phonetic'],
                prepared_card['meaning'],
                prepared_card['example'],
                prepared_card['example_translation'],
                prepared_card['etymology'],
                prepared_card['part_of_speech'],
                prepared_card['chinese_meaning'],
                prepared_card['english_definition'],
                prepared_card['hint'],
                prepared_card['example_front'],
            ]
            if card_template == "definition_front":
                fields.extend([
                    prepared_card['example_cloze'],
                    prepared_card['example_one'],
                ])
            elif card_template == "front_back":
                fields.extend([
                    prepared_card['imported_front'],
                    prepared_card['imported_back'],
                ])
            fields.extend([
                prepared_card['audio_phrase_field'],
                prepared_card['audio_example_field'],
            ])
            if prepared_card['note_id']:
                note = genanki.Note(
                    model=model,
                    fields=fields,
                    guid=prepared_card['note_id']
                )
            else:
                note = genanki.Note(
                    model=model,
                    fields=fields
                )
            notes_buffer.append(note)

        for note in notes_buffer:
            deck.add_note(note)

        if progress_callback:
            progress_callback(1.0, "📦 正在打包 .apkg 文件...")

        package = genanki.Package(deck)
        package.media_files = [f for f in media_files if os.path.exists(f)]

        os.makedirs(APKG_TEMP_DIR, exist_ok=True)
        output_file = tempfile_mod.NamedTemporaryFile(
            dir=APKG_TEMP_DIR, delete=False, suffix='.apkg'
        )
        output_file.close()

        package.write_to_file(output_file.name)
        return output_file.name
