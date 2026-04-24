"""DeepSeek chat tab rendering."""

import html

import streamlit as st

import constants
from ai import chat_with_deepseek
from config import get_config

STARTER_PROMPTS = [
    "帮我区分 affect 和 effect",
    "给我 5 个 travel 相关短语",
    "解释 present perfect 的用法",
]


def _render_chat_history() -> None:
    """Render stored chat history."""
    for message in st.session_state.get("deepseek_chat_messages", []):
        role = message.get("role")
        if role not in {"user", "assistant"}:
            continue
        with st.chat_message(role):
            st.markdown(message.get("content", ""))


def _run_chat_turn(prompt: str) -> None:
    """Handle one user prompt and append the assistant response to history."""
    user_message = prompt.strip()
    if not user_message:
        return

    st.session_state["deepseek_chat_messages"].append({"role": "user", "content": user_message})

    result = chat_with_deepseek(st.session_state["deepseek_chat_messages"])
    if result and "error" not in result:
        assistant_message = result["result"]
        st.session_state["deepseek_chat_messages"].append(
            {"role": "assistant", "content": assistant_message}
        )
        st.session_state["deepseek_chat_last_model"] = {
            "requested": result.get("model", ""),
            "returned": result.get("response_model", ""),
        }
        st.session_state["deepseek_chat_last_error"] = ""
    else:
        error_message = result.get("error", "未知错误") if result else "未知错误"
        st.session_state["deepseek_chat_last_error"] = error_message


def _queue_chat_prompt(prompt: str) -> None:
    """Store a prompt so the next rerun can process it before rendering history."""
    cleaned_prompt = prompt.strip()
    if cleaned_prompt:
        st.session_state["deepseek_chat_pending_prompt"] = cleaned_prompt


def _process_pending_chat_prompt() -> None:
    """Process a queued prompt and keep the rendered chat window in sync."""
    pending_prompt = st.session_state.get("deepseek_chat_pending_prompt", "").strip()
    if not pending_prompt:
        return

    st.session_state["deepseek_chat_pending_prompt"] = ""
    with st.spinner("DeepSeek 正在回复..."):
        _run_chat_turn(pending_prompt)


def render_chat_tab() -> None:
    """Render the DeepSeek chat experience."""
    cfg = get_config()
    configured_model = str(cfg["deepseek_chat_model"]).strip()
    _process_pending_chat_prompt()
    history_count = len(st.session_state.get("deepseek_chat_messages", []))
    last_model = st.session_state.get("deepseek_chat_last_model") or {}
    requested_model = str(last_model.get("requested") or configured_model)
    returned_model = str(last_model.get("returned") or "等待首次返回")

    st.markdown(
        f"""
        <div class="chatbox-hero">
            <div class="chatbox-hero-title">💬 DeepSeek 聊天</div>
            <div class="chatbox-hero-text">
                这里是独立的聊天入口，更适合追问、解释、对比和自由交流。
            </div>
            <div class="chatbox-meta-row">
                <span class="chatbox-meta-pill">锁定模型：{html.escape(configured_model)}</span>
                <span class="chatbox-meta-pill">请求模型：{html.escape(requested_model)}</span>
                <span class="chatbox-meta-pill">返回模型：{html.escape(returned_model)}</span>
                <span class="chatbox-meta-pill">上下文：全部会话（{history_count} 条）</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if (
        constants.DEEPSEEK_CHAT_MODEL_BLOCKED_FRAGMENT in configured_model.lower()
        or not configured_model.lower().startswith(constants.DEEPSEEK_CHAT_MODEL_REQUIRED_PREFIX)
    ):
        st.error(
            f"当前聊天模型配置为 `{configured_model}`，聊天板块只允许 "
            f"`{constants.DEEPSEEK_CHAT_MODEL_REQUIRED_PREFIX}` 系列模型。"
        )
    st.caption(
        "如需单独配置，请在 `.streamlit/secrets.toml` 中设置 "
        "`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_CHAT_MODEL`。"
    )

    col_title, col_clear = st.columns([4, 1])
    with col_title:
        st.markdown("#### 对话区")
    with col_clear:
        if st.button("清空对话", key="btn_clear_deepseek_chat", use_container_width=True):
            st.session_state["deepseek_chat_messages"] = []
            st.session_state["deepseek_chat_last_model"] = {}
            st.session_state["deepseek_chat_pending_prompt"] = ""
            st.session_state["deepseek_chat_last_error"] = ""
            st.rerun()

    with st.container(height=520, border=True):
        st.markdown('<div class="chatbox-scroll-anchor"></div>', unsafe_allow_html=True)
        if not st.session_state.get("deepseek_chat_messages"):
            st.markdown(
                """
                <div class="chatbox-empty">
                    <strong>像聊天框一样直接输入问题就行。</strong><br>
                    你也可以先点下面的示例问题开始。
                </div>
                """,
                unsafe_allow_html=True,
            )

            starter_cols = st.columns(len(STARTER_PROMPTS))
            for index, starter_prompt in enumerate(STARTER_PROMPTS):
                with starter_cols[index]:
                    if st.button(starter_prompt, key=f"deepseek_starter_{index}", use_container_width=True):
                        _queue_chat_prompt(starter_prompt)
                        st.rerun()

        _render_chat_history()
        if st.session_state.get("deepseek_chat_last_error"):
            st.error(f"❌ 回复失败：{st.session_state['deepseek_chat_last_error']}")
            st.caption("如果这是首次使用，请先配置 `DEEPSEEK_API_KEY`，必要时再配置 `DEEPSEEK_BASE_URL`。")

    st.markdown('<div class="chatbox-composer-anchor"></div>', unsafe_allow_html=True)
    with st.form("deepseek_chat_composer", clear_on_submit=True):
        col_input, col_send = st.columns([5, 1])
        with col_input:
            chat_prompt = st.text_input(
                "输入你想和 DeepSeek 聊的内容",
                placeholder="输入消息，按 Enter 或点击发送",
                label_visibility="collapsed",
                autocomplete="off",
            )
        with col_send:
            submitted = st.form_submit_button("发送", type="primary", use_container_width=True)

    if submitted and chat_prompt.strip():
        _queue_chat_prompt(chat_prompt)
        st.rerun()
