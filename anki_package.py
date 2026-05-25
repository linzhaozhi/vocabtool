# Anki package (.apkg) generation with optional TTS.

import html
import os
import random
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

APKG_TEMP_DIR = os.path.join(tempfile.gettempdir(), constants.APKG_TEMP_SUBDIR)

CARD_TEMPLATE_MODEL_OFFSETS = {
    "word_front": 1,
    "example_front": 2,
    "definition_front": 3,
}


def _normalize_card_template(card_template: str) -> str:
    if card_template in constants.CARD_TEMPLATES:
        return card_template
    return constants.DEFAULT_CARD_TEMPLATE


def _first_letter_hint(phrase: str) -> str:
    tokens = re.findall(r"[A-Za-z]+", phrase)
    return " ".join(
        f'<span class="hint-token"><span class="hint-letter">{html.escape(token[0].lower())}</span><span class="hint-line"></span></span>'
        for token in tokens
        if token
    )


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _looks_like_part_of_speech(text: str) -> bool:
    normalized = text.strip().lower().replace(".", "")
    english_pos = (
        "noun", "n", "verb", "v", "adjective", "adj", "adverb", "adv",
        "preposition", "prep", "conjunction", "conj", "pronoun", "pron",
        "interjection", "phrase", "phrasal verb", "idiom",
    )
    chinese_pos = ("名词", "动词", "形容词", "副词", "介词", "连词", "代词", "感叹词", "短语", "习语")
    return any(pos == normalized for pos in english_pos) or any(pos in text for pos in chinese_pos)


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
        return parts[0], chinese_meaning, english_definition
    if len(parts) >= 2:
        chinese_meaning, english_definition = _pick_meaning_parts(parts)
        return "", chinese_meaning, english_definition
    return "", meaning, ""


