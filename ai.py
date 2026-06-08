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
        if cleaned in {"喵～", "喵~"}:
            continue
        cleaned = re.sub(r"\*\*(.+?)\*\*", r"\1", cleaned).strip()
        if cleaned:
            match = re.match(r"([A-Za-z][A-Za-z' -]*?)(?:\s+/|\s+\(|$)", cleaned)
            if match:
                return re.sub(r"\s+", " ", match.group(1)).strip().lower()
            return cleaned.lower()
    return ""


def _looks_like_missing_lookup_input(raw_content: str) -> bool:
    lowered = str(raw_content or "").strip().lower()
    missing_input_markers = (
        "please provide the word",
        "please provide a word",
        "please provide the phrase",
        "provide the word, phrase",
        "word, phrase, or chinese meaning",
        "请输入",
        "请提供",
    )
    return any(marker in lowered for marker in missing_input_markers)


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


def _normalize_definition_language(value: str) -> str:
    """Normalize card definition-language options from UI."""
    if value in {"英文", "english", "en"}:
        return "英文"
    if value in {"中英", "bilingual", "both"}:
        return "中英"
    return "中文"


def _definition_instruction(definition_language: str) -> str:
    """Build the prompt rule for the card meaning field."""
    if definition_language == "英文":
        return "English only, concise, under 10 words. Do not include Chinese."
    if definition_language == "中英":
        return "Simplified Chinese + short English definition, format: 中文释义 | English definition under 8 words."
    return "Concise Simplified Chinese only."


def get_word_quick_definition(word: str) -> Dict[str, Any]:
    """Get an etymology-only dictionary note for one word or phrase."""
    vocab_dict = get_vocab_dict()
    model_name = get_ai_model()
    system_prompt = """You are a strict English etymology explainer for a Chinese-speaking learner.

Task:
Return only the etymology for exactly one English word or short English phrase.

Output language:
- Use Simplified Chinese for the explanation.
- Keep the label exactly in English: 🌱 Etymology:

Hard rules:
- Return plain text only. Do not use HTML, Markdown tables, code fences, example sentences, or extra notes.
- The user's message contains the lookup input. Never ask the user to provide a word.
- If the input is a plain word such as "developer", format that word directly.
- Do not output pronunciation, definitions, part of speech, collocations, or example sentences.
- Explain where the word comes from, such as Latin, Greek, Old English, Old Norse, French, or its root, prefix, or suffix.
- Make the etymology richer than a one-line note: include the earliest known source, the original concrete image or cultural scene, and how the meaning changed into modern English.
- If there are two common etymology explanations, mention both and say which one is more widely accepted.
- Keep it readable and useful, normally 1-3 short Chinese paragraphs.
- If the etymology is unclear or not useful, write exactly: 🌱 Etymology: 词源不明显，重点记住常用含义即可。

Output exactly in this format:
🌱 Etymology:
Chinese etymology explanation only.

Reference example:
🌱 Etymology:
April 的词源通常追溯到拉丁语 Aprilis。较流行的解释认为它和拉丁语 aperire（to open，打开）有关，因为四月是春天真正展开的月份：树木抽芽、花朵开放，万物像被“打开”一样进入生长期。

另一种说法认为 Aprilis 可能与希腊神话中的爱与美之神 Aphrodite 有关，因为古罗马月份名常和神话、祭祀传统相连。相比之下，aperire 这个解释更容易记忆，也更符合“四月万物开放”的画面。
"""

    normalized_word = str(word or "").strip()
    if not normalized_word:
        return {"error": "Lookup input is required"}
    user_prompt = f"""Input term:
{normalized_word}

Write only the etymology note for the input term above. Do not ask for another word."""

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
        if _looks_like_missing_lookup_input(content):
            retry_prompt = f"""The input term is "{normalized_word}".

Return only its etymology in the required format now. Do not ask for input."""
            response = _call_ai_chat_completion(
                model_name,
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": retry_prompt}
                ],
                0.2
            )
            if "error" in response:
                return {"error": response["error"]}
            content = response.get("content", "")
        headword = extract_lookup_headword(content)
        if not headword or headword.startswith("🌱"):
            headword = normalized_word.lower()
        rank = vocab_dict.get(headword, 99999)
        return {"result": content, "rank": rank, "headword": headword, "is_question": False}

    except Exception as e:
        logger.error("Error getting definition: %s", e)
        return {"error": str(e)}


