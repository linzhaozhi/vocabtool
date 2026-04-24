"""DeepSeek chat tab rendering."""

import streamlit as st

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
        avatar = "🙂" if role == "user" else "DS"
        with st.chat_message(role, avatar=avatar):
            st.markdown(message.get("content", ""))


def _run_chat_turn(prompt: str) -> None:
    """Handle one user prompt and append the assistant response."""
    user_message = prompt.strip()
    if not user_message:
        return

    st.session_state["deepseek_chat_messages"].append({"role": "user", "content": user_message})

    with st.chat_message("user", avatar="🙂"):
        st.markdown(user_message)

    with st.chat_message("assistant", avatar="DS"):
        with st.spinner("DeepSeek 正在回复..."):
            result = chat_with_deepseek(st.session_state["deepseek_chat_messages"])

        if result and "error" not in result:
            assistant_message = result["result"]
            st.markdown(assistant_message)
            st.session_state["deepseek_chat_messages"].append(
                {"role": "assistant", "content": assistant_message}
            )
        else:
            error_message = result.get("error", "未知错误") if result else "未知错误"
            st.error(f"❌ 回复失败：{error_message}")
            st.caption("如果这是首次使用，请先配置 `DEEPSEEK_API_KEY`，必要时再配置 `DEEPSEEK_BASE_URL`。")


def render_chat_tab() -> None:
    """Render the DeepSeek chat experience."""
    cfg = get_config()

    st.markdown(
        f"""
        <div class="chatbox-hero">
            <div class="chatbox-hero-title">💬 DeepSeek 聊天</div>
            <div class="chatbox-hero-text">
                这里是独立的聊天入口，更适合追问、解释、对比和自由交流。
            </div>
            <div class="chatbox-meta-row">
                <span class="chatbox-meta-pill">当前模型：{cfg['deepseek_chat_model']}</span>
                <span class="chatbox-meta-pill">独立于查词 / 提词 / 制卡</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
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
            st.rerun()

    prompt_to_send = ""
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
                    prompt_to_send = starter_prompt

    _render_chat_history()

    chat_prompt = st.chat_input("输入你想和 DeepSeek 聊的内容", key="deepseek_chat_input")
    if chat_prompt and chat_prompt.strip():
        prompt_to_send = chat_prompt.strip()

    st.caption("按 Enter 发送。这里适合自由聊天、追问、举例、对比和语法解释。")

    if prompt_to_send:
        _run_chat_turn(prompt_to_send)
