# AI-backed word definitions and batch card generation.

import logging
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


def get_openai_client() -> Optional[Any]:
    """Get configured OpenAI client with proper error handling."""
    if not OpenAI:
        st.error("❌ 未安装 OpenAI 库，无法使用内置 AI 功能。")
        return None

    cfg = get_config()
    api_key = cfg["openai_api_key"]
    if not api_key:
        st.error("❌ 未找到 OPENAI_API_KEY。请在 .streamlit/secrets.toml 中配置。")
        return None

    try:
        return OpenAI(api_key=api_key, base_url=cfg["openai_base_url"])
    except Exception as e:
        ErrorHandler.handle(e, "Failed to initialize OpenAI client")
        return None


def get_word_quick_definition(word: str) -> Dict[str, Any]:
    """Get ultra-concise word definition using AI, with rank info."""
    vocab_dict = get_vocab_dict()

    client = get_openai_client()
    if not client:
        return {"error": "AI client not available"}

    model_name = get_config()["openai_model"]

    system_prompt = """# Role
Atomic Dictionary.

# Goal
Output ONE core meaning, ONE etymology, and TWO matching examples.

# Input Understanding
- The user input may be an English word/phrase OR a short Chinese gloss.
- If the input is Chinese, infer the most natural English target word/phrase first.
- Line 1 must ALWAYS be the final English word/phrase in lowercase.

# Critical Constraint: ATOMIC SINGLE SENSE
- **Force Single Sense**: Regardless of how many meanings a word has, pick ONLY the #1 most common one.
- **Strict Alignment**: The Definition, Etymology, and BOTH Examples must strictly support this single meaning.
- **Format**: Follow the 4-line structure below perfectly.

# Output Format
[word] (lowercase)
[CN Meaning] | [Short EN Definition (<8 words)]
🌱 词源: [root (CN) + affix (CN)] (Explain origin briefly)
• [English Example 1] ([CN Trans])
• [English Example 2] ([CN Trans])

# Few-Shot Examples (Demonstrating Selection)
**User Input:**
spring

**Model Output:**
spring
春天 | The season after winter
🌱 词源: spring- (涌出/生长) → 万物复苏
• Flowers bloom in spring. (花朵在春天绽放。)
• I love the fresh air of spring. (我喜欢春天清新的空气。)

**User Input:**
date

**Model Output:**
date
日期 | Specific day of the month
🌱 词源: dat- (给予/指定) + -e (名词后缀)
• What is today's date? (今天是几号？)
• Please sign and date the form. (请在表格上签名并注明日期的。)

**User Input:**
express

**Model Output:**
express
表达；表示 | Convey a thought or feeling
🌱 词源: ex- (向外) + press (压/挤)
• She expressed her thanks to us. (她向我们表达了谢意。)
• Words cannot express my feelings. (言语无法表达我的感受。)"""

    user_prompt = word

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3
        )

        content = response.choices[0].message.content
        headword = extract_lookup_headword(content)
        rank = vocab_dict.get(headword, 99999)
        return {"result": content, "rank": rank, "headword": headword}

    except Exception as e:
        logger.error("Error getting definition: %s", e)
        return {"error": str(e)}


def generate_topic_word_list(topic: str, count: int) -> Dict[str, Any]:
    """Generate a topic-based English word list from a topic and desired count."""
    client = get_openai_client()
    if not client:
        return {"error": "AI client not available"}

    model_name = get_config()["openai_model"]
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
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"Topic: {normalized_topic}\nCount: {normalized_count}"
                }
            ],
            temperature=0.4
        )

        content = response.choices[0].message.content
        return {"result": content}

    except Exception as e:
        logger.error("Error generating topic word list: %s", e)
        return {"error": str(e)}


def process_ai_in_batches(
    words_list: List[str],
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> Optional[str]:
    """Process words in batches using AI with progress reporting."""
    words_list = words_list[:constants.MAX_AUTO_LIMIT]

    client = get_openai_client()
    if not client:
        return None

    model_name = get_config()["openai_model"]
    total_words = len(words_list)
    full_results = []

    system_prompt = "You are a helpful assistant for vocabulary learning."

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
   `Word/Phrase` ||| `Chinese Definition` ||| `Short English Example Sentence` ||| `Chinese Translation of the Example` ||| `Etymology (Chinese)`

# Field Constraints
1. Field 1: Phrase - Output the target word OR a very short high-frequency collocation (1-3 words max).
2. Field 2: Definition - **Simplified Chinese Only**. Concise meaning corresponding to the phrase.
3. Field 3: Example - Short authentic English sentence.
4. Field 4: Example Translation - **Simplified Chinese Only**. Must be a faithful translation of Field 3.
5. Field 5: Etymology - **Simplified Chinese Only**. Format: `root (CN meaning) + affix (CN meaning)`.

# Valid Example
Input: hectic
Output:
hectic schedule ||| 忙乱的日程/非常忙碌 ||| She has a hectic schedule with meetings all day. ||| 她的日程很忙，一整天都排满了会议。 ||| hect- (持续/习惯 - 希腊语) + -ic (形容词后缀)

Input: altruism
Output:
altruism ||| 利他主义/无私 ||| Motivated by altruism, he donated anonymously. ||| 出于利他精神，他匿名捐了款。 ||| alter (其他) + -ism (主义/行为)

# Task
Process the input list strictly.

# Final Checks
- Every line must contain exactly 5 fields separated by `|||`.
- Field 4 must translate Field 3, not the isolated word.
- Do not omit any input item."""

        for attempt in range(constants.MAX_RETRIES):
            try:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.4
                )
                content = response.choices[0].message.content
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
