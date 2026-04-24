"""DeepSeek chat tab rendering."""

import streamlit as st

from ai import chat_with_deepseek
from config import get_config


def _render_chat_history() -> None:
    """Render stored chat history."""
    for message in st.session_state.get("deepseek_chat_messages", []):
        role = message.get("role")
        if role not in {"user", "assistant"}:
            continue
        with st.chat_message(role):
            st.markdown(message.get("content", ""))


def render_chat_tab() -> None:
    """Render the DeepSeek chat experience."""
    cfg = get_config()

    st.markdown("### 💬 DeepSeek 聊天")
    st.caption(
        f"这个板块独立调用 DeepSeek 聊天模型，当前默认使用 {cfg['deepseek_chat_model']}。"
        "如需单独配置，请在 `.streamlit/secrets.toml` 中设置 "
        "`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_CHAT_MODEL`。"
    )

    col_model, col_clear = st.columns([4, 1])
    with col_model:
        st.markdown(f"当前聊天模型：**{cfg['deepseek_chat_model']}**")
    with col_clear:
        if st.button("清空对话", key="btn_clear_deepseek_chat", use_container_width=True):
            st.session_state["deepseek_chat_messages"] = []
            st.rerun()

    if not st.session_state.get("deepseek_chat_messages"):
        st.caption("例如：帮我区分 affect 和 effect；给我 5 个 travel 相关短语；解释 present perfect 的用法。")

    _render_chat_history()

    prompt = st.chat_input("输入你想和 DeepSeek 聊的内容", key="deepseek_chat_input")
    if not prompt:
        return

    user_message = prompt.strip()
    if not user_message:
        return

    st.session_state["deepseek_chat_messages"].append({"role": "user", "content": user_message})

    with st.chat_message("user"):
        st.markdown(user_message)

    with st.chat_message("assistant"):
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