def answer_english_learning_question(question: str) -> Dict[str, Any]:
    """Answer a standalone English-learning question."""
    model_name = get_ai_model()
    normalized_question = str(question or "").strip()
    if not normalized_question:
        return {"error": "Question is required"}

    system_prompt = """You are a practical English AI assistant for a Chinese-speaking learner.

Task:
Replace the user's daily English-related AI questions. The user may ask about word usage, differences between words, grammar, translation, polishing, sentence correction, rewriting, pronunciation, collocations, examples, email wording, spoken English, or study wording.

Rules:
- Answer in Simplified Chinese by default.
- Use English examples when helpful.
- Be practical and direct; give the key answer first.
- Infer the user's intent automatically; do not ask the user to choose a category.
- For word comparisons, explain the main difference, then give examples.
- For grammar questions, name the pattern, explain when to use it, and give examples.
- For sentence correction or rewriting, show the corrected English sentence first, then explain briefly.
- For translation requests, provide natural English and mention a more formal or casual option only if useful.
- For example requests, include short Chinese translations when useful.
- Prefer answers that the user can reuse immediately.
- Do not answer non-English-learning tasks.
- Do not output HTML, Markdown tables, code fences, or long essays.
- Keep the answer concise and easy to scan."""

    try:
        response = _call_ai_chat_completion(
            model_name,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": normalized_question},
            ],
            0.3,
        )
        if "error" in response:
            return {"error": response["error"]}
        return {"result": response.get("content", "")}
    except Exception as e:
        logger.error("Error answering English question: %s", e)
        return {"error": str(e)}


def generate_topic_word_list(topic: str, count: int) -> Dict[str, Any]:
    """Generate a topic-based English word list from a topic and desired count."""
    model_name = get_ai_model()
    normalized_topic = " ".join(str(topic).split()).strip()
    if not normalized_topic:
        return {"error": "Topic is required"}

    normalized_count = max(1, min(int(count), constants.AI_TOPIC_WORDLIST_MAX))

    system_prompt = f"""You are an English topic vocabulary generator.

Task:
Generate a common, practical, high-frequency English vocabulary list for the given topic.

Rules:
- Generate no more than {constants.AI_TOPIC_WORDLIST_MAX} items.
- Output only one ```text code block.
- One English word or phrase per line.
- Use lowercase only.
- Do not number the lines.
- Do not use bullet points.
- Do not output Chinese.
- Do not add explanations.
- Do not add category headings.
- Prefer common, useful, high-frequency vocabulary.
- Prefer single words; use short phrases only when they are very common.
- Do not repeat items.

Output format:

```text
word
short phrase
another word
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


def _normalize_selection_item(value: str) -> str:
    """Normalize a vocabulary candidate for matching AI output back to input."""
    text = re.sub(r"^[\s>*•◆◇●○\-–—]+", "", str(value or "")).strip()
    text = re.sub(r"^\d+[.)]\s*", "", text).strip()
    text = re.sub(r"\s+", " ", text)
    text = text.strip(" \r\n,;:，。；：.!?！？\"“”‘’")
    text = re.sub(r"\s*\([^)]*\)\s*$", "", text).strip()
    return text.lower()


def _parse_ai_word_block(raw_text: str) -> List[str]:
    """Parse one AI-returned word code block into clean lines."""
    words = []
    for raw_line in str(raw_text or "").splitlines():
        cleaned = re.sub(r"^[\s>*•◆◇●○\-–—]+", "", raw_line).strip()
        cleaned = re.sub(r"^\d+[.)]\s*", "", cleaned).strip()
        cleaned = cleaned.strip(" \r\n,;:，。；：.!?！？\"“”‘’")
        if cleaned and not re.fullmatch(r"(?i)(selected|remaining|rest|筛选|剩余)[:：]?", cleaned):
            words.append(cleaned)
    return words


def select_priority_words(candidates: List[str], target_count: int) -> Dict[str, Any]:
    """Use AI to select the most worthwhile words to learn first."""
    normalized_candidates = []
    seen_candidates = set()
    for candidate in candidates:
        cleaned = str(candidate or "").strip()
        normalized = _normalize_selection_item(cleaned)
        if cleaned and normalized and normalized not in seen_candidates:
            seen_candidates.add(normalized)
            normalized_candidates.append(cleaned)

    if not normalized_candidates:
        return {"error": "No candidate words"}

    target_count = max(1, min(int(target_count), len(normalized_candidates), constants.AI_WORD_SELECTION_MAX_OUTPUT))
    model_name = get_ai_model()
    candidate_text = "\n".join(f"{idx + 1}. {word}" for idx, word in enumerate(normalized_candidates))

    system_prompt = """You are a strict English vocabulary prioritizer for a Chinese-speaking learner.

