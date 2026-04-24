# AI-backed word definitions and batch card generation.

import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional

import streamlit as st

import constants
from config import get_config
from errors import ErrorHandler
from resources import get_vocab_dict

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None
    logger.warning("OpenAI library not available")


def extract_lookup_headword(raw_content: str) -> str:
    """Extract the first non-empty line as the canonical English lookup headword."""
    for line in raw_content.splitlines():
        cleaned = line.strip().strip("`")
        if cleaned:
            return cleaned.lower()
    return ""


def _get_openai_compatible_client(
    api_key: str,
    base_url: str,
    missing_key_message: str,
) -> Optional[Any]:
    """Build an OpenAI-compatible client for OpenAI-style endpoints."""
    if not OpenAI:
        st.error("❌ 未安装 OpenAI 库，无法使用 AI 功能。")
        return None

    if not api_key:
        st.error(missing_key_message)
        return None

    try:
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        return OpenAI(**client_kwargs)
    except Exception as e:
        ErrorHandler.handle(e, "初始化 AI 客户端失败")
        return None


def get_ai_client() -> Optional[Any]:
    """Get the active AI client used by lookup, topics, and cards."""
    cfg = get_config()
    return _get_openai_compatible_client(
        cfg["ai_api_key"],
        cfg["ai_base_url"],
        cfg["ai_missing_key_message"],
    )


def get_openai_client() -> Optional[Any]:
    """Backward-compatible alias for the active AI client."""
    return get_ai_client()


def get_deepseek_client() -> Optional[Any]:
    """Backward-compatible alias for the active AI client."""
    return get_ai_client()


def _sanitize_ai_error(error: Exception) -> str:
    """Return a user-safe AI error message without leaking credentials."""
    raw_message = str(error)
    scrubbed = re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "sk-****", raw_message)
    scrubbed = re.sub(r"(Bearer\s+)[A-Za-z0-9._\-]+", r"\1****", scrubbed, flags=re.IGNORECASE)
    lowered = scrubbed.lower()

    if "401" in scrubbed or "invalid_api_key" in lowered or "incorrect api key" in lowered:
        return "API Key 无效或不属于当前配置的模型服务，请检查 secrets 里的 API Key、Base URL 和模型名。"
    if "timeout" in lowered or "timed out" in lowered:
        return "AI 请求超时，请稍后重试，或减少本次处理的单词数量。"
    if "model" in lowered and ("not found" in lowered or "does not exist" in lowered):
        return "当前模型名不可用，请检查 OPENAI_MODEL / DEEPSEEK_MODEL 配置。"
    return scrubbed


def _call_ai_chat_completion(
    model_name: str,
    messages: List[Dict[str, str]],
    temperature: float,
) -> Dict[str, Any]:
    """Call the active OpenAI-compatible chat completions endpoint."""
    cfg = get_config()
    client = _get_openai_compatible_client(
        cfg["ai_api_key"],
        cfg["ai_base_url"],
        cfg["ai_missing_key_message"],
    )
    if not client:
        return {"error": "AI client not available"}

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=temperature,
            timeout=constants.DEEPSEEK_REQUEST_TIMEOUT_SECONDS,
        )
        content = response.choices[0].message.content
        return {
            "content": content,
            "model": str(getattr(response, "model", "") or model_name),
            "base_url": cfg["ai_base_url"],
            "provider": cfg["ai_provider"],
        }
    except Exception as e:
        logger.error("AI API request failed: %s", e)
        return {"error": _sanitize_ai_error(e)}


def _call_deepseek_chat_completion(
    model_name: str,
    messages: List[Dict[str, str]],
    temperature: float,
) -> Dict[str, Any]:
    """Backward-compatible alias for the active AI chat completion call."""
    return _call_ai_chat_completion(model_name, messages, temperature)


def get_ai_model() -> str:
    """Return the active model used by lookup, topic lists, and cards."""
    return str(get_config()["ai_model"]).strip()


def get_deepseek_model() -> str:
    """Backward-compatible alias for the active AI model."""
    return get_ai_model()


def _count_parseable_cards(raw_text: str) -> int:
    """Count parseable cards without making ai.py depend on UI code."""
    from anki_parse import parse_anki_data

    return len(parse_anki_data(raw_text))


def get_word_quick_definition(word: str) -> Dict[str, Any]:
    """Get ultra-concise word definition using AI, with rank info."""
    vocab_dict = get_vocab_dict()
    model_name = get_ai_model()

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
        response = _call_ai_chat_completion(
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
    model_name = get_ai_model()
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
        response = _call_ai_chat_completion(
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

    model_name = get_ai_model()
    total_words = len(words_list)
    full_results = []
    failed_batches: list[str] = []

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
                response = _call_ai_chat_completion(
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
                    raise RuntimeError("AI 返回了空内容")
                parsed_count = _count_parseable_cards(content)
                if parsed_count < len(batch):
                    raise RuntimeError(
                        f"AI 返回格式不完整：本批 {len(batch)} 个词，只解析到 {parsed_count} 张卡片"
                    )
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
                    failed_batches.append(", ".join(batch))
                    ErrorHandler.handle(
                        e,
                        f"Batch {i//constants.AI_BATCH_SIZE + 1} failed after {constants.MAX_RETRIES} attempts",
                        show_user=True
                    )

    if failed_batches and full_results:
        st.warning(f"⚠️ 有 {len(failed_batches)} 个批次生成失败，已保留成功生成的部分。建议减少词数后重试失败词。")

    return "\n".join(full_results)
