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


def _target_occurrence_count(sentence: str, target: str) -> int:
    """Count exact target occurrences in one generated example sentence."""
    target = re.sub(r"\s+", " ", str(target or "").strip())
    if not target:
        return 0
    if " " in target:
        return len(re.findall(rf"(?<![A-Za-z0-9]){re.escape(target)}(?![A-Za-z0-9])", sentence, re.IGNORECASE))
    return len(re.findall(rf"(?<![A-Za-z0-9]){re.escape(target)}(?![A-Za-z0-9])", sentence, re.IGNORECASE))


def _looks_like_weak_example(sentence: str, target: str) -> bool:
    """Reject vague examples that do not reveal what the target means."""
    sentence_clean = re.sub(r"\s+", " ", str(sentence or "").strip())
    lowered = sentence_clean.lower().strip(" .")
    target_escaped = re.escape(str(target or "").strip().lower())
    if not lowered or not target_escaped:
        return True

    weak_patterns = (
        rf"^(i|we|they|he|she)\s+(visited|saw|found|noticed|liked|used|bought|checked)\s+.*\b{target_escaped}\b.*\b(yesterday|today|last\s+week|last\s+weekend)\b",
        rf"^(i|we|they|he|she)\s+(visited|saw|found|noticed|liked)\s+(a|an|the|my|our)?\s*(local|nearby|new|old|small|big)?\s*\b{target_escaped}\b$",
        rf"^(this|that|it)\s+is\s+(a|an|the)?\s*\b{target_escaped}\b$",
        rf"^there\s+(is|was|are|were)\s+(a|an|the)?\s*\b{target_escaped}\b",
        rf"^the\s+\b{target_escaped}\b\s+(is|was)\s+(nice|good|bad|important|useful|common|popular)$",
    )
    return any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in weak_patterns)


def _validate_definition_front_examples(raw_text: str) -> Optional[str]:
    """Validate template-3 examples before accepting an AI batch."""
    from anki_parse import parse_anki_data

    cards = parse_anki_data(raw_text)
    for card in cards:
        phrase = str(card.get("w", "")).strip()
        examples = [
            re.sub(r"\s+", " ", item).strip()
            for item in re.split(r"<br\s*/?>", str(card.get("e", "")), flags=re.IGNORECASE)
            if re.sub(r"\s+", " ", item).strip()
        ]
        if len(examples) != 1:
            return f"{phrase} 必须生成 1 个英文例句"
        for index, sentence in enumerate(examples, start=1):
            count = _target_occurrence_count(sentence, phrase)
            if count != 1:
                return f"{phrase} 第 {index} 个例句中目标词必须只出现 1 次"
            if len(re.findall(r"[A-Za-z]+", sentence)) < 8:
                return f"{phrase} 第 {index} 个例句太短，信息量不足"
            if _looks_like_weak_example(sentence, phrase):
                return f"{phrase} 第 {index} 个例句信息量不足"
    return None


def _normalize_card_item(text: str) -> str:
    """Normalize a generated card item for strict batch comparison."""
    return re.sub(r"\s+", " ", str(text or "").strip()).lower()


def _split_example_sentences(example_field: str) -> list[str]:
    """Split normalized <br>-joined example fields."""
    return [
        re.sub(r"\s+", " ", item).strip()
        for item in re.split(r"<br\s*/?>", str(example_field or ""), flags=re.IGNORECASE)
        if re.sub(r"\s+", " ", item).strip()
    ]