Task:
From a messy list of English words and phrases, select the target number of items that are most worth learning first.

Priority rules:
- Higher priority: common, general-purpose, useful, reusable, easy or concrete words and phrases.
- Simpler and more common items should rank higher than rare or specialized items.
- Medium priority: useful academic, workplace, health, news, or daily-life words.
- Lower priority: proper nouns, brands, organizations, acronyms, sports-only terms, very technical terms, very rare words, chapter headings, duplicates, misspellings, and noisy fragments.
- Keep multi-word phrases only when they are genuinely useful expressions.
- Preserve the exact candidate wording when possible.

Output rules:
- Output exactly two fenced ```text code blocks.
- The first code block contains the selected items, one per line.
- The second code block contains the remaining valid items, one per line.
- Do not number the lines.
- Do not use bullets.
- Do not add explanations.
- Do not output anything except the two code blocks."""

    user_prompt = f"""Target selected count: {target_count}

Candidate list:
{candidate_text}"""

    try:
        response = _call_ai_chat_completion(
            model_name,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            0.2,
        )
        if "error" in response:
            return {"error": response["error"]}

        content = response.get("content", "")
        code_blocks = re.findall(r"```(?:text)?\s*(.*?)```", content, flags=re.IGNORECASE | re.DOTALL)
        selected_lines = _parse_ai_word_block(code_blocks[0] if code_blocks else content)

        candidate_by_norm = {_normalize_selection_item(word): word for word in normalized_candidates}
        selected = []
        selected_norms = set()
        for line in selected_lines:
            normalized = _normalize_selection_item(line)
            if normalized in candidate_by_norm and normalized not in selected_norms:
                selected_norms.add(normalized)
                selected.append(candidate_by_norm[normalized])
            if len(selected) >= target_count:
                break

        for candidate in normalized_candidates:
            normalized = _normalize_selection_item(candidate)
            if len(selected) >= target_count:
                break
            if normalized not in selected_norms:
                selected_norms.add(normalized)
                selected.append(candidate)

        remaining = [
            candidate
            for candidate in normalized_candidates
            if _normalize_selection_item(candidate) not in selected_norms
        ]

        return {
            "result": content,
            "selected": selected,
            "remaining": remaining,
        }
    except Exception as e:
        logger.error("Error selecting priority words: %s", e)
        return {"error": str(e)}


def process_ai_in_batches(
    words_list: List[str],
    example_count: int = constants.AI_CARD_EXAMPLE_COUNT_DEFAULT,
    definition_language: str = "中文",
    translate_examples: bool = True,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    card_template: str = constants.DEFAULT_CARD_TEMPLATE,
) -> Optional[str]:
    """Process words in batches using AI with progress reporting."""
    words_list = words_list[:constants.MAX_AUTO_LIMIT]
    example_count = max(
        constants.AI_CARD_EXAMPLE_COUNT_MIN,
        min(int(example_count), constants.AI_CARD_EXAMPLE_COUNT_MAX)
    )
    definition_language = _normalize_definition_language(definition_language)
    definition_rule = _definition_instruction(definition_language)
    template_specific_rules = ""
    if card_template == "definition_front":
        definition_rule = (
            "Use exactly this inner format: English part of speech | Simplified Chinese meaning | "
            "English-only definition under 12 words. The third inner part is shown on the card front, "
            "so it must be English only, must contain no Chinese characters, and must not contain the target word or phrase. "
            "Use English part-of-speech names only, such as noun, verb, adjective, adverb, or phrase. "
            "Example: noun | 活力；生命力 | energy and strong life force."
        )
        template_specific_rules = """
Template 3 strict rules:
- Field 3 must contain exactly three inner parts separated by two single | characters:
  English part of speech | Simplified Chinese meaning | English-only definition
- The card front uses the third inner part, so the third inner part must be English only.
- Never put Chinese text, Chinese punctuation, or Chinese translation in the third inner part.
- Never include the target word, target phrase, or main content word from the target phrase in the third inner part.
- Never use Chinese part-of-speech labels such as 名词 or 动词; use noun, verb, adjective, adverb, phrase, etc.
- If unsure, write a simple English definition instead of a Chinese explanation.
"""
    translation_rule = (
        "Translate field 4 sentence by sentence into Simplified Chinese."
        if translate_examples
        else "Leave this field empty. Keep the field separator, but write no text in this field."
    )
    translation_count_rule = (
        f"Field 5 contains exactly {example_count} Chinese translation(s), matching field 4 in order."
        if translate_examples
        else "Field 5 is empty."
    )

    model_name = get_ai_model()
    total_words = len(words_list)
    full_results = []
    failed_batches: list[str] = []

    system_prompt = "You are a strict Anki vocabulary card generator."

    for i in range(0, total_words, constants.AI_BATCH_SIZE):
        batch = words_list[i:i + constants.AI_BATCH_SIZE]
        current_batch_str = "\n".join(batch)

        user_prompt = f"""Task:
Convert the input word or phrase list into Anki card data.
The selected card template is: {constants.CARD_TEMPLATES.get(card_template, constants.CARD_TEMPLATES[constants.DEFAULT_CARD_TEMPLATE])["label"]}.

Input items:
{current_batch_str}

Output rules:
- Output only one ```text code block.
- One input item per line.
- Each line must contain exactly 6 fields.
- Fields must be separated only by |||.
- Do not number the lines.
- Do not add explanations.
- Do not omit any input item.
- Do not merge multiple input items.
- Preserve the input order.
- Do not output anything outside the code block.

Field format:
Word/Phrase ||| Pronunciation ||| Meaning ||| English Example(s) ||| Example Translation(s) ||| Etymology

Field requirements:
1. Word/Phrase: English word or phrase, preferably lowercase.
2. Pronunciation: must follow exactly this format: 美 /.../；英 /.../
3. Meaning: {definition_rule}
4. English Example(s): generate exactly {example_count} natural and short English example sentence(s).
5. Example Translation(s): {translation_rule}
6. Etymology: briefly explain root, affix, or origin in Simplified Chinese.

If {example_count}=1:
- Field 4 contains exactly 1 English sentence.
- {translation_count_rule}

If {example_count}>1:
- Field 4 joins the English sentences with <br>.
- If translations are enabled, field 5 joins the Chinese translations with <br>.
- Translation order must match the English examples when field 5 is not empty.

Final check:
Each line must contain exactly 5 occurrences of |||.
Each line must contain both US and UK pronunciation.
Field 4 must contain exactly {example_count} English example sentence(s).
{translation_count_rule}
For template 3, the English definition shown on the card front must not contain the target word or phrase.
{template_specific_rules}
Output only the text code block."""

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
