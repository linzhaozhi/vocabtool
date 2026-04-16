"""Card-generation tab rendering."""

import pandas as pd
import streamlit as st

import constants
from ai import process_ai_in_batches
from anki_package import generate_anki_package
from anki_parse import parse_anki_data
from ui.helpers import (
    parse_unique_words,
    render_anki_download_button,
    reset_anki_state,
    set_anki_pkg,
    sync_card_editor_to_extract,
)
from utils import get_beijing_time_str, render_copy_button, run_gc


def render_cards_tab() -> None:
    """Render the card-generation tab."""
    st.markdown("### 📦 制作卡片")
    st.caption("使用内置智能能力，把准备好的词表直接生成 Anki 卡片。")

    current_words_text = st.session_state.get("word_list_editor", "").strip()
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
    st.caption("支持美音和英音；音频只朗读英文单词和英文例句，卡片会显示对应的美音/英音音标。")

    col_audio, col_example_count = st.columns([2, 2])
    with col_audio:
        enable_audio_auto = st.checkbox("生成单词和例句音频", value=True, key="chk_audio_cards")
    with col_example_count:
        selected_example_count = st.radio(
            "🧾 例句数量",
            options=[1, 2],
            index=constants.AI_CARD_EXAMPLE_COUNT_DEFAULT - 1,
            horizontal=True,
            format_func=lambda value: f"{value} 句",
            key="sel_example_count",
        )

    col_title, col_copy_btn = st.columns([5, 1])
    with col_title:
        st.markdown("### 📝 待制卡词表")
    with col_copy_btn:
        render_copy_button(st.session_state.get("word_list_editor", ""), key="copy_card_words_btn")

    st.caption("💡 可以在这里继续编辑、新增或删除单词，每行一个。")
    edited_words = st.text_area(
        "待制卡单词列表",
        height=300,
        key="word_list_editor",
        label_visibility="collapsed",
        help="每行一个单词",
        on_change=sync_card_editor_to_extract,
    )

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

    col_generate, col_reset = st.columns([3, 1])
    with col_generate:
        st.markdown(
            '<div class="card-generate-panel"><strong>最后一步：生成卡片</strong>确认词表没问题后，点击下面按钮开始批量生成。</div>',
            unsafe_allow_html=True,
        )
        start_auto_gen = st.button("🚀 使用 DeepSeek 生成卡片", type="primary", use_container_width=True)
    with col_reset:
        st.button("清空结果", type="secondary", on_click=reset_anki_state, use_container_width=True)

    if start_auto_gen:
        if not words_for_generation:
            st.warning("⚠️ 当前没有可用于制卡的单词。")
        else:
            progress_bar = st.progress(0)
            status_text = st.empty()

            def update_ai_progress(current: int, total: int) -> None:
                ratio = current / total if total > 0 else 0
                progress_bar.progress(ratio)
                status_text.text(f"正在处理 ({current}/{total})")

            status_text.text("🧠 正在请求智能生成...")
            ai_result = process_ai_in_batches(
                words_for_generation,
                example_count=int(selected_example_count),
                progress_callback=update_ai_progress,
            )

            if ai_result:
                status_text.text("✅ 内容生成完成，正在解析...")
                parsed_data = parse_anki_data(ai_result)

                if parsed_data:
                    try:
                        status_text.text("📦 正在生成 Anki 包...")
                        final_deck_name = deck_name.strip() or default_deck_name

                        def update_pkg_progress(ratio: float, text: str) -> None:
                            progress_bar.progress(ratio)
                            status_text.text(text)

                        file_path = generate_anki_package(
                            parsed_data,
                            final_deck_name,
                            enable_tts=enable_audio_auto,
                            tts_voice=selected_voice_code,
                            progress_callback=update_pkg_progress,
                        )

                        st.session_state["anki_cards_cache"] = parsed_data
                        set_anki_pkg(file_path, final_deck_name)

                        status_text.markdown(f"✅ **处理完成！共生成 {len(parsed_data)} 张卡片**")
                        st.balloons()
                        run_gc()
                    except Exception as exc:
                        from errors import ErrorHandler

                        ErrorHandler.handle(exc, "生成出错")
                else:
                    st.error("解析失败，返回内容为空或格式错误。")
            else:
                st.error("生成失败，请检查 API Key 或网络连接。")

    st.caption("⚠️ 智能生成内容可能存在错误，请人工复核。")

    render_anki_download_button(
        f"📥 下载 {st.session_state.get('anki_pkg_name', '词卡.apkg')}",
        button_type="primary",
        use_container_width=True,
    )

    if st.session_state["anki_cards_cache"]:
        cards = st.session_state["anki_cards_cache"]
        with st.expander(f"👀 预览卡片 (前 {constants.MAX_PREVIEW_CARDS} 张)", expanded=True):
            df_view = pd.DataFrame(cards)
            display_cols = ["w", "p", "m", "e", "ec", "r"]
            df_view = df_view[[column for column in display_cols if column in df_view.columns]]
            rename_map = {
                "w": "正面",
                "p": "音标",
                "m": "中文/英文释义",
                "e": "英文例句",
                "ec": "例句翻译",
                "r": "词源",
            }
            df_view = df_view.rename(columns=rename_map)
            for column_name in ("英文例句", "例句翻译"):
                if column_name in df_view.columns:
                    df_view[column_name] = df_view[column_name].astype(str).str.replace(r"<br\s*/?>", "\n", regex=True)
            st.dataframe(df_view.head(constants.MAX_PREVIEW_CARDS), use_container_width=True, hide_index=True)
