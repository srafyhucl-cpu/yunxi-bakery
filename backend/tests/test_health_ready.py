import sqlite3
import re
from contextlib import closing

import numpy as np

from app.config import APP_VERSION
from app import main
from app import database
from app import readiness


SAFE_TABLE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
KNOWLEDGE_BASE_GOVERNANCE_COLUMNS_SQL = (
    "audience TEXT DEFAULT 'all', "
    "review_status TEXT DEFAULT 'published', "
    "valid_from TEXT DEFAULT '', "
    "valid_until TEXT DEFAULT '', "
    "reviewed_by TEXT DEFAULT '', "
    "reviewed_at TEXT DEFAULT ''"
)

KNOWLEDGE_RETRIEVAL_LOGS_COLUMNS_SQL = (
    "bot_type TEXT DEFAULT '', "
    "audience TEXT DEFAULT 'all', "
    "query TEXT DEFAULT '', "
    "retrieval_mode TEXT DEFAULT '', "
    "matched_entry_ids_json TEXT DEFAULT '[]', "
    "matched_titles_json TEXT DEFAULT '[]', "
    "result_count INTEGER DEFAULT 0, "
    "fallback_reason TEXT DEFAULT '', "
    "created_at TEXT DEFAULT ''"
)


def _create_required_tables(db_path) -> None:
    with closing(sqlite3.connect(db_path)) as conn, conn:
        for table_name in readiness.REQUIRED_DATABASE_TABLES:
            assert SAFE_TABLE_NAME_PATTERN.fullmatch(table_name)
            if table_name == "knowledge_base":
                conn.execute(
                    "CREATE TABLE knowledge_base ("
                    "id TEXT PRIMARY KEY, "
                    + KNOWLEDGE_BASE_GOVERNANCE_COLUMNS_SQL
                    + ")"
                )
            elif table_name == "knowledge_retrieval_logs":
                conn.execute(
                    "CREATE TABLE knowledge_retrieval_logs ("
                    "id TEXT PRIMARY KEY, " + KNOWLEDGE_RETRIEVAL_LOGS_COLUMNS_SQL + ")"
                )
            else:
                conn.execute("CREATE TABLE " + table_name + " (id TEXT PRIMARY KEY)")


def _create_embedding_cache(index_path) -> None:
    np.save(index_path.with_suffix(".npy"), np.array([], dtype=np.float32))
    index_path.with_suffix(".json").write_text(
        '{"doc_keys": [], "ready": true, "data_hash": "test"}',
        encoding="utf-8",
    )


def test_health_returns_version() -> None:
    assert main.health.__name__ == "health"


