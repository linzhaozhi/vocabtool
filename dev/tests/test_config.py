# Tests for AI provider selection.

from config import _build_ai_config


def test_ai_provider_defaults_to_openai_when_both_keys_exist():
    config = _build_ai_config({
        "OPENAI_API_KEY": "sk-openai",
        "DEEPSEEK_API_KEY": "sk-deepseek",
    })
    assert config["ai_provider"] == "openai"
    assert config["ai_api_key"] == "sk-openai"


def test_ai_provider_can_be_forced_to_deepseek():
    config = _build_ai_config({
        "AI_PROVIDER": "deepseek",
        "OPENAI_API_KEY": "sk-openai",
        "DEEPSEEK_API_KEY": "sk-deepseek",
    })
    assert config["ai_provider"] == "deepseek"
    assert config["ai_api_key"] == "sk-deepseek"


def test_ai_provider_falls_back_to_deepseek_without_openai_key():
    config = _build_ai_config({"DEEPSEEK_API_KEY": "sk-deepseek"})
    assert config["ai_provider"] == "deepseek"
    assert config["ai_api_key"] == "sk-deepseek"
