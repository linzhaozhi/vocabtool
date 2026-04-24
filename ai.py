# AI-backed word definitions and batch card generation.

import logging
import time
from typing import Any, Callable, Dict, List, Optional

import requests
import streamlit as st

import constants
from config import get_config
from errors import ErrorHandler
from resources import get_vocab_dict

logger = logging.getLogger(__name__)


def extract_lookup_headword(raw_content: str) -> str:
    """Extract the first non-empty line as the canonical English lookup headword."""
    for line in raw_content.splitlines():
        cleaned = line.strip().strip("`")
        if cleaned:
            return cleaned.lower()
    return ""


def _call_deepseek_chat_completion(
    model_name: str,
    messages: List[Dict[str, str]],
    temperature: float,
) -> Dict[str, Any]:
    """Call DeepSeek's chat completions API directly."""
    cfg = get_config()
    api_key = cfg["deepseek_api_key"]
    if not api_key:
        st.error("❌ 未找到 DEEPSEEK_API_KEY。请在 .streamlit/secrets.toml 中配置。")
        return {"error": "DeepSeek API key not available"}

    try:
        response = requests.post(
            f"{cfg['deepseek_base_url'].rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
            },
            timeout=constants.DEEPSEEK_REQUEST_TIMEOUT_SECONDS,
        )
        try:
            response_data = response.json()
        except ValueError:
            response_data = {}

        if response.status_code >= 400:
            error_detail = response_data.get("error", response.text)
            return {"error": f"DeepSeek API {response.status_code}: {error_detail}"}

        content = response_data["choices"][0]["message"]["content"]
        return {
            "content": content,
            "model": response_data.get("model", model_name),
            "base_url": cfg["deepseek_base_url"],
        }
    except Exception as e:
        logger.error("DeepSeek API request failed: %s", e)
        return {"error": str(e)}


def get_deepseek_model() -> str:
    """Return the shared DeepSeek model used by lookup, topic lists, and cards."""
    return str(get_config()["deepseek_model"]).strip()


def get_deepseek_chat_model() -> str:
    """Return the DeepSeek model used by the chat tab."""
    return str(get_config()["deepseek_chat_model"]).strip()


def _is_allowed_deepseek_chat_model(model_name: str) -> bool:
    """Only allow the configured DeepSeek chat model family for the chat tab."""
    normalized_model = model_name.strip().lower()
    return (
        normalized_model.startswith(constants.DEEPSEEK_CHAT_MODEL_REQUIRED_PREFIX)
        and constants.DEEPSEEK_CHAT_MODEL_BLOCKED_FRAGMENT not in normalized_model
    )


def get_word_quick_definition(word: str) -> Dict[str, Any]:
    """Get ultra-concise word definition using AI, with rank info."""
    vocab_dict = get_vocab_dict()
    model_name = get_deepseek_model()

    system_prompt = """# Role
Atomic Dictionary.

# Goal
Output ONE core meaning, US/UK phonetics, ONE etymology, and TWO matching examples.

# Input Understanding
- The user input may be an English word/phrase OR a short Chinese gloss.
- If the input is Chinese, infer the most natural English target word/phrase first.
- Line 1 must ALWAYS be the final English word/phrase in lowercase.
- Line 2 must ALWAYS contain both US and UK phonetics.

# Critical Constraint: ATOMIC SINGLE SENSE
- **Force Single Sense**: Regardless of how many meanings a word has, pick ONLY the #1 most common one.
- **Strict Alignment**: The Definition, Etymology, and BOTH Examples must strictly support this single meaning.
- **Format**: Follow the 6-line structure below perfectly.

# Output Format
[word] (lowercase)
🔊 美 /US IPA/；英 /UK IPA/
[CN Meaning] | [Short EN Definition (<8 words)]
🌱 词源: [root (CN) + affix (CN)] (Explain origin briefly)
• [English Example 1] ([CN Trans])
• [English Example 2] ([CN Trans])

# Few-Shot Examples (Demonstrating Selection)
**User Input:**
spring

**Model Output:**
spring
🔊 美 /sprɪŋ/；英 /sprɪŋ/
春天 | The season after winter
🌱 词源: spring- (涌出/生长) → 万物复苏
• Flowers bloom in spring. (花朵在春天绽放。)
• I love the fresh air of spring. (我喜欢春天清新的空气。)

**User Input:**
date

**Model Output:**
date
🔊 美 /deɪt/；英 /deɪt/
日期 | Specific day of the month
🌱 词源: dat- (给予/指定) + -e (名词后缀)
• What is today's date? (今天是几号？)
• Please sign and date the form. (请在表格上签名并注明日期的。)

**User Input:**
express

**Model Output:**
express
🔊 美 /ɪkˈspres/；英 /ɪkˈspres/
表达；表示 | Convey a thought or feeling
🌱 词源: ex- (向外) + press (压/挤)
• She expressed her thanks to us. (她向我们表达了谢意。)
• Words cannot express my feelings. (言语无法表达我的感受。)"""

    user_prompt = word

    try:
        response = _call_deepseek_chat_completion(
            model_name,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            0.3
        )
        if "error" in response:
            return {"error": response["error"]}

        content = response.get("content", "")
        headword = extract_lookup_headword(content)
        rank = vocab_dict.get(headword, 99999)
        return {"result": content, "rank": rank, "headword": headword}

    except Exception as e:
        logger.error("Error getting definition: %s", e)
        return {"error": str(e)}