def test_build_readiness_checks_reports_configured_paths(
    monkeypatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "bot.db"
    index_path = tmp_path / "embeddings"
    dist_dir = tmp_path / "dist"
    assets_dir = dist_dir / "assets"
    db_path.write_text("", encoding="utf-8")
    _create_required_tables(db_path)
    _create_embedding_cache(index_path)
    assets_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text("<div id='app'></div>", encoding="utf-8")
    (assets_dir / "admin.js").write_text(
        'http.get("/observability/summary")',
        encoding="utf-8",
    )
    monkeypatch.setattr(main.settings, "ADMIN_API_TOKEN", "strong-token")
    monkeypatch.setattr(main.settings, "MIMO_API_KEY", "mimo-key")
    monkeypatch.setattr(main.settings, "DB_PATH", str(db_path))
    monkeypatch.setattr(main.settings, "EMBEDDING_INDEX_DIR", str(index_path))
    monkeypatch.setattr(main.settings, "YOUZAN_CLIENT_ID", "youzan-client")
    monkeypatch.setattr(main.settings, "YOUZAN_CLIENT_SECRET", "youzan-secret")
    monkeypatch.setattr(main.settings, "YOUZAN_KDT_ID", "youzan-kdt")
    monkeypatch.setattr(main.settings, "YOUZAN_MOCK_MODE", False)
    monkeypatch.setattr(main.settings, "WECOM_CORP_ID", "corp-id")
    monkeypatch.setattr(main.settings, "WECOM_AGENT_ID", "1000001")
    monkeypatch.setattr(main.settings, "WECOM_SECRET", "wecom-secret")
    monkeypatch.setattr(main.settings, "WECOM_TOKEN", "wecom-token")
    monkeypatch.setattr(main.settings, "WECOM_ENCODING_AES_KEY", "wecom-aes-key")
    monkeypatch.setattr(main.settings, "WECOM_KF_ID", "wk_test")
    monkeypatch.setattr(main.settings, "WECOM_BOT_PLUGIN_API_KEY", "plugin-key")
    monkeypatch.setattr(main.settings, "WECOM_STAFF_ID", "")
    monkeypatch.setattr(main.settings, "WECOM_KF_SERVICER_USERID", "servicer-user")
    monkeypatch.setattr(readiness, "ADMIN_DIST_DIR", dist_dir)

    checks = readiness.build_readiness_checks()

    assert checks == {
        "admin_token_configured": True,
        "mimo_api_key_configured": True,
        "database_path_exists": True,
        "database_schema_ready": True,
        "embedding_index_path_exists": True,
        "youzan_client_id_configured": True,
        "youzan_client_secret_configured": True,
        "youzan_kdt_id_configured": True,
        "youzan_production_mode_ready": True,
        "wecom_corp_id_configured": True,
        "wecom_agent_id_configured": True,
        "wecom_secret_configured": True,
        "wecom_callback_token_configured": True,
        "wecom_encoding_aes_key_configured": True,
        "wecom_kf_id_configured": True,
        "wecom_bot_plugin_api_key_configured": True,
        "wecom_intelligent_bot_callback_token_configured": True,
        "wecom_intelligent_bot_encoding_aes_key_configured": True,
        "handoff_staff_userid_ready": True,
        "admin_frontend_index_exists": True,
        "admin_frontend_assets_exist": True,
        "admin_frontend_observability_summary_built": True,
    }


def test_build_readiness_checks_rejects_defaults(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(main.settings, "ADMIN_API_TOKEN", main.DEFAULT_ADMIN_TOKEN)
    monkeypatch.setattr(main.settings, "MIMO_API_KEY", "")
    monkeypatch.setattr(main.settings, "DB_PATH", str(tmp_path / "missing.db"))
    monkeypatch.setattr(main.settings, "EMBEDDING_INDEX_DIR", str(tmp_path / "missing"))
    monkeypatch.setattr(main.settings, "YOUZAN_CLIENT_ID", "")
    monkeypatch.setattr(main.settings, "YOUZAN_CLIENT_SECRET", "")
    monkeypatch.setattr(main.settings, "YOUZAN_KDT_ID", "")
    monkeypatch.setattr(main.settings, "YOUZAN_MOCK_MODE", True)
    monkeypatch.setattr(main.settings, "WECOM_CORP_ID", "")
    monkeypatch.setattr(main.settings, "WECOM_AGENT_ID", "")
    monkeypatch.setattr(main.settings, "WECOM_SECRET", "")
    monkeypatch.setattr(main.settings, "WECOM_TOKEN", "")
    monkeypatch.setattr(main.settings, "WECOM_ENCODING_AES_KEY", "")
    monkeypatch.setattr(main.settings, "WECOM_KF_ID", "")
    monkeypatch.setattr(main.settings, "WECOM_BOT_PLUGIN_API_KEY", "")
    monkeypatch.setattr(main.settings, "WECOM_STAFF_ID", "")
    monkeypatch.setattr(main.settings, "WECOM_KF_SERVICER_USERID", "")
    monkeypatch.setattr(readiness, "ADMIN_DIST_DIR", tmp_path / "missing-dist")

    checks = readiness.build_readiness_checks()

    assert checks["admin_token_configured"] is False
    assert checks["mimo_api_key_configured"] is False
    assert checks["database_path_exists"] is False
    assert checks["database_schema_ready"] is False
    assert checks["embedding_index_path_exists"] is False
    assert checks["youzan_production_mode_ready"] is False
    assert checks["wecom_corp_id_configured"] is False
    assert checks["wecom_callback_token_configured"] is False
    assert checks["wecom_encoding_aes_key_configured"] is False
    assert checks["wecom_kf_id_configured"] is False
    assert checks["wecom_bot_plugin_api_key_configured"] is False
    assert checks["wecom_intelligent_bot_callback_token_configured"] is False
    assert checks["wecom_intelligent_bot_encoding_aes_key_configured"] is False
    assert checks["handoff_staff_userid_ready"] is False
    assert checks["admin_frontend_index_exists"] is False
    assert checks["admin_frontend_assets_exist"] is False
    assert checks["admin_frontend_observability_summary_built"] is False


def test_build_channel_readiness_checks_accepts_production_channels(
    monkeypatch,
) -> None:
    monkeypatch.setattr(main.settings, "YOUZAN_CLIENT_ID", "youzan-client")
    monkeypatch.setattr(main.settings, "YOUZAN_CLIENT_SECRET", "youzan-secret")
    monkeypatch.setattr(main.settings, "YOUZAN_KDT_ID", "youzan-kdt")
    monkeypatch.setattr(main.settings, "YOUZAN_MOCK_MODE", False)
    monkeypatch.setattr(main.settings, "WECOM_CORP_ID", "corp-id")
    monkeypatch.setattr(main.settings, "WECOM_AGENT_ID", "1000001")
    monkeypatch.setattr(main.settings, "WECOM_SECRET", "wecom-secret")
    monkeypatch.setattr(main.settings, "WECOM_TOKEN", "wecom-token")
    monkeypatch.setattr(main.settings, "WECOM_ENCODING_AES_KEY", "wecom-aes-key")
    monkeypatch.setattr(main.settings, "WECOM_KF_ID", "wk_test")
    monkeypatch.setattr(main.settings, "WECOM_BOT_PLUGIN_API_KEY", "plugin-key")
    monkeypatch.setattr(main.settings, "WECOM_STAFF_ID", "")
    monkeypatch.setattr(main.settings, "WECOM_KF_SERVICER_USERID", "servicer-user")

    checks = readiness.build_channel_readiness_checks()

    assert checks == {
        "youzan_client_id_configured": True,
        "youzan_client_secret_configured": True,
        "youzan_kdt_id_configured": True,
        "youzan_production_mode_ready": True,
        "wecom_corp_id_configured": True,
        "wecom_agent_id_configured": True,
        "wecom_secret_configured": True,
        "wecom_callback_token_configured": True,
        "wecom_encoding_aes_key_configured": True,
        "wecom_kf_id_configured": True,
        "wecom_bot_plugin_api_key_configured": True,
        "wecom_intelligent_bot_callback_token_configured": True,
        "wecom_intelligent_bot_encoding_aes_key_configured": True,
        "handoff_staff_userid_ready": True,
    }


def test_build_channel_readiness_checks_rejects_mock_mode(
    monkeypatch,
) -> None:
    monkeypatch.setattr(main.settings, "YOUZAN_CLIENT_ID", "youzan-client")
    monkeypatch.setattr(main.settings, "YOUZAN_CLIENT_SECRET", "youzan-secret")
    monkeypatch.setattr(main.settings, "YOUZAN_KDT_ID", "youzan-kdt")
    monkeypatch.setattr(main.settings, "YOUZAN_MOCK_MODE", True)
    monkeypatch.setattr(main.settings, "WECOM_CORP_ID", "corp-id")
    monkeypatch.setattr(main.settings, "WECOM_AGENT_ID", "1000001")
    monkeypatch.setattr(main.settings, "WECOM_SECRET", "wecom-secret")
    monkeypatch.setattr(main.settings, "WECOM_TOKEN", "wecom-token")
    monkeypatch.setattr(main.settings, "WECOM_ENCODING_AES_KEY", "wecom-aes-key")
    monkeypatch.setattr(main.settings, "WECOM_KF_ID", "wk_test")
    monkeypatch.setattr(main.settings, "WECOM_BOT_PLUGIN_API_KEY", "plugin-key")
    monkeypatch.setattr(main.settings, "WECOM_STAFF_ID", "")
    monkeypatch.setattr(main.settings, "WECOM_KF_SERVICER_USERID", "servicer-user")

    checks = readiness.build_channel_readiness_checks()

    assert checks["youzan_client_id_configured"] is True
    assert checks["youzan_production_mode_ready"] is False
    assert checks["handoff_staff_userid_ready"] is True


def test_build_readiness_checks_rejects_missing_database_schema(
    monkeypatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "bot.db"
    db_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(main.settings, "DB_PATH", str(db_path))

    checks = readiness.build_readiness_checks()

    assert checks["database_path_exists"] is True
    assert checks["database_schema_ready"] is False


def test_embedding_index_files_exist_requires_npy_and_json(tmp_path) -> None:
    index_path = tmp_path / "embeddings"
    index_path.mkdir()

    assert readiness.embedding_index_files_exist(index_path) is False

    np.save(index_path.with_suffix(".npy"), np.array([], dtype=np.float32))

    assert readiness.embedding_index_files_exist(index_path) is False

    index_path.with_suffix(".json").write_text(
        '{"doc_keys": [], "ready": true}',
        encoding="utf-8",
    )

    assert readiness.embedding_index_files_exist(index_path) is True


def test_embedding_index_files_exist_rejects_unreadable_npy(tmp_path) -> None:
    index_path = tmp_path / "embeddings"
    index_path.with_suffix(".npy").write_bytes(b"not a numpy cache")
    index_path.with_suffix(".json").write_text(
        '{"doc_keys": [], "ready": true}',
        encoding="utf-8",
    )

    assert readiness.embedding_index_files_exist(index_path) is False


def test_embedding_index_files_exist_rejects_invalid_metadata(tmp_path) -> None:
    index_path = tmp_path / "embeddings"
    np.save(index_path.with_suffix(".npy"), np.array([], dtype=np.float32))
    index_path.with_suffix(".json").write_text(
        '{"doc_keys": {}, "ready": "yes"}',
        encoding="utf-8",
    )

    assert readiness.embedding_index_files_exist(index_path) is False


def test_embedding_index_files_exist_rejects_non_object_metadata(tmp_path) -> None:
    index_path = tmp_path / "embeddings"
    np.save(index_path.with_suffix(".npy"), np.array([], dtype=np.float32))
    index_path.with_suffix(".json").write_text("[]", encoding="utf-8")

    assert readiness.embedding_index_files_exist(index_path) is False


def test_readiness_resolves_relative_paths_from_project_root(
    monkeypatch,
    tmp_path,
) -> None:
    project_root = tmp_path / "project"
    data_dir = project_root / "data"
    other_cwd = tmp_path / "other-cwd"
    db_path = data_dir / "bot.db"
    index_path = data_dir / "embeddings"
    data_dir.mkdir(parents=True)
    other_cwd.mkdir()
    db_path.write_text("", encoding="utf-8")
    _create_required_tables(db_path)
    _create_embedding_cache(index_path)
    monkeypatch.chdir(other_cwd)
    monkeypatch.setattr(database, "ROOT_DIR", project_root)
    monkeypatch.setattr(readiness, "ROOT_DIR", project_root)
    monkeypatch.setattr(main.settings, "DB_PATH", "data/bot.db")
    monkeypatch.setattr(main.settings, "EMBEDDING_INDEX_DIR", "data/embeddings")

    checks = readiness.build_readiness_checks()

    assert checks["database_path_exists"] is True
    assert checks["database_schema_ready"] is True
    assert checks["embedding_index_path_exists"] is True


async def test_database_session_resolves_relative_path_from_project_root(
    monkeypatch,
    tmp_path,
) -> None:
    project_root = tmp_path / "project"
    data_dir = project_root / "data"
    other_cwd = tmp_path / "other-cwd"
    data_dir.mkdir(parents=True)
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)
    monkeypatch.setattr(database, "ROOT_DIR", project_root)
    monkeypatch.setattr(main.settings, "DB_PATH", "data/bot.db")

    async with database.db_session_scope() as conn:
        await conn.execute("CREATE TABLE runtime_path_probe (id TEXT PRIMARY KEY)")

    assert (project_root / "data" / "bot.db").exists() is True
    assert (other_cwd / "data" / "bot.db").exists() is False


def test_build_admin_frontend_readiness_checks_detects_built_summary(
    monkeypatch,
    tmp_path,
) -> None:
    dist_dir = tmp_path / "dist"
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text("<div id='app'></div>", encoding="utf-8")
    (assets_dir / "admin.css").write_text("/* 上线值守 */", encoding="utf-8")
    monkeypatch.setattr(readiness, "ADMIN_DIST_DIR", dist_dir)

    checks = readiness.build_admin_frontend_readiness_checks()

    assert checks == {
        "admin_frontend_index_exists": True,
        "admin_frontend_assets_exist": True,
        "admin_frontend_observability_summary_built": True,
    }


def test_build_admin_frontend_readiness_checks_rejects_stale_dist(
    monkeypatch,
    tmp_path,
) -> None:
    dist_dir = tmp_path / "dist"
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text("<div id='app'></div>", encoding="utf-8")
    (assets_dir / "old.js").write_text("console.log('old admin')", encoding="utf-8")
    monkeypatch.setattr(readiness, "ADMIN_DIST_DIR", dist_dir)

    checks = readiness.build_admin_frontend_readiness_checks()

    assert checks["admin_frontend_index_exists"] is True
    assert checks["admin_frontend_assets_exist"] is True
    assert checks["admin_frontend_observability_summary_built"] is False


async def test_ready_returns_ready_when_all_checks_pass(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "bot.db"
    index_path = tmp_path / "embeddings"
    dist_dir = tmp_path / "dist"
    assets_dir = dist_dir / "assets"
    db_path.write_text("", encoding="utf-8")
    _create_required_tables(db_path)
    _create_embedding_cache(index_path)
    assets_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text("<div id='app'></div>", encoding="utf-8")
    (assets_dir / "admin.js").write_text("慢 Webhook", encoding="utf-8")
    monkeypatch.setattr(main.settings, "ADMIN_API_TOKEN", "strong-token")
    monkeypatch.setattr(main.settings, "MIMO_API_KEY", "mimo-key")
    monkeypatch.setattr(main.settings, "DB_PATH", str(db_path))
    monkeypatch.setattr(main.settings, "EMBEDDING_INDEX_DIR", str(index_path))
    monkeypatch.setattr(main.settings, "YOUZAN_CLIENT_ID", "youzan-client")
    monkeypatch.setattr(main.settings, "YOUZAN_CLIENT_SECRET", "youzan-secret")
    monkeypatch.setattr(main.settings, "YOUZAN_KDT_ID", "youzan-kdt")
    monkeypatch.setattr(main.settings, "YOUZAN_MOCK_MODE", False)
    monkeypatch.setattr(main.settings, "WECOM_CORP_ID", "corp-id")
    monkeypatch.setattr(main.settings, "WECOM_AGENT_ID", "1000001")
    monkeypatch.setattr(main.settings, "WECOM_SECRET", "wecom-secret")
    monkeypatch.setattr(main.settings, "WECOM_TOKEN", "wecom-token")
    monkeypatch.setattr(main.settings, "WECOM_ENCODING_AES_KEY", "wecom-aes-key")
    monkeypatch.setattr(main.settings, "WECOM_KF_ID", "wk_test")
    monkeypatch.setattr(main.settings, "WECOM_BOT_PLUGIN_API_KEY", "plugin-key")
    monkeypatch.setattr(main.settings, "WECOM_STAFF_ID", "staff-user")
    monkeypatch.setattr(main.settings, "WECOM_KF_SERVICER_USERID", "")
    monkeypatch.setattr(main.settings, "ENABLE_REPLY_GUARD", True)
    monkeypatch.setattr(readiness, "ADMIN_DIST_DIR", dist_dir)

    payload = await main.ready()

    assert payload["status"] == "ready"
    assert payload["version"] == APP_VERSION
    assert payload["features"]["reply_guard"] is True


async def test_ready_returns_degraded_when_check_fails(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(main.settings, "ADMIN_API_TOKEN", main.DEFAULT_ADMIN_TOKEN)
    monkeypatch.setattr(main.settings, "MIMO_API_KEY", "mimo-key")
    monkeypatch.setattr(main.settings, "DB_PATH", str(tmp_path / "missing.db"))
    monkeypatch.setattr(main.settings, "EMBEDDING_INDEX_DIR", str(tmp_path / "missing"))
    monkeypatch.setattr(main.settings, "YOUZAN_CLIENT_ID", "youzan-client")
    monkeypatch.setattr(main.settings, "YOUZAN_CLIENT_SECRET", "youzan-secret")
    monkeypatch.setattr(main.settings, "YOUZAN_KDT_ID", "youzan-kdt")
    monkeypatch.setattr(main.settings, "YOUZAN_MOCK_MODE", True)
    monkeypatch.setattr(main.settings, "WECOM_CORP_ID", "corp-id")
    monkeypatch.setattr(main.settings, "WECOM_AGENT_ID", "1000001")
    monkeypatch.setattr(main.settings, "WECOM_SECRET", "wecom-secret")
    monkeypatch.setattr(main.settings, "WECOM_TOKEN", "wecom-token")
    monkeypatch.setattr(main.settings, "WECOM_ENCODING_AES_KEY", "wecom-aes-key")
    monkeypatch.setattr(main.settings, "WECOM_KF_ID", "wk_test")
    monkeypatch.setattr(main.settings, "WECOM_BOT_PLUGIN_API_KEY", "")
    monkeypatch.setattr(main.settings, "WECOM_STAFF_ID", "staff-user")
    monkeypatch.setattr(main.settings, "WECOM_KF_SERVICER_USERID", "")
    monkeypatch.setattr(readiness, "ADMIN_DIST_DIR", tmp_path / "missing-dist")

    payload = await main.ready()

    assert payload["status"] == "degraded"
    assert payload["checks"]["admin_token_configured"] is False
    assert payload["checks"]["youzan_production_mode_ready"] is False
    assert payload["checks"]["wecom_bot_plugin_api_key_configured"] is False
    assert payload["checks"]["admin_frontend_observability_summary_built"] is False
