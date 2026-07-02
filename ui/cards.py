"""Card-generation tab rendering."""

import re
from typing import Any

import pandas as pd
import streamlit as st

import constants
from ai import process_ai_in_batches
from anki_package import cleanup_old_apkg_files, generate_anki_package
from anki_parse import parse_anki_data
from config import get_config
from resources import get_vocab_dict
from ui.helpers import (
    get_prepared_word_list_text,
    parse_unique_words,
    render_anki_download_button,
    reset_anki_state,
    restore_word_editor_state,
    set_anki_pkg,
    sync_card_editor_to_extract,
)
from utils import get_beijing_time_str, render_copy_button, run_gc


def _select_card_template() -> str:
    label_to_key = {template["label"]: key for key, template in constants.CARD_TEMPLATES.items()}
    selected_label = st.radio(
        "🧩 制作卡片模板（三选一）",
        options=list(label_to_key.keys()),
        key="sel_card_template_cards",
    )
    selected_key = label_to_key[selected_label]
    st.caption(constants.CARD_TEMPLATES[selected_key]["description"])
    return selected_key


def _card_word_key(value: str) -> str:
    """Normalize word keys only for counting generated cards."""
    cleaned = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", str(value or "").strip())
    cleaned = cleaned.strip("`'\"“”‘’[](){}<>:：")
    return re.sub(r"\s+", " ", cleaned).lower()


def _generated_card_source_note(word: str) -> str:
    """Build the source note shown on generated card backs."""
    vocab_dict = get_vocab_dict()
    word_key = _card_word_key(word)
    content_source = "内容来源：释义、例句等制卡内容为 AI 生成，请复核"
    if not vocab_dict:
        return f"{content_source}；内置词库：当前未加载 {constants.VOCAB_PROJECT_NAME}。"

    rank = vocab_dict.get(word_key)
    if rank is None:
        return f"{content_source}；内置词库：未命中 {constants.VOCAB_PROJECT_NAME}。"
    return (
        f"{content_source}；词表/rank 来自内置词库 {constants.VOCAB_PROJECT_NAME} "
        f"（rank {rank}；{constants.VOCAB_PROJECT_SOURCE}）。"
    )


def _append_source_notes(cards: list[dict], requested_words: list[str]) -> list[dict]:
    """Attach generated-content and internal-vocab source notes to cards."""
    requested_by_key = {_card_word_key(word): word for word in requested_words}
    annotated_cards = []
    for card in cards:
        normalized_card = dict(card)
        word = requested_by_key.get(_card_word_key(normalized_card.get("w", "")), normalized_card.get("w", ""))
        generated_note = _generated_card_source_note(str(word))
        existing_note = str(normalized_card.get("s") or normalized_card.get("source_note") or "").strip()
        if existing_note:
            normalized_card["s"] = f"{existing_note}；{generated_note}"
        else:
            normalized_card["s"] = generated_note
        annotated_cards.append(normalized_card)
    return annotated_cards


def _card_is_complete(card: dict, requested_word: str, card_template: str) -> bool:
    """Check only structural completeness, not semantic quality."""
    if _card_word_key(card.get("w", "")) != _card_word_key(requested_word):
        return False
    meaning = str(card.get("m", "")).strip()
    example = str(card.get("e", "")).strip()
    if not meaning or not example or not re.search(r"[A-Za-z]", example):
        return False
    if card_template == "definition_front" and "|" not in meaning:
        return False
    return True


def _complete_cards_by_key(cards: list[dict], requested_words: list[str], card_template: str) -> dict[str, dict]:
    """Return one structurally complete card per requested word."""
    requested_by_key = {_card_word_key(word): word for word in requested_words}
    cards_by_key: dict[str, dict] = {}
    for card in cards:
        key = _card_word_key(card.get("w", ""))
        requested_word = requested_by_key.get(key)
        if not requested_word or key in cards_by_key:
            continue
        if _card_is_complete(card, requested_word, card_template):
            normalized_card = dict(card)
            normalized_card["w"] = requested_word
            cards_by_key[key] = normalized_card
    return cards_by_key


