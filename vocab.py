# Word validation and text analysis (rank-based vocabulary extraction).

import re
from collections import Counter
from typing import Any, Dict, List, Tuple

import constants
from resources import get_vocab_dict, load_nlp_resources

# Lazy reference: VOCAB_DICT is read at runtime from resources.
def _vocab_dict() -> Dict[str, int]:
    return get_vocab_dict()


def is_valid_word(word: str) -> bool:
    """Validate if a word meets criteria for processing."""
    if len(word) < constants.MIN_WORD_LENGTH or len(word) > constants.MAX_WORD_LENGTH:
        return False
    if re.search(r'(.)\1{2,}', word):
        return False
    if not re.search(r'[aeiouy]', word):
        return False
    return True


def get_lemma(word: str, lemminflect: Any) -> str:
    """Get lemma of a word with error handling."""
    try:
        lemmas = lemminflect.getLemma(word, upos='VERB')
        return lemmas[0] if lemmas else word
    except Exception:
        return word


def analyze_logic(
    text: str,
    current_level: int,
    target_level: int,
    include_unknown: bool
) -> Tuple[List[Tuple[str, int]], int, Dict[str, float]]:
    """Analyze text to extract vocabulary within specified rank range."""
    nltk, lemminflect = load_nlp_resources()
    vocab_dict = _vocab_dict()

    raw_tokens = re.findall(r"[a-zA-Z]+(?:[-'][a-zA-Z]+)*", text)
    total_raw_count = len(raw_tokens)

    valid_tokens = [token.lower() for token in raw_tokens if is_valid_word(token.lower())]
    token_counts = Counter(valid_tokens)

    stats_known_count = 0
    stats_target_count = 0
    stats_valid_total = sum(token_counts.values())

    final_candidates = []
    seen_lemmas = set()

    for word, count in token_counts.items():
        lemma = get_lemma(word, lemminflect)
        rank_lemma = vocab_dict.get(lemma, 99999)
        rank_orig = vocab_dict.get(word, 99999)

        if rank_lemma != 99999 and rank_orig != 99999:
            best_rank = min(rank_lemma, rank_orig)
        elif rank_lemma != 99999:
            best_rank = rank_lemma
        else:
            best_rank = rank_orig

        if best_rank < current_level:
            stats_known_count += count
        elif current_level <= best_rank <= target_level:
            stats_target_count += count

        is_in_range = (best_rank >= current_level and best_rank <= target_level)
        is_unknown_included = (best_rank == 99999 and include_unknown)

        if is_in_range or is_unknown_included:
            word_to_keep = lemma if rank_lemma != 99999 else word
            if lemma not in seen_lemmas:
                final_candidates.append((word_to_keep, best_rank))
                seen_lemmas.add(lemma)

    final_candidates.sort(key=lambda x: x[1])

    coverage_ratio = (stats_known_count / stats_valid_total) if stats_valid_total > 0 else 0
    target_ratio = (stats_target_count / stats_valid_total) if stats_valid_total > 0 else 0

    stats_info = {
        "coverage": coverage_ratio,
        "target_density": target_ratio
    }

    return final_candidates, total_raw_count, stats_info