def _validate_card_batch_completeness(
    raw_text: str,
    expected_items: List[str],
    example_count: int,
    translate_examples: bool,
    card_template: str,
) -> Optional[str]:
    """Validate that an AI batch can produce a complete card set."""
    from anki_parse import parse_anki_data

    cards = parse_anki_data(raw_text)
    if len(cards) != len(expected_items):
        return f"应返回 {len(expected_items)} 张卡片，实际解析到 {len(cards)} 张"

    for index, (card, expected_item) in enumerate(zip(cards, expected_items), start=1):
        phrase = str(card.get("w", "")).strip()
        if _normalize_card_item(phrase) != _normalize_card_item(expected_item):
            return f"第 {index} 张卡片词条不匹配：应为 {expected_item}，实际为 {phrase}"
        if not str(card.get("p", "")).strip() or "美" not in card.get("p", "") or "英" not in card.get("p", ""):
            return f"{phrase} 缺少完整美英音标"
        if not str(card.get("m", "")).strip():
            return f"{phrase} 缺少释义"

        examples = _split_example_sentences(str(card.get("e", "")))
        if len(examples) != example_count:
            return f"{phrase} 应有 {example_count} 个英文例句，实际为 {len(examples)} 个"

        translations = _split_example_sentences(str(card.get("ec", "")))
        if card_template == "definition_front":
            if translations:
                return f"{phrase} 第三种模板不应包含例句中文翻译"
            if str(card.get("r", "")).strip():
                return f"{phrase} 第三种模板不应包含词源字段"
        elif translate_examples and len(translations) != example_count:
            return f"{phrase} 应有 {example_count} 个例句翻译，实际为 {len(translations)} 个"
        elif not translate_examples and translations:
            return f"{phrase} 不应包含例句翻译"

    if card_template == "definition_front":
        return _validate_definition_front_examples(raw_text)
    return None


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
        return "Use only the single most common core meaning. English only, concise, under 10 words. Do not include Chinese."
    if definition_language == "中英":
        return "Use only the single most common core meaning. Format: 中文释义 | English definition under 8 words."
    return "Use only the single most common core meaning. Concise Simplified Chinese only."