def _incomplete_card_words(cards: list[dict], requested_words: list[str], card_template: str) -> list[str]:
    """Return requested words that still lack one structurally complete card."""
    complete_keys = set(_complete_cards_by_key(cards, requested_words, card_template))
    return [word for word in requested_words if _card_word_key(word) not in complete_keys]


def _merge_card_results(
    current_cards: list[dict],
    new_cards: list[dict],
    requested_words: list[str],
    card_template: str,
) -> list[dict]:
    """Merge new AI cards, letting complete cards replace incomplete earlier cards."""
    requested_by_key = {_card_word_key(word): word for word in requested_words}
    merged_by_key: dict[str, dict] = {}

    for card in current_cards + new_cards:
        key = _card_word_key(card.get("w", ""))
        requested_word = requested_by_key.get(key)
        if not requested_word:
            continue

        normalized_card = dict(card)
        normalized_card["w"] = requested_word
        existing = merged_by_key.get(key)
        if existing is None:
            merged_by_key[key] = normalized_card
            continue
        if (
            not _card_is_complete(existing, requested_word, card_template)
            and _card_is_complete(normalized_card, requested_word, card_template)
        ):
            merged_by_key[key] = normalized_card

    return list(merged_by_key.values())


def _ordered_requested_cards(cards: list[dict], requested_words: list[str]) -> list[dict]:
    """Keep exactly one generated card per requested word, in requested order."""
    cards_by_key: dict[str, dict] = {}
    for card in cards:
        key = _card_word_key(card.get("w", ""))
        if key and key not in cards_by_key:
            cards_by_key[key] = card

    ordered_cards = []
    for word in requested_words:
        card = cards_by_key.get(_card_word_key(word))
        if card:
            ordered_cards.append(card)
    return ordered_cards


def _generate_complete_cards_with_queue(
    requested_words: list[str],
    *,
    example_count: int,
    definition_language: str,
    translate_examples: bool,
    card_template: str,
    content_status: Any,
    content_progress_bar: Any,
) -> tuple[list[dict], list[str]]:
    """Generate complete cards by re-queuing failed words at the tail."""
    pending_words = list(requested_words)
    parsed_cards: list[dict] = []
    attempts_by_key: dict[str, int] = {}
    total_words = len(requested_words)
    max_attempts_per_word = max(constants.MAX_RETRIES * 4, 12)

    while pending_words:
        batch = pending_words[: constants.AI_BATCH_SIZE]
        pending_words = pending_words[constants.AI_BATCH_SIZE:]

        for word in batch:
            key = _card_word_key(word)
            attempts_by_key[key] = attempts_by_key.get(key, 0) + 1

        completed_count = len(_complete_cards_by_key(parsed_cards, requested_words, card_template))
        content_status.text(
            f"🧠 正在生成卡片：已完成 {completed_count}/{total_words}，"
            f"本组处理 {len(batch)}/{constants.AI_BATCH_SIZE} 个，队列剩余 {len(pending_words)} 个"
        )

        def update_queue_progress(current: int, total: int) -> None:
            ratio = (completed_count + current) / total_words if total_words else 0
            content_progress_bar.progress(min(ratio, 0.98))
            content_status.text(
                f"🧠 正在生成卡片：批次 {current}/{total}，"
                f"已完成 {completed_count}/{total_words}，队列剩余 {len(pending_words)} 个"
            )

        result = process_ai_in_batches(
            batch,
            example_count=int(example_count),
            definition_language=definition_language,
            translate_examples=bool(translate_examples),
            progress_callback=update_queue_progress,
            card_template=card_template,
        )
        if result:
            new_cards = _append_source_notes(parse_anki_data(result), requested_words)
            parsed_cards = _merge_card_results(
                parsed_cards,
                new_cards,
                requested_words,
                card_template,
            )

        incomplete_words = _incomplete_card_words(parsed_cards, batch, card_template)
        exhausted_words = [
            word
            for word in incomplete_words
            if attempts_by_key.get(_card_word_key(word), 0) >= max_attempts_per_word
        ]
        if exhausted_words:
            return parsed_cards, exhausted_words

        pending_words.extend(incomplete_words)

    complete_cards = _complete_cards_by_key(parsed_cards, requested_words, card_template)
    ordered_cards = _ordered_requested_cards(list(complete_cards.values()), requested_words)
    missing_words = _incomplete_card_words(ordered_cards, requested_words, card_template)
    return ordered_cards, missing_words


