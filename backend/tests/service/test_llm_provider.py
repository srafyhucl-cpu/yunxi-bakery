"""文本模型 provider resolver 合同测试。"""

from app.service.llm.provider import resolve_provider_model


def test_empty_model_uses_mimo_default() -> None:
    provider, model = resolve_provider_model()

    assert provider == "mimo"
    assert model


def test_explicit_mimo_model_stays_on_mimo() -> None:
    assert resolve_provider_model("mimo-test") == ("mimo", "mimo-test")


def test_explicit_non_mimo_model_is_explicit_deepseek_fallback() -> None:
    assert resolve_provider_model("deepseek-chat") == ("deepseek", "deepseek-chat")
