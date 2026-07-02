import constants
from resources import get_vocab_dict, load_local_card_lexicon, lookup_local_card_entry, resolve_vocab_rank


def test_internal_vocab_lazy_loads_priority_list():
    vocab_dict = get_vocab_dict()
    assert len(vocab_dict) == constants.VOCAB_PROJECT_MAX_RANK
    assert resolve_vocab_rank("sophisticated") == (10628, "sophisticated")


def test_internal_vocab_lookup_handles_common_inflections():
    assert resolve_vocab_rank("companies") == (107, "company")
    assert resolve_vocab_rank("pharmaceuticals") == (4651, "pharmaceutical")
    assert resolve_vocab_rank("children") == (101, "child")


def test_local_card_lexicon_loads_local_definitions():
    entries = load_local_card_lexicon()
    assert len(entries) > 29000

    entry = lookup_local_card_entry("pharmaceuticals")
    assert entry is not None
    assert entry["word"] == "pharmaceutical"
    assert entry["english_definition"] == "relating to the preparation and making of medicine"
    assert "TSL 1.2" in entry["sources"]


def test_local_card_lexicon_uses_wordnet_examples_when_available():
    entry = lookup_local_card_entry("sophisticated")
    assert entry is not None
    assert entry["english_definition"].startswith("having or appealing")
    assert entry["example"] == "sophisticated young socialites"
    assert "WordNet" in entry["sources"]