def render_cards_tab() -> None:
    """Render the card-generation tab."""
    cleanup_old_apkg_files()
    st.markdown("### 📦 制作卡片")
    st.caption("使用内置智能能力，把准备好的词表直接生成 Anki 卡片。")
    ai_provider_label = get_config().get("ai_provider_label", "智能模型")
    card_template = _select_card_template()

    current_words_text = restore_word_editor_state("card_word_list_editor").strip()
    st.session_state["word_list_editor"] = current_words_text
    if not current_words_text:
        st.info("先到“提取单词”里准备词表，然后再来制作卡片。")
        return

    beijing_time_str = get_beijing_time_str()
    default_deck_name = f"词卡_{beijing_time_str}"
    if "deck_name_input" not in st.session_state:
        st.session_state["deck_name_input"] = default_deck_name

    col_name, col_voice = st.columns([2, 3])
    with col_name:
        deck_name = st.text_input("🏷️ 牌组名称", key="deck_name_input")
    with col_voice:
        selected_voice_label = st.radio(
            "🎙️ 英语发音",
            options=list(constants.VOICE_MAP.keys()),
            index=0,
            horizontal=True,
            key="sel_voice_cards",
        )
    selected_voice_code = constants.VOICE_MAP[selected_voice_label]

    audio_label_to_key = {mode["label"]: key for key, mode in constants.CARD_AUDIO_MODES.items()}
    default_audio_label = constants.CARD_AUDIO_MODES[constants.DEFAULT_CARD_AUDIO_MODE]["label"]
    selected_audio_label = st.radio(
        "🎚️ 音频内容",
        options=list(audio_label_to_key.keys()),
        index=list(audio_label_to_key.keys()).index(default_audio_label),
        horizontal=True,
        key="sel_audio_mode_cards",
    )
    selected_audio_mode = audio_label_to_key[selected_audio_label]
    if card_template == "definition_front" and selected_audio_mode == "word":
        selected_audio_mode = "word_and_example"
    enable_audio_auto = selected_audio_mode != "none"
    if card_template == "definition_front" and enable_audio_auto:
        st.caption("第 3 种模板会在反面生成单词和例句音频；个别音频失败时会跳过音频，卡片照常生成。")
    else:
        st.caption(
            f"{constants.CARD_AUDIO_MODES[selected_audio_mode]['description']} "
            "个别音频失败时会跳过音频，卡片照常生成。"
        )
    selected_example_count = constants.AI_CARD_EXAMPLE_COUNT_DEFAULT
    definition_language = "中文"
    translate_examples = False

    col_title, col_copy_btn = st.columns([5, 1])
    with col_title:
        st.markdown("### 📝 待制卡词表")
    with col_copy_btn:
        render_copy_button(get_prepared_word_list_text(), key="copy_card_words_btn")

    st.caption("💡 可以在这里继续编辑、新增或删除单词，每行一个。")
    edited_words = st.text_area(
        "待制卡单词列表",
        height=300,
        key="card_word_list_editor",
        label_visibility="collapsed",
        help="每行一个单词",
        on_change=sync_card_editor_to_extract,
    )
    st.session_state["word_list_editor"] = edited_words

    words_only = parse_unique_words(edited_words)

    st.caption(f"当前待制作 {len(words_only)} 个词。")
    st.caption(f"单次最多处理 {constants.MAX_AUTO_LIMIT} 个词。")

    if len(words_only) > constants.MAX_AUTO_LIMIT:
        st.warning(
            f"⚠️ 单词数超过 {constants.MAX_AUTO_LIMIT}，内置智能仅处理前 {constants.MAX_AUTO_LIMIT} 个。请缩小列表后再生成。"
        )
        words_for_generation = words_only[: constants.MAX_AUTO_LIMIT]
    else:
        words_for_generation = words_only

    col_generate, col_reset = st.columns([4, 1])
    with col_generate:
        st.markdown(
            '<div class="card-generate-hint"><strong>最后一步：生成卡片</strong>确认词表没问题后，点击下面按钮开始批量生成。</div>',
            unsafe_allow_html=True,
        )
        start_auto_gen = st.button(
            f"🚀 使用 {ai_provider_label} 生成卡片",
            type="primary",
            key="btn_generate_cards",
            use_container_width=False,
        )
    with col_reset:
        st.markdown('<div class="card-reset-panel"></div>', unsafe_allow_html=True)
        st.button("清空", type="secondary", on_click=reset_anki_state, use_container_width=False)

    if start_auto_gen:
        if not words_for_generation:
            st.warning("⚠️ 当前没有可用于制卡的单词。")
        else:
            st.markdown("#### 生成进度")
            content_status = st.empty()
            content_progress_bar = st.progress(0)
            voice_status = st.empty()
            voice_progress_bar = st.progress(0)

            content_status.text("🧠 正在按 10 个一组生成卡片...")
            voice_status.text("🎙️ 语音进度：等待内容生成完成")
            parsed_data, incomplete_words = _generate_complete_cards_with_queue(
                words_for_generation,
                example_count=int(selected_example_count),
                definition_language=definition_language,
                translate_examples=bool(translate_examples),
                card_template=card_template,
                content_status=content_status,
                content_progress_bar=content_progress_bar,
            )

            if incomplete_words:
                preview = "、".join(incomplete_words[:20])
                more = f" 等 {len(incomplete_words)} 个词" if len(incomplete_words) > 20 else ""
                content_status.text("⚠️ 仍有卡片暂未生成完整")
                st.warning(f"仍有 {len(incomplete_words)} 个词没有生成完整卡片：{preview}{more}。本次不会打包不完整卡片。")
                return

            try:
                content_progress_bar.progress(1.0)
                content_status.text(f"✅ 内容生成完成：共 {len(parsed_data)} 张卡片，正在打包...")
                voice_status.text("🎙️ 正在准备语音和 Anki 包...")
                voice_progress_bar.progress(0.0)
                final_deck_name = deck_name.strip() or default_deck_name

                def update_pkg_progress(ratio: float, text: str) -> None:
                    voice_progress_bar.progress(ratio)
                    voice_status.text(text)

                file_path = generate_anki_package(
                    parsed_data,
                    final_deck_name,
                    enable_tts=enable_audio_auto,
                    tts_voice=selected_voice_code,
                    progress_callback=update_pkg_progress,
                    card_template=card_template,
                    tts_mode=selected_audio_mode,
                )

                st.session_state["anki_cards_cache"] = parsed_data
                set_anki_pkg(file_path, final_deck_name)

                voice_progress_bar.progress(1.0)
                voice_status.text("✅ 音频和打包完成")
                content_status.markdown(f"✅ **处理完成！共生成 {len(parsed_data)} 张卡片**")
                st.balloons()
                run_gc()
            except Exception as exc:
                from errors import ErrorHandler

                ErrorHandler.handle(exc, "生成出错")

    st.caption("⚠️ 智能生成内容可能存在错误，请人工复核。卡片反面会标注 AI 生成和内置词库命中情况。")

    render_anki_download_button(
        f"📥 下载 {st.session_state.get('anki_pkg_name', '词卡.apkg')}",
        button_type="primary",
        use_container_width=True,
    )

    if st.session_state.get("anki_cards_cache"):
        cards = st.session_state["anki_cards_cache"]
        with st.expander(f"👀 预览卡片 (前 {constants.MAX_PREVIEW_CARDS} 张)", expanded=True):
            df_view = pd.DataFrame(cards)
            display_cols = ["w", "p", "m", "e", "ec", "r", "s"]
            df_view = df_view[[column for column in display_cols if column in df_view.columns]]
            rename_map = {
                "w": "正面",
                "p": "音标",
                "m": "中文/英文释义",
                "e": "英文例句",
                "ec": "例句翻译",
                "r": "词源",
                "s": "来源注释",
            }
            df_view = df_view.rename(columns=rename_map)
            for column_name in ("英文例句", "例句翻译"):
                if column_name in df_view.columns:
                    df_view[column_name] = df_view[column_name].astype(str).str.replace(r"<br\s*/?>", "\n", regex=True)
            st.dataframe(df_view.head(constants.MAX_PREVIEW_CARDS), use_container_width=True, hide_index=True)
