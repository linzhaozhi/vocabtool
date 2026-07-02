import constants
from resources import get_vocab_dict, resolve_vocab_rank


def test_internal_vocab_lazy_loads_priority_list():
    vocab_dict = get_vocab_dict()
    assert len(vocab_dict) == constants.VOCAB_PROJECT_MAX_RANK
    assert resolve_vocab_rank("sophisticated") == (10628, "sophisticated")


def test_internal_vocab_lookup_handles_common_inflections():
    assert resolve_vocab_rank("companies") == (107, "company")
    assert resolve_vocab_rank("pharmaceuticals") == (4651, "pharmaceutical")
    assert resolve_vocab_rank("children") == (101, "child")
