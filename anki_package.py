# Anki package (.apkg) generation with optional TTS.

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
    progress_callback: Optional[ProgressCallback] = None
) -> str:
    """Generate Anki package (.apkg) file with optional TTS audio."""
    genanki, tempfile_mod = get_genanki()
    media_files = []

    CSS = """
    .card { font-family: 'Arial', sans-serif; font-size: 20px; text-align: center; color: #333; background-color: white; padding: 20px; }
    .phrase { font-size: 28px; font-weight: 700; color: #0056b3; margin-bottom: 20px; }
    .nightMode .phrase { color: #66b0ff; }
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
    .nightMode .example { background: #383838; color: #ccc; border-left-color: #66b0ff; }
    .example-translation {
        margin-top: 10px;
        font-size: 18px;
        color: #1f2937;
        font-style: normal;
    }
    .nightMode .example-translation { color: #e5e7eb; }
    .etymology { display: block; font-size: """ + str(constants.ANKI_ETYMOLOGY_FONT_SIZE_PX) + """px; line-height: 1.6; color: #555; background-color: #fffdf5; padding: 10px; border-radius: 6px; margin-bottom: 5px; border: 1px solid #fef3c7; }
    .nightMode .etymology { background-color: #333; color: #aaa; border-color: #444; }
    """

    DECK_ID = zlib.adler32(deck_name.encode('utf-8'))

    model = genanki.Model(
        constants.ANKI_MODEL_ID,
        'VocabFlow Unified Model',
        fields=[
            {'name': 'Phrase'}, {'name': 'Phonetic'}, {'name': 'Meaning'},
            {'name': 'Example'}, {'name': 'Example_Translation'}, {'name': 'Etymology'},
            {'name': 'Audio_Phrase'}, {'name': 'Audio_Example'}
        ],
        templates=[{
            'name': 'Vocab Card',
            'qfmt': '''
                <div class="phrase">{{Phrase}}</div>
                <div>{{Audio_Phrase}}</div>
            ''',
            'afmt': '''
            {{FrontSide}}
            <hr>
            {{#Phonetic}}
            <div class="phonetic">{{Phonetic}}</div>
            {{/Phonetic}}
            <div class="meaning">{{Meaning}}</div>
            <div class="example">
                <div>🗣️ {{Example}}</div>
                {{#Example_Translation}}
                <div class="example-translation">译：{{Example_Translation}}</div>
                {{/Example_Translation}}
            </div>
            <div>{{Audio_Example}}</div>
            {{#Etymology}}
            <div class="etymology">🌱 词源: {{Etymology}}</div>
            {{/Etymology}}
            ''',
        }], css=CSS
    )

    deck = genanki.Deck(DECK_ID, deck_name)

    with tempfile_mod.TemporaryDirectory() as tmp_dir:
        notes_buffer = []
        audio_tasks = []

        for idx, card in enumerate(cards_data):
            phrase = safe_str_clean(card.get('w', ''))
            phonetic = safe_str_clean(card.get('p', ''))
            meaning = safe_str_clean(card.get('m', ''))
            example = safe_str_clean(card.get('e', ''))
            example_translation = safe_str_clean(card.get('ec', ''))
            etymology = safe_str_clean(card.get('r', ''))
            note_id = card.get('id')

            audio_phrase_field = ""
            audio_example_field = ""

            if enable_tts and phrase:
                safe_phrase = re.sub(r'[^a-zA-Z0-9]', '_', phrase)[:20]
                unique_id = int(time.time() * 1000) + random.randint(0, 9999)

                phrase_filename = f"tts_{safe_phrase}_{unique_id}_p.mp3"
                phrase_path = os.path.join(tmp_dir, phrase_filename)
                audio_tasks.append({
                    'text': phrase,
                    'path': phrase_path,
                    'voice': tts_voice
                })
                media_files.append(phrase_path)
                audio_phrase_field = f"[sound:{phrase_filename}]"

                tts_example = re.sub(r'<br\s*/?>', '. ', example, flags=re.IGNORECASE)
                tts_example = re.sub(r'\s+', ' ', tts_example).strip()
                if tts_example and len(tts_example) > 3:
                    example_filename = f"tts_{safe_phrase}_{unique_id}_e.mp3"
                    example_path = os.path.join(tmp_dir, example_filename)
                    audio_tasks.append({
                        'text': tts_example,
                        'path': example_path,
                        'voice': tts_voice
                    })
                    media_files.append(example_path)
                    audio_example_field = f"[sound:{example_filename}]"

            if note_id:
                note = genanki.Note(
                    model=model,
                    fields=[phrase, phonetic, meaning, example, example_translation, etymology, audio_phrase_field, audio_example_field],
                    guid=note_id
                )
            else:
                note = genanki.Note(
                    model=model,
                    fields=[phrase, phonetic, meaning, example, example_translation, etymology, audio_phrase_field, audio_example_field]
                )
            notes_buffer.append(note)

        if audio_tasks:
            if progress_callback:
                progress_callback(0.0, f"🎙️ 正在准备 {len(audio_tasks)} 个音频任务...")

            def internal_progress(ratio: float, msg: str) -> None:
                if progress_callback:
                    progress_callback(ratio, f"🎙️ {msg}")

            run_async_batch(audio_tasks, concurrency=constants.TTS_CONCURRENCY, progress_callback=internal_progress)
        elif progress_callback:
            progress_callback(1.0, "🎙️ 未启用语音，已跳过音频生成。")

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