def generate_topic_word_list(topic: str, count: int) -> Dict[str, Any]:
    """Generate a topic-based English word list from a topic and desired count."""
    model_name = get_deepseek_model()
    normalized_topic = " ".join(str(topic).split()).strip()
    if not normalized_topic:
        return {"error": "Topic is required"}

    normalized_count = max(1, min(int(count), constants.AI_TOPIC_WORDLIST_MAX))

    system_prompt = f"""# Role
Topic Vocabulary Curator.

# Goal
Create a practical English word list for the given topic.

# Input
- The topic may be in Chinese or English.
- The target length is provided separately.
- Never generate more than {constants.AI_TOPIC_WORDLIST_MAX} entries.

# Output Rules
- Output strictly inside one ```text code block.
- One entry per line.
- English only.
- lowercase only.
- No numbering.
- No bullets.
- No Chinese.
- No explanations, headings, labels, or categories.
- Prefer single words; use very short phrases only when they are clearly common and useful.

# Quality Standard
- Choose common, practical, high-frequency vocabulary tied closely to the topic.
- Avoid obscure, literary, or overly technical words unless the topic clearly requires them.

# Example
Topic: travel
Count: 12
Output:
```text
travel
trip
ticket
hotel
flight
passport
luggage
map
train
airport
booking
tour
```"""

    try:
        response = _call_deepseek_chat_completion(
            model_name,
            [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"Topic: {normalized_topic}\nCount: {normalized_count}"
                }
            ],
            0.4
        )
        if "error" in response:
            return {"error": response["error"]}

        content = response.get("content", "")
        return {"result": content}

    except Exception as e:
        logger.error("Error generating topic word list: %s", e)
        return {"error": str(e)}


