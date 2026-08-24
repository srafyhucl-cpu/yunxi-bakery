"""LangChain 适配层测试。"""

import sys


def test_agents_llm_import_does_not_import_langchain_runtime() -> None:
    sys.modules.pop("app.service.agents.llm", None)
    sys.modules.pop("langchain_openai", None)

    import app.service.agents.llm  # noqa: F401

    assert "langchain_openai" not in sys.modules


def test_langchain_chat_model_factory_builds_mimo_model() -> None:
    from app.service.agents import llm

    llm._MODEL_REGISTRY.clear()
    llm._TRANSPORT_REGISTRY.clear()
    model = llm.get_langchain_chat_model(provider="mimo", model="mimo-test")
    same_model = llm.get_langchain_chat_model(provider="mimo", model="mimo-test")

    assert model.model_name == "mimo-test"
    assert str(model.openai_api_base).rstrip("/") == "https://api.xiaomimimo.com/v1"
    assert same_model is model