def get_word_quick_definition(word: str) -> Dict[str, Any]:
    """Get a concise Chinese meaning and vivid etymology story."""
    vocab_dict = get_vocab_dict()
    model_name = get_ai_model()
    system_prompt = """You are a top-tier human linguistics professor, film director, and modern storyteller for a Chinese-speaking English learner.

Task:
Return concise Chinese meanings, vivid core images, and a deep etymology story for exactly one English word or short English phrase.

Output language:
- Use Simplified Chinese for the explanation.

Style:
- Accuracy is more important than vividness. If accuracy and storytelling conflict, choose accuracy.
- Write like a cinematic etymology storyteller, not like a dry dictionary.
- Keep the 【释义】 short and practical, like a Chinese dictionary.
- In 【底层逻辑】, turn the abstract meaning into one visible physical or mental scene.
- In 【🌱 Etymology 词源史诗】, show the ancient source, the concrete historical scene, and the word's drift into modern English.
- Use modern, energetic, memorable prose, but never invent facts, roots, dates, people, places, myths, or historical scenes.
- Create a strong contrast between the oldest concrete meaning and today's modern usage when that contrast is real.

Hard rules:
- Return plain text only. Do not use HTML, Markdown tables, code fences, example sentences, or extra notes.
- The user's message contains the lookup input. Never ask the user to provide a word.
- If the input is a plain word such as "developer", format that word directly.
- Do not output pronunciation, part of speech, collocations, or English definitions.
- Include only the three required sections: 【释义】, 【底层逻辑】, and 【🌱 Etymology 词源史诗】.
- Do not output any section other than these three.
- Put 【释义】 on its own line.
- In 【释义】, give 1-3 core high-frequency meanings on one single line.
- Separate different core meanings with Chinese semicolons: ；.
- Separate synonymous translations inside the same meaning with Chinese commas: ，.
- Example: 竞技场，活动场所；公开较量的领域
- Use only 1 meaning if the word has one dominant modern meaning.
- Only add a second or third meaning if it is also genuinely common and frequently used in modern English.
- If you are not sure a meaning is common, omit it and output only the dominant meaning.
- Never pad the answer to reach 2 or 3 meanings.
- Do not list obscure, rare, overly technical, or unrelated meanings.
- Do not include example sentences or translations in 【释义】.
- Always use the dominant contemporary meaning. If the word is mainly slang, taboo, vulgar, sexual, offensive, medical, or internet language, still give that most common meaning neutrally and factually.
- Do not replace a dominant slang or adult meaning with a safer literal meaning, food meaning, brand meaning, or older rare meaning.
- For adult or vulgar terms, keep the wording non-graphic and dictionary-like.
- Do not output horizontal separator lines.
- Explain where the word comes from when credible, such as Indo-European roots, Latin, Greek, Old English, Old Norse, French, or its root, prefix, or suffix.
- In 【🌱 Etymology 词源史诗】, write 2-4 compact but vivid Chinese paragraphs.
- When credible, include the earliest reliable source, the original concrete image or cultural scene, and how the meaning changed into modern English.
- Use dates, centuries, places, cultural practices, myths, or historical facts only when they are credible and widely attested.
- Do not derive a word from sound similarity, visual similarity, folk etymology, or a clever story unless that explanation is widely accepted.
- For transparent compounds, modern slang, brand-like terms, and internet terms, explain the actual word formation and semantic shift instead of forcing ancient roots.
- Use a loose historical timeline only when the evidence supports it. Do not force Industrial Revolution, Cold War, AI, Silicon Valley, or internet history unless the word truly connects to them.
- If there are two common etymology explanations, mention both and say which one is more widely accepted.
- Do not output the asterisk character anywhere.
- If you mention a reconstructed historical form, write it as “重建形式 ap(a)laz” without any marker before the form.
- If the etymology is unclear, disputed, weakly attested, or not useful, say that clearly in the etymology section and do not create a dramatic origin story.
- Use cautious wording such as “通常认为”, “可能来自”, “更可靠的说法是”, or “词源有争议” whenever the evidence is uncertain.
- End with one memorable "word drift" sentence that connects the old physical scene to the modern English usage.

Output exactly in this format:
【释义】
同一核心义的译法，同义译法；另一个核心释义

【底层逻辑】
One vivid Chinese sentence that captures the word's shared physical or mental image across contexts.

【🌱 Etymology 词源史诗】
Chinese etymology story only.

Reference example:
【释义】
竞技场，活动场所；公开较量的领域

【底层逻辑】
arena 的底层画面，是一块被人群围住的沙地：所有人都看着你上场，胜负、风险和声望一起被推到聚光灯下。

【🌱 Etymology 词源史诗】
arena 最早不是今天灯光炸裂、观众欢呼的“竞技场”，而是一层铺在地上的沙。它来自拉丁语 harena，意思就是沙子。古罗马人把沙铺在斗兽场和角斗场上，不是为了浪漫，而是为了吸血、防滑、盖住混乱。这个词一出生，就带着阳光、尘土、脚步声和危险的味道。

后来，沙地变成了场地，场地又变成了任何公开较量的空间。政治有 political arena，商业有 market arena，科技公司也有自己的 AI arena。词义一路从“铺着沙的肉搏现场”漂流到“任何强者交锋的舞台”。

几千年前那层用来遮住血迹的沙，最后变成了我们谈论竞争、权力和胜负时最锋利的一个词。
"""

    normalized_word = str(word or "").strip()
    if not normalized_word:
        return {"error": "Lookup input is required"}
    user_prompt = f"""Input term:
{normalized_word}

Write only the three required sections for the input term above. Do not ask for another word."""

    try:
        response = _call_ai_chat_completion(
            model_name,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            0.15
        )
        if "error" in response:
            return {"error": response["error"]}

        content = str(response.get("content", "")).replace("*", "")
        if _looks_like_missing_lookup_input(content):
            retry_prompt = f"""The input term is "{normalized_word}".

Return only the three required sections for its Chinese meaning, bottom logic, and etymology now. Do not ask for input."""
            response = _call_ai_chat_completion(
                model_name,
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": retry_prompt}
                ],
                0.1
            )
            if "error" in response:
                return {"error": response["error"]}
            content = str(response.get("content", "")).replace("*", "")
        headword = extract_lookup_headword(content)
        if not headword or headword.startswith("🌱") or headword.startswith("【"):
            headword = normalized_word.lower()
        rank = vocab_dict.get(headword, 99999)
        return {"result": content, "rank": rank, "headword": headword, "is_question": False}

    except Exception as e:
        logger.error("Error getting definition: %s", e)
        return {"error": str(e)}


