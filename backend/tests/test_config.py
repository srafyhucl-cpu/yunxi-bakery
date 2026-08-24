import pytest
from pydantic import ValidationError

from app.config import ENV_FILE, PROJECT_ROOT, Settings


def test_settings_env_file_is_project_root_absolute_path() -> None:
    assert ENV_FILE == PROJECT_ROOT / ".env"
    assert ENV_FILE.is_absolute()


def test_settings_default_env_file_does_not_follow_current_directory(
    monkeypatch,
    tmp_path,
) -> None:
    (tmp_path / ".env").write_text(
        "ADMIN_API_TOKEN=TOKEN_FROM_WRONG_WORKDIR\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ADMIN_API_TOKEN", raising=False)

    loaded_settings = Settings()

    assert loaded_settings.ADMIN_API_TOKEN != "TOKEN_FROM_WRONG_WORKDIR"


def test_settings_defaults_enable_customer_memory_without_env() -> None:
    loaded_settings = Settings(_env_file=None)

    assert loaded_settings.ENABLE_CUSTOMER_MEMORY is True


def test_settings_defaults_keep_langsmith_tracing_disabled() -> None:
    loaded_settings = Settings(_env_file=None)

    assert loaded_settings.LANGCHAIN_TRACING_ENABLED is False
    assert loaded_settings.LANGCHAIN_PROJECT == "yunxi-bakebot"
    assert loaded_settings.LANGSMITH_API_KEY == ""
    assert loaded_settings.AGENT_LOCAL_TRACE_ENABLED is True


def test_settings_defaults_keep_rag_retrieval_mode_stable() -> None:
    loaded_settings = Settings(_env_file=None)

    assert loaded_settings.RAG_RETRIEVAL_MODE == "hybrid"


def test_settings_accepts_planned_rag_retrieval_mode(monkeypatch) -> None:
    monkeypatch.setenv("RAG_RETRIEVAL_MODE", " planned-hybrid-rerank ")

    loaded_settings = Settings(_env_file=None)

    assert loaded_settings.RAG_RETRIEVAL_MODE == "planned-hybrid-rerank"


def test_settings_rejects_unknown_rag_retrieval_mode(monkeypatch) -> None:
    monkeypatch.setenv("RAG_RETRIEVAL_MODE", "experimental")

    with pytest.raises(ValidationError, match="RAG_RETRIEVAL_MODE"):
        Settings(_env_file=None)