def _highlight_target_in_example(example: str, phrase: str) -> str:
    first_example = re.split(r"<br\s*/?>", example, maxsplit=1, flags=re.IGNORECASE)[0].strip()
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
            {{#Phonetic}}<div class="phonetic">{{Phonetic}}</div>{{/Phonetic}}
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
            {{#Phonetic}}<div class="phonetic">{{Phonetic}}</div>{{/Phonetic}}
            <div class="meaning">{{Meaning}}</div>
            {{#EnglishDefinition}}<div class="definition">{{EnglishDefinition}}</div>{{/EnglishDefinition}}
            <div class="example">
                <div>{{Example}}</div>
                {{#Example_Translation}}<div class="example-translation">译：{{Example_Translation}}</div>{{/Example_Translation}}
            </div>
            ''',
        },
        "definition_front": {
            "name": "3. Definition Front",
            "qfmt": '''
                <div class="front-definition">{{EnglishDefinition}}</div>
                {{#PartOfSpeech}}<div class="meta">{{PartOfSpeech}}</div>{{/PartOfSpeech}}
                {{#Hint}}<div class="hint">Hint: {{Hint}}</div>{{/Hint}}
            ''',
            "afmt": '''
            {{FrontSide}}
            <hr>
            <div class="phrase-row">
                <span class="phrase">{{Phrase}}</span>
                <span class="phrase-audio">{{Audio_Phrase}}</span>
            </div>
            {{#Phonetic}}<div class="phonetic">{{Phonetic}}</div>{{/Phonetic}}
            <div class="meaning">{{ChineseMeaning}}</div>
            <div class="example">
                <div>{{Example}}</div>
                {{#Example_Translation}}<div class="example-translation">译：{{Example_Translation}}</div>{{/Example_Translation}}
            </div>
            <div class="example-audio">{{Audio_Example}}</div>
            ''',
        },
    }
    return templates[_normalize_card_template(card_template)]


def cleanup_old_apkg_files(max_age_seconds: int = constants.APKG_CLEANUP_MAX_AGE_SECONDS) -> None:
    """Remove .apkg files in our temp subdir older than max_age_seconds."""
    if not os.path.isdir(APKG_TEMP_DIR):
        return
    now = time.time()
    try:
        for name in os.listdir(APKG_TEMP_DIR):
            if not name.endswith(".apkg"):
                continue
            path = os.path.join(APKG_TEMP_DIR, name)
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
) -> str:
    """Generate Anki package (.apkg) file with optional TTS audio."""
    genanki, tempfile_mod = get_genanki()
    media_files = []
    card_template = _normalize_card_template(card_template)
    if tts_mode not in constants.CARD_AUDIO_MODES:
        tts_mode = constants.DEFAULT_CARD_AUDIO_MODE

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
    .meta { display: inline-block; font-size: 15px; color: #526071; background: #eef6f8; border: 1px solid #cfe4ea; border-radius: 999px; padding: 3px 10px; margin: 4px 0 10px; }
    .hint { display: inline-block; font-size: 18px; line-height: 1.35; letter-spacing: 0; color: #0f766e; background: #eefbf7; border: 1px solid #b7ead8; border-radius: 8px; padding: 6px 12px; margin-top: 8px; }
    .hint-token { display: inline-block; margin-right: 0.65em; white-space: nowrap; }
    .hint-letter { font-weight: 700; }
    .hint-line { display: inline-block; width: 2.6em; height: 0.72em; margin-left: 2px; border-bottom: 2px solid currentColor; vertical-align: baseline; }
    .definition { font-size: 19px; color: #435060; margin-bottom: 14px; text-align: left; }
    .etymology { display: block; font-size: """ + str(constants.ANKI_ETYMOLOGY_FONT_SIZE_PX) + """px; line-height: 1.6; color: #555; background-color: #fffdf5; padding: 10px; border-radius: 6px; margin-bottom: 5px; border: 1px solid #fef3c7; }
    .nightMode .etymology { background-color: #333; color: #aaa; border-color: #444; }
    .nightMode .front-example, .nightMode .front-definition { color: #e5e7eb; }
    .nightMode .definition { color: #cbd5e1; }
    .nightMode .meta { background: #263241; color: #cbd5e1; border-color: #3f4f63; }
    .nightMode .hint { background: #12312f; color: #99f6e4; border-color: #1f5f58; }
    """

    DECK_ID = zlib.adler32(deck_name.encode('utf-8'))
    model_id = constants.ANKI_MODEL_ID_BASE + CARD_TEMPLATE_MODEL_OFFSETS[card_template]
    model_label = constants.CARD_TEMPLATES[card_template]["label"]

    model = genanki.Model(
        model_id,
        f'VocabFlow {model_label}',
        fields=[
            {'name': 'Phrase'}, {'name': 'Phonetic'}, {'name': 'Meaning'},
            {'name': 'Example'}, {'name': 'Example_Translation'}, {'name': 'Etymology'},
            {'name': 'PartOfSpeech'}, {'name': 'ChineseMeaning'},
            {'name': 'EnglishDefinition'}, {'name': 'Hint'}, {'name': 'ExampleFront'},
            {'name': 'Audio_Phrase'}, {'name': 'Audio_Example'}
        ],
        templates=[_get_template(card_template)],
        css=CSS
    )

    deck = genanki.Deck(DECK_ID, deck_name)

    with tempfile_mod.TemporaryDirectory() as tmp_dir:
        notes_buffer = []
        audio_tasks = []
        prepared_cards = []

        for idx, card in enumerate(cards_data):
            phrase = safe_str_clean(card.get('w', ''))
            phonetic = safe_str_clean(card.get('p', ''))
            meaning = safe_str_clean(card.get('m', ''))
            example = safe_str_clean(card.get('e', ''))
            example_translation = safe_str_clean(card.get('ec', ''))
            etymology = safe_str_clean(card.get('r', ''))
            note_id = card.get('id')
            part_of_speech, chinese_meaning, english_definition = _split_structured_meaning(meaning)
            if not chinese_meaning:
                chinese_meaning = meaning
            if not english_definition:
                if card_template == "definition_front":
                    raise RuntimeError(f"第三种卡片格式错误：{phrase} 缺少英文正面释义，请重新生成。")
                english_definition = meaning if not re.search(r"[\u4e00-\u9fff]", meaning) else ""
            if card_template == "definition_front" and _contains_cjk(english_definition):
                raise RuntimeError(f"第三种卡片格式错误：{phrase} 的正面释义包含中文，请重新生成。")
            hint = _first_letter_hint(phrase)
            example_front = _highlight_target_in_example(example, phrase)

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
                'note_id': note_id,
                'audio_phrase_field': audio_phrase_field,
                'audio_example_field': audio_example_field,
                'phrase_audio_path': "",
                'phrase_audio_filename': "",
                'example_audio_path': "",
                'example_audio_filename': "",
            }

            if enable_tts and tts_mode != "none" and phrase:
                safe_phrase = re.sub(r'[^a-zA-Z0-9]', '_', phrase)[:20]
                unique_id = int(time.time() * 1000) + random.randint(0, 9999)

                phrase_filename = f"tts_{safe_phrase}_{unique_id}_p.mp3"
                phrase_path = os.path.join(tmp_dir, phrase_filename)
                audio_tasks.append({
                    'text': phrase,
                    'path': phrase_path,
                    'voice': tts_voice
                })
                prepared_card['phrase_audio_path'] = phrase_path
                prepared_card['phrase_audio_filename'] = phrase_filename

                tts_example = re.sub(r'<br\s*/?>', '. ', example, flags=re.IGNORECASE)
                tts_example = re.sub(r'<[^>]+>', '', tts_example)
                tts_example = re.sub(r'\s+', ' ', tts_example).strip()
                if tts_mode == "word_and_example" and tts_example and len(tts_example) > 3:
                    example_filename = f"tts_{safe_phrase}_{unique_id}_e.mp3"
                    example_path = os.path.join(tmp_dir, example_filename)
                    audio_tasks.append({
                        'text': tts_example,
                        'path': example_path,
                        'voice': tts_voice
                    })
                    prepared_card['example_audio_path'] = example_path
                    prepared_card['example_audio_filename'] = example_filename

            prepared_cards.append(prepared_card)

        if audio_tasks:
            if progress_callback:
                progress_callback(0.0, f"🎙️ 正在准备 {len(audio_tasks)} 个音频任务...")

            def internal_progress(ratio: float, msg: str) -> None:
                if progress_callback:
                    progress_callback(ratio, f"🎙️ {msg}")

            run_async_batch(audio_tasks, concurrency=constants.TTS_CONCURRENCY, progress_callback=internal_progress)

            successful_audio_count = 0
            for prepared_card in prepared_cards:
                phrase_audio_path = prepared_card.get('phrase_audio_path', '')
                if (
                    phrase_audio_path
                    and os.path.exists(phrase_audio_path)
                    and os.path.getsize(phrase_audio_path) > constants.MIN_AUDIO_FILE_SIZE
                ):
                    prepared_card['audio_phrase_field'] = f"[sound:{prepared_card['phrase_audio_filename']}]"
                    media_files.append(phrase_audio_path)
                    successful_audio_count += 1

                example_audio_path = prepared_card.get('example_audio_path', '')
                if (
                    example_audio_path
                    and os.path.exists(example_audio_path)
                    and os.path.getsize(example_audio_path) > constants.MIN_AUDIO_FILE_SIZE
                ):
                    prepared_card['audio_example_field'] = f"[sound:{prepared_card['example_audio_filename']}]"
                    media_files.append(example_audio_path)
                    successful_audio_count += 1

            if progress_callback:
                progress_callback(1.0, f"🎙️ 已生成 {successful_audio_count}/{len(audio_tasks)} 个音频。")
            if successful_audio_count != len(audio_tasks):
                missing_audio_count = len(audio_tasks) - successful_audio_count
                raise RuntimeError(
                    f"语音生成不完整：缺少 {missing_audio_count} 个音频。请稍后重试，或减少本次单词数量。"
                )
            if progress_callback:
                progress_callback(1.0, "🎙️ 音频全部生成完成，正在打包。")
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
                prepared_card['audio_phrase_field'],
                prepared_card['audio_example_field'],
            ]
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