def get_word_simple_definition(word: str) -> Dict[str, Any]:
    """Get a compact dictionary entry or reverse lookup for a Chinese gloss."""
    vocab_dict = get_vocab_dict()
    model_name = get_ai_model()
    normalized_word = str(word or "").strip()
    if not normalized_word:
        return {"error": "Lookup input is required"}

    system_prompt = """You are a strict concise English dictionary formatter for a Chinese-speaking learner.

Task:
Return a concise lookup result for exactly one input.

Input modes:
- If the input is an English word or short English phrase, return a short core-sense dictionary entry.
- If the input is a Simplified Chinese meaning, return the closest common English words that match that meaning.

Rules:
- Return plain text only. Do not use HTML, Markdown tables, code fences, headings, or extra notes.
- The user's message contains the lookup input. Never ask the user to provide a word.
- Automatically detect whether the input is English or Chinese.

English input rules:
- Give 1-3 core high-frequency meanings. Use only 1 meaning if the word has one dominant modern meaning.
- Only add a second or third meaning if it is also genuinely common and frequently used in modern English.
- If you are not sure a meaning is common, omit it and output only the dominant meaning.
- Never pad the answer to reach 2 or 3 meanings.
- Do not list obscure, rare, overly technical, or unrelated meanings.
- In each Chinese meaning, separate synonymous translations with Chinese commas: ，.
- Do not use Chinese semicolons inside one numbered meaning.
- Include exactly: word, IPA, 1-3 concise Chinese meanings, 1-3 concise English meanings, and one example sentence per meaning with its Simplified Chinese translation.
- Use one common IPA pronunciation.
- Give exactly 1 short, natural English example sentence for each meaning.
- Put the Simplified Chinese translation of each example sentence on the next line.
- Always use the dominant contemporary meaning. If the word is mainly slang, taboo, vulgar, sexual, offensive, medical, or internet language, still give that most common meaning neutrally and factually.
- Do not replace a dominant slang or adult meaning with a safer literal meaning, food meaning, brand meaning, or older rare meaning.
- For adult, vulgar, or offensive terms, keep the definition non-graphic and make the example a neutral sentence about usage or context, not a vivid scenario.
- Do not include etymology, collocations, phrases, frequency, rank, or part of speech.

Chinese input rules:
- Return 1-5 closest common English words or short phrases, ordered from closest and most common to less close.
- Only include words that are genuinely common and useful in modern English. If only one English word clearly fits, output only one.
- Do not include obscure, literary, technical, archaic, or low-frequency words just to reach a number.
- For each candidate, include IPA, concise Chinese meaning, concise English meaning, and one natural English example sentence with its Simplified Chinese translation.
- If two candidates are close, prefer the more common, everyday word first.

For English input, output exactly in this format:
word /IPA/
1. 简洁中文释义 | Concise English meaning
• Natural English example.
中文翻译。

English input reference example:
run /rʌn/
1. 跑，奔跑 | Move quickly on foot
• She runs every morning before work.
她每天上班前跑步。

2. 经营，管理 | Operate or manage something
• He runs a small cafe near the station.
他在车站附近经营一家小咖啡馆。

3. 运转，运行 | Function or operate
• The app runs smoothly on my phone.
这个应用在我的手机上运行很流畅。

For Chinese input, output exactly in this format:
中文释义：用户输入的中文释义
1. word /IPA/
简洁中文释义 | Concise English meaning
• Natural English example.
中文翻译。

Chinese input reference example:
中文释义：活力
1. vitality /vaɪˈtæləti/
活力，生命力 | Energy and strong life force
• Exercise can improve your vitality.
运动可以增强你的活力。

2. energy /ˈenərdʒi/
精力，能量 | Strength to do things
• She still has a lot of energy after work.
她下班后仍然精力充沛。"""

    user_prompt = f"""Input term:
{normalized_word}

Return the concise lookup result for the input above."""

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
        headword = extract_lookup_headword(response.get("content", "")) or normalized_word.lower()
        return {
            "result": response.get("content", ""),
            "headword": headword,
            "rank": vocab_dict.get(headword, 99999),
            "is_question": False,
        }
    except Exception as e:
        logger.error("Error getting simple definition: %s", e)
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
    translate_examples: bool = False,
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
        translate_examples = False
        example_count = 1
        definition_rule = (
            "Use exactly this inner format: English part-of-speech abbreviation | concise English definition under 10 words. "
            "Select only the single most common core meaning. "
            "Use abbreviations such as n., v., adj., adv., or phrase. "
            "The English definition should be simple and should not repeat the target word or phrase. "
            "Example: adj. | able to catch fire easily."
        )
        template_specific_rules = """
Template 3 strict rules:
- Field 3 must contain exactly two inner parts separated by one single | character:
  English part-of-speech abbreviation | concise English definition
- Field 4 must contain exactly one natural English sentence.
- The sentence is used as the card front cloze and the full card back example.
- The sentence must contain the exact target word or phrase once and will be converted into a cloze deletion.
- The sentence must illustrate the same single core meaning from field 3.
- The sentence must be self-contained and semantically informative: it should show what the word is, does, produces, causes, describes, or is used for.
- Keep the definition concise; the example can be longer when needed for natural, sufficient context.
- The example should usually be about 10-20 words, with a concrete subject, action, and meaning clue.
- Avoid overly short, empty, or diary-like sentences.
- Do not write vague event-only examples about visiting, seeing, liking, or using something without revealing the meaning.
- Do not include secondary meanings, rare meanings, or multiple senses.
- Bad for "brewery": We visited a local brewery last weekend.
- Good for "brewery": The brewery produces small-batch beer and delivers fresh kegs to nearby restaurants.
- Bad for "flammable": Materials near fire can be dangerous.
- Good for "flammable": Keep flammable materials away from sparks because they can catch fire quickly.
- Never put Chinese text, Chinese punctuation, or Chinese translation in field 3 or field 5.
- Never use Chinese part-of-speech labels such as 名词 or 动词; use n., v., adj., adv., or phrase.
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
    etymology_rule = (
        "Leave this field empty for template 3."
        if card_template == "definition_front"
        else "Briefly explain root, affix, or origin in Simplified Chinese."
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
4. English Example(s): generate exactly {example_count} natural, moderately detailed English example sentence(s) for the same core meaning as field 3. Each example must be self-contained and reveal the meaning through concrete context.
5. Example Translation(s): {translation_rule}
6. Etymology: {etymology_rule}

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
Field 3 and field 4 must all use one same dominant, common meaning.
Each example must contain the target word or phrase exactly once and must be informative enough to reveal the meaning.
{translation_count_rule}
For template 3, field 4 must contain the target word or phrase so the app can convert it into {{{{c1::word::first-letter hint}}}}.
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
                validation_error = _validate_card_batch_completeness(
                    content,
                    batch,
                    example_count,
                    translate_examples,
                    card_template,
                )
                if validation_error:
                    raise RuntimeError(f"AI 返回内容不完整：{validation_error}")
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

    if failed_batches:
        st.error(f"❌ 有 {len(failed_batches)} 个批次生成失败。为保证制卡完整性，本次不会生成部分卡片，请减少词数或重试。")
        return None

    return "\n".join(full_results)