def chat_with_deepseek(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """Send a multi-turn chat request to DeepSeek's chat model."""
    model_name = get_deepseek_chat_model()
    if not _is_allowed_deepseek_chat_model(model_name):
        return {
            "error": (
                f"DeepSeek 聊天已锁定 {constants.DEEPSEEK_CHAT_MODEL_REQUIRED_PREFIX} 系列模型，"
                f"当前配置是 {model_name or '空'}。请不要配置为 pro。"
            ),
            "model": model_name,
        }
    normalized_messages: List[Dict[str, str]] = []

    for message in messages:
        role = str(message.get("role", "")).strip()
        content = str(message.get("content", "")).strip()
        if role in {"system", "user", "assistant"} and content:
            normalized_messages.append({"role": role, "content": content})

    if not normalized_messages:
        return {"error": "No chat messages provided"}

    if not any(message["role"] == "system" for message in normalized_messages):
        normalized_messages.insert(
            0,
            {
                "role": "system",
                "content": (
                    "你是 DeepSeek 聊天助手。回答时尽量清晰、直接、自然；"
                    "用户用中文就优先用中文回答，需要时可以补充简短英文。"
                ),
            },
        )

    try:
        response = _call_deepseek_chat_completion(model_name, normalized_messages, 0.7)
        if "error" in response:
            return {"error": response["error"], "model": model_name}

        content = response.get("content", "")
        if not content:
            return {"error": "DeepSeek 返回了空内容"}
        response_model = str(response.get("model", "") or "").strip()
        if response_model and not _is_allowed_deepseek_chat_model(response_model):
            return {
                "error": (
                    f"DeepSeek 返回的实际模型是 {response_model}，不是 "
                    f"{constants.DEEPSEEK_CHAT_MODEL_REQUIRED_PREFIX} 系列。请检查平台模型映射。"
                ),
                "model": model_name,
                "response_model": response_model,
            }
        return {
            "result": content,
            "model": model_name,
            "response_model": response_model or model_name,
            "base_url": response.get("base_url", get_config()["deepseek_base_url"]),
        }
    except Exception as e:
        logger.error("Error chatting with DeepSeek: %s", e)
        return {"error": str(e), "model": model_name}


def process_ai_in_batches(
    words_list: List[str],
    example_count: int = constants.AI_CARD_EXAMPLE_COUNT_DEFAULT,
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> Optional[str]:
    """Process words in batches using AI with progress reporting."""
    words_list = words_list[:constants.MAX_AUTO_LIMIT]
    example_count = max(
        constants.AI_CARD_EXAMPLE_COUNT_MIN,
        min(int(example_count), constants.AI_CARD_EXAMPLE_COUNT_MAX)
    )

    model_name = get_deepseek_model()
    total_words = len(words_list)
    full_results = []

    system_prompt = "You are a helpful assistant for vocabulary learning."
    example_demo = (
        "hectic schedule ||| 美 /ˈhektɪk/；英 /ˈhektɪk/ ||| 忙乱的日程/非常忙碌 ||| "
        "She has a hectic schedule with meetings all day. ||| "
        "她的日程很忙，一整天都排满了会议。 ||| "
        "hect- (持续/习惯 - 希腊语) + -ic (形容词后缀)"
        if example_count == 1 else
        "hectic schedule ||| 美 /ˈhektɪk/；英 /ˈhektɪk/ ||| 忙乱的日程/非常忙碌 ||| "
        "She has a hectic schedule with meetings all day.<br>My week became hectic before the trip. ||| "
        "她的日程很忙，一整天都排满了会议。<br>旅行前我的一周变得非常忙乱。 ||| "
        "hect- (持续/习惯 - 希腊语) + -ic (形容词后缀)"
    )

    for i in range(0, total_words, constants.AI_BATCH_SIZE):
        batch = words_list[i:i + constants.AI_BATCH_SIZE]
        current_batch_str = "\n".join(batch)

        user_prompt = f"""# Role
You are an expert English Lexicographer.
# Input Data
{current_batch_str}

# Output Format Guidelines
1. **Output Container**: Strictly inside a single ```text code block.
2. **Layout**: One entry per line.
3. **Separator**: Use `|||` as the delimiter.
4. **Target Structure**:
   `Word/Phrase` ||| `Pronunciation` ||| `Chinese Definition` ||| `English Example Sentence(s)` ||| `Chinese Translation(s)` ||| `Etymology (Chinese)`

# Field Constraints
1. Field 1: Phrase - Output the target word OR a very short high-frequency collocation (1-3 words max).
2. Field 2: Pronunciation - Output BOTH pronunciations in this exact format: `美 /.../；英 /.../`.
3. Field 3: Definition - **Simplified Chinese Only**. Concise meaning corresponding to the phrase.
4. Field 4: Example - Exactly {example_count} short authentic English sentence(s).
   - If {example_count} is 1, output just 1 sentence.
   - If {example_count} is 2, join the 2 sentences with `<br>`.
5. Field 5: Example Translation - **Simplified Chinese Only**. Must faithfully translate Field 4 in matching order.
   - If {example_count} is 1, output just 1 translation.
   - If {example_count} is 2, join the 2 translations with `<br>`.
6. Field 6: Etymology - **Simplified Chinese Only**. Format: `root (CN meaning) + affix (CN meaning)`.

# Valid Example
Input: hectic
Output:
{example_demo}

# Task
Process the input list strictly.

# Final Checks
- Every line must contain exactly 6 fields separated by `|||`.
- Field 2 must include both `美 /.../` and `英 /.../`.
- Field 5 must translate Field 4, not the isolated word.
- If {example_count} is 2, Field 4 and Field 5 must each contain exactly 2 items separated by `<br>` in matching order.
- Do not omit any input item."""

        for attempt in range(constants.MAX_RETRIES):
            try:
                response = _call_deepseek_chat_completion(
                    model_name,
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    0.4
                )
                if "error" in response:
                    raise RuntimeError(response["error"])

                content = response.get("content", "")
                if not content:
                    raise RuntimeError("DeepSeek 返回了空内容")
                full_results.append(content)

                if progress_callback:
                    processed_count = min(i + constants.AI_BATCH_SIZE, total_words)
                    progress_callback(processed_count, total_words)

                break

            except Exception as e:
                if attempt < constants.MAX_RETRIES - 1:
                    time.sleep(1 + attempt)
                    continue
                else:
                    ErrorHandler.handle(
                        e,
                        f"Batch {i//constants.AI_BATCH_SIZE + 1} failed after {constants.MAX_RETRIES} attempts",
                        show_user=True
                    )

    return "\n".join(full_results)
