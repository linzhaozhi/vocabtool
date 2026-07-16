"""External AI card-file import and packaging page."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pandas as pd
import streamlit as st

import constants
from anki_package import cleanup_old_apkg_files, generate_anki_package
from card_file_import import (
    DISPLAY_COLUMNS,
    FRONT_BACK_DISPLAY_COLUMNS,
    CardFileParseError,
    cards_to_display_rows,
    display_rows_to_cards,
    display_rows_to_front_back_cards,
    front_back_cards_to_display_rows,
    parse_card_file,
    validate_imported_cards,
)
from errors import ErrorHandler
from ui.helpers import render_anki_download_button, reset_anki_state, set_anki_pkg
from utils import get_beijing_time_str, run_gc


IMPORT_PATH_KEY = "import_anki_pkg_path"
IMPORT_NAME_KEY = "import_anki_pkg_name"
IMPORT_CACHE_KEY = "import_cards_cache"

CSV_TEMPLATE = (
    "\ufeffword,phonetic,part_of_speech,chinese_meaning,english_definition,"
    "example,example_translation,etymology\n"
    'example,/ɪɡˈzɑːmpəl/,noun,例子,"something that shows what something is like",'
    '"This is a clear example.",这是一个清楚的例子。,来自拉丁语 exemplum\n'
)
TXT_TEMPLATE = (
    "example ||| /ɪɡˈzɑːmpəl/ ||| noun | 例子 | something that shows what something is like "
    "||| This is a clear example. ||| 这是一个清楚的例子。 ||| 来自拉丁语 exemplum\n"
)


def _reset_import_package() -> None:
    reset_anki_state(
        path_key=IMPORT_PATH_KEY,
        name_key=IMPORT_NAME_KEY,
        cache_key=IMPORT_CACHE_KEY,
    )
    st.session_state["import_package_signature"] = ""


def _clear_import_state() -> None:
    _reset_import_package()
    for key in (
        "import_file_signature",
        "import_file_cards",
        "import_file_format",
        "import_file_warnings",
        "import_card_template",
        "import_source_name",
        "import_current_cards",
    ):
        st.session_state.pop(key, None)
    st.session_state["import_uploader_nonce"] = int(st.session_state.get("import_uploader_nonce", 0)) + 1


def _safe_deck_stem(file_name: str) -> str:
    stem = Path(file_name or "导入卡片").stem.strip() or "导入卡片"
    return re.sub(r"[\\/:*?\"<>|]+", "_", stem)


def _build_signature(
    cards: list[dict[str, str]],
    *,
    deck_name: str,
    card_template: str,
    audio_mode: str,
    voice: str,
) -> str:
    payload = {
        "cards": cards,
        "deck_name": deck_name,
        "card_template": card_template,
        "audio_mode": audio_mode,
        "voice": voice,
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _render_format_templates() -> None:
    with st.expander("文件格式"):
        st.caption(
            "推荐字段：word、phonetic、meaning，或 part_of_speech + chinese_meaning + "
            "english_definition，以及 example、example_translation、etymology。也支持富文本 Front/Back 两列表："
            "Back 首行为“单词 · 词性”，下一行为英文定义；Front 可包含一个或多个例句。"
        )
        csv_col, txt_col = st.columns(2)
        with csv_col:
            st.download_button(
                "下载 CSV 模板",
                data=CSV_TEMPLATE.encode("utf-8"),
                file_name="ai_cards_template.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with txt_col:
            st.download_button(
                "下载 TXT 模板",
                data=TXT_TEMPLATE.encode("utf-8"),
                file_name="ai_cards_template.txt",
                mime="text/plain",
                use_container_width=True,
            )
        st.code(
            "word ||| phonetic ||| meaning ||| example ||| example_translation ||| etymology",
            language="text",
        )


def _load_uploaded_file(uploaded_file) -> None:
    bytes_data = uploaded_file.getvalue()
    signature = hashlib.sha256(bytes_data).hexdigest()
    if signature == st.session_state.get("import_file_signature"):
        return

    _reset_import_package()
    result = parse_card_file(uploaded_file.name, bytes_data)
    st.session_state["import_file_signature"] = signature
    st.session_state["import_file_cards"] = result.cards
    st.session_state["import_current_cards"] = result.cards
    st.session_state["import_file_format"] = result.format_name
    st.session_state["import_file_warnings"] = result.warnings
    st.session_state["import_card_template"] = result.card_template
    st.session_state["import_source_name"] = uploaded_file.name


def render_card_import_tab() -> None:
    """Render the external card import, TTS, and APKG workflow."""
    cleanup_old_apkg_files()
    st.markdown("### 导入 AI 卡片")
    st.caption("上传其他 AI 制作的 CSV 或 TXT 卡片文件，确认内容后直接生成语音和 Anki 包。")
    _render_format_templates()

    uploader_nonce = int(st.session_state.get("import_uploader_nonce", 0))
    uploaded_file = st.file_uploader(
        "上传卡片文件",
        type=["csv", "txt"],
        key=f"external_card_file_uploader_{uploader_nonce}",
        help=f"单个文件最大 {constants.MAX_UPLOAD_MB} MB",
    )

    if uploaded_file is not None:
        if uploaded_file.size > constants.MAX_UPLOAD_BYTES:
            st.error(f"文件超过 {constants.MAX_UPLOAD_MB} MB，无法处理。")
            return
        try:
            _load_uploaded_file(uploaded_file)
        except CardFileParseError as exc:
            st.error(str(exc))
            return
        except Exception as exc:
            ErrorHandler.handle(exc, "读取卡片文件失败")
            return

    source_cards = st.session_state.get("import_file_cards") or []
    if not source_cards:
        st.info("请先上传包含卡片内容的 CSV 或 TXT 文件。")
        return

    source_name = st.session_state.get("import_source_name", "已导入文件")
    format_name = st.session_state.get("import_file_format", "卡片文件")
    title_col, clear_col = st.columns([5, 1])
    with title_col:
        st.success(f"已从 {source_name} 识别 {len(source_cards)} 行卡片（{format_name}）。")
    with clear_col:
        st.button("清除导入", on_click=_clear_import_state, use_container_width=True)

    for warning in st.session_state.get("import_file_warnings") or []:
        st.warning(warning)

    card_template = st.session_state.get("import_card_template", "word_front")
    card_type_labels = {
        "front_back": "普通 Front/Back",
        "definition_front": "Anki Cloze",
        "word_front": "字段词卡",
    }
    st.caption(f"卡片类型：{card_type_labels.get(card_template, '字段词卡')}（已根据文件自动识别）")

    deck_default = f"{_safe_deck_stem(source_name)}_{get_beijing_time_str()}"
    deck_name = st.text_input(
        "牌组名称",
        value=deck_default,
        key=f"import_deck_name_{st.session_state.get('import_file_signature', '')[:12]}",
    ).strip() or deck_default

    voice_col, audio_col = st.columns(2)
    with voice_col:
        selected_voice_label = st.radio(
            "英语发音",
            options=list(constants.VOICE_MAP.keys()),
            key="sel_voice_import",
        )
    selected_voice_code = constants.VOICE_MAP[selected_voice_label]

    audio_keys = list(constants.CARD_AUDIO_MODES)
    if card_template == "definition_front":
        audio_keys.remove("word")
    audio_label_to_key = {constants.CARD_AUDIO_MODES[key]["label"]: key for key in audio_keys}
    default_audio_label = constants.CARD_AUDIO_MODES[constants.DEFAULT_CARD_AUDIO_MODE]["label"]
    with audio_col:
        selected_audio_label = st.radio(
            "音频内容",
            options=list(audio_label_to_key),
            index=list(audio_label_to_key).index(default_audio_label),
            key=f"sel_audio_mode_import_{card_template}",
        )
    selected_audio_mode = audio_label_to_key[selected_audio_label]
    enable_tts = selected_audio_mode != "none"

    st.markdown("#### 卡片内容")
    st.caption("可直接修改单元格，也可以新增或删除行。打包时每个有效行对应一张卡片。")
    editor_key = f"import_cards_editor_{st.session_state.get('import_file_signature', '')[:12]}"
    editor_base_cards = source_cards
    if editor_key not in st.session_state:
        editor_base_cards = st.session_state.get("import_current_cards") or source_cards
        st.session_state["import_file_cards"] = editor_base_cards
    is_front_back = card_template == "front_back"
    if is_front_back:
        editor_rows = front_back_cards_to_display_rows(editor_base_cards)
        editor_columns = list(FRONT_BACK_DISPLAY_COLUMNS.values())
        column_config = {
            "正面": st.column_config.TextColumn("正面", required=True, width="large"),
            "背面": st.column_config.TextColumn("背面", required=True, width="large"),
        }
    else:
        editor_rows = cards_to_display_rows(editor_base_cards)
        editor_columns = list(DISPLAY_COLUMNS.values())
        column_config = {
            "单词/短语": st.column_config.TextColumn("单词/短语", required=True, width="medium"),
            "音标": st.column_config.TextColumn("音标", width="medium"),
            "释义": st.column_config.TextColumn("释义", required=True, width="large"),
            "英文例句": st.column_config.TextColumn("英文例句", width="large"),
            "例句翻译": st.column_config.TextColumn("例句翻译", width="large"),
            "词源": st.column_config.TextColumn("词源", width="large"),
        }
    editor_df = pd.DataFrame(editor_rows, columns=editor_columns)
    editor_height = min(720, max(260, 36 * (len(editor_df) + 2)))
    edited_df = st.data_editor(
        editor_df,
        key=editor_key,
        num_rows="dynamic",
        hide_index=False,
        use_container_width=True,
        height=editor_height,
        column_config=column_config,
    )
    if is_front_back:
        cards = display_rows_to_front_back_cards(edited_df.to_dict(orient="records"))
    else:
        cards = display_rows_to_cards(edited_df.to_dict(orient="records"))
    st.session_state["import_current_cards"] = cards

    require_examples = card_template in {"example_front", "definition_front"} or selected_audio_mode == "word_and_example"
    issues = validate_imported_cards(cards, require_examples=require_examples)
    st.caption(f"当前将打包 {len(cards)} 张卡片。")
    if issues:
        st.error(f"发现 {len(issues)} 个结构问题，修正后才能打包。")
        with st.expander("查看需要修正的行", expanded=True):
            for issue in issues[:100]:
                st.write(f"- {issue}")
            if len(issues) > 100:
                st.write(f"另有 {len(issues) - 100} 个问题未显示。")

    build_signature = _build_signature(
        cards,
        deck_name=deck_name,
        card_template=card_template,
        audio_mode=selected_audio_mode,
        voice=selected_voice_code,
    )
    if (
        st.session_state.get(IMPORT_PATH_KEY)
        and st.session_state.get("import_package_signature") != build_signature
    ):
        _reset_import_package()

    start_packaging = st.button(
        f"生成 {len(cards)} 张卡片的 APKG",
        type="primary",
        key="btn_package_imported_cards",
        disabled=bool(issues),
        use_container_width=True,
    )

    if start_packaging:
        status = st.empty()
        progress = st.progress(0.0)
        status.text("正在准备卡片和语音...")

        def update_progress(ratio: float, message: str) -> None:
            progress.progress(min(max(float(ratio), 0.0), 1.0))
            status.text(message)

        try:
            file_path = generate_anki_package(
                cards,
                deck_name,
                enable_tts=enable_tts,
                tts_voice=selected_voice_code,
                progress_callback=update_progress,
                card_template=card_template,
                tts_mode=selected_audio_mode,
            )
            set_anki_pkg(
                file_path,
                deck_name,
                path_key=IMPORT_PATH_KEY,
                name_key=IMPORT_NAME_KEY,
            )
            st.session_state[IMPORT_CACHE_KEY] = cards
            st.session_state["import_package_signature"] = build_signature
            progress.progress(1.0)
            status.text(f"完成：{len(cards)} 行已生成 {len(cards)} 张 Anki 卡片。")
            st.success(f"APKG 已生成，共 {len(cards)} 张卡片。")
            run_gc()
        except Exception as exc:
            ErrorHandler.handle(exc, "生成 APKG 失败")

    render_anki_download_button(
        f"下载 {st.session_state.get(IMPORT_NAME_KEY, '导入卡片.apkg')}",
        button_type="primary",
        use_container_width=True,
        path_key=IMPORT_PATH_KEY,
        name_key=IMPORT_NAME_KEY,
    )
