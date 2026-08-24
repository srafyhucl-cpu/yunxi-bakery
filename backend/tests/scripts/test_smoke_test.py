import io
import json
import sqlite3
from contextlib import closing
from datetime import datetime

import numpy as np
import pytest

from scripts import smoke_test


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, object]:
        return self._payload


class _FakeAsyncClient:
    requested_urls: list[str] = []
    requested_headers: list[dict[str, str] | None] = []
    response = _FakeResponse(200, {"status": "ready", "checks": {}})

    def __init__(self, timeout: int) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def get(
        self, url: str, headers: dict[str, str] | None = None
    ) -> _FakeResponse:
        self.requested_urls.append(url)
        self.requested_headers.append(headers)
        return self.response


class _ForbiddenAsyncClient:
    def __init__(self, timeout: int) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> "_ForbiddenAsyncClient":
        raise AssertionError("HTTP client should not be opened when service is down")

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class _FakeStreamWriter:
    closed = False
    waited = False

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        self.waited = True


class _FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 6, 11, 11, 20, 0, tzinfo=tz)


class _FakeStdout:
    def __init__(self) -> None:
        self.buffer = io.BytesIO()


@pytest.fixture(autouse=True)
def _reset_smoke_target_override():
    smoke_test.SMOKE_TARGET_OVERRIDE = None
    smoke_test.SMOKE_RUNTIME_PATHS_OVERRIDE = None
    yield
    smoke_test.SMOKE_TARGET_OVERRIDE = None
    smoke_test.SMOKE_RUNTIME_PATHS_OVERRIDE = None


def _create_smoke_schema(db_path, table_names: tuple[str, ...]) -> None:
    with closing(sqlite3.connect(db_path)) as conn, conn:
        for table_name in table_names:
            assert table_name.replace("_", "").isalnum()
            conn.execute("CREATE TABLE " + table_name + " (id TEXT PRIMARY KEY)")


def _assert_json_does_not_leak_secret_values(
    payload: dict[str, object],
    secret_values: tuple[str, ...],
) -> None:
    serialized_payload = json.dumps(payload, ensure_ascii=False)
    for secret_value in secret_values:
        assert secret_value not in serialized_payload


def _write_embedding_cache(index_path) -> None:
    np.save(index_path.with_suffix(".npy"), np.array([], dtype=np.float32))
    index_path.with_suffix(".json").write_text(
        '{"doc_keys": [], "ready": true, "data_hash": "test"}',
        encoding="utf-8",
    )


def test_check_required_settings_uses_mimo_key(monkeypatch) -> None:
    monkeypatch.setattr(smoke_test.settings, "ADMIN_API_TOKEN", "strong-token")
    monkeypatch.setattr(smoke_test.settings, "MIMO_API_KEY", "")
    monkeypatch.setattr(smoke_test.settings, "DEEPSEEK_API_KEY", "")

    result = smoke_test.check_required_settings()

    assert result.passed is False
    assert "MIMO_API_KEY" in result.detail
    assert "DEEPSEEK_API_KEY" not in result.detail


def test_smoke_result_serializes_to_dict() -> None:
    result = smoke_test.SmokeResult("检查项", False, "failed detail")

    assert result.to_dict() == {
        "name": "检查项",
        "passed": False,
        "detail": "failed detail",
    }


def test_format_http_error_falls_back_to_exception_type() -> None:
    error = smoke_test.httpx.ConnectError("")

    assert smoke_test._format_http_error(error) == "请求失败: ConnectError"


def test_parse_base_url_accepts_http_and_https_defaults() -> None:
    http_target = smoke_test.parse_base_url("http://127.0.0.1:7001")
    https_target = smoke_test.parse_base_url("https://bot.example.com")

    assert http_target == smoke_test.SmokeTarget("http", "127.0.0.1", 7001)
    assert https_target == smoke_test.SmokeTarget("https", "bot.example.com", 443)


def test_parse_base_url_rejects_paths_and_query() -> None:
    try:
        smoke_test.parse_base_url("https://bot.example.com/ready?x=1")
    except ValueError as exc:
        assert "根地址" in str(exc)
    else:
        raise AssertionError("base url with path should be rejected")


def test_set_smoke_target_override_does_not_mutate_settings(monkeypatch) -> None:
    monkeypatch.setattr(smoke_test.settings, "SERVER_HOST", "127.0.0.1")
    monkeypatch.setattr(smoke_test.settings, "SERVER_PORT", 7001)

    smoke_test.set_smoke_target_override("https://bot.example.com")

    assert smoke_test.get_smoke_target() == smoke_test.SmokeTarget(
        "https",
        "bot.example.com",
        443,
    )
    assert smoke_test.settings.SERVER_HOST == "127.0.0.1"
    assert smoke_test.settings.SERVER_PORT == 7001


def test_set_smoke_runtime_paths_override_uses_explicit_paths(
    monkeypatch,
    tmp_path,
) -> None:
    default_db_path = tmp_path / "default" / "bot.db"
    default_index_path = tmp_path / "default" / "embeddings"
    target_db_path = tmp_path / "target" / "bot.db"
    target_index_path = tmp_path / "target" / "embeddings"
    monkeypatch.setattr(smoke_test.settings, "DB_PATH", str(default_db_path))
    monkeypatch.setattr(
        smoke_test.settings,
        "EMBEDDING_INDEX_DIR",
        str(default_index_path),
    )

    smoke_test.set_smoke_runtime_paths_override(
        str(target_db_path),
        str(target_index_path),
    )

    runtime_paths = smoke_test.get_smoke_runtime_paths()
    assert runtime_paths.database_path == target_db_path
    assert runtime_paths.index_path == target_index_path
    assert smoke_test.settings.DB_PATH == str(default_db_path)
    assert smoke_test.settings.EMBEDDING_INDEX_DIR == str(default_index_path)


def test_check_required_settings_rejects_default_admin_token(monkeypatch) -> None:
    monkeypatch.setattr(
        smoke_test.settings,
        "ADMIN_API_TOKEN",
        smoke_test.DEFAULT_ADMIN_TOKEN,
    )
    monkeypatch.setattr(smoke_test.settings, "MIMO_API_KEY", "mimo-key")

    result = smoke_test.check_required_settings()

    assert result.passed is False
    assert "ADMIN_API_TOKEN" in result.detail


def test_check_runtime_feature_flags_reports_enabled_flags(monkeypatch) -> None:
    monkeypatch.setattr(smoke_test.settings, "ENABLE_REPLY_GUARD", True)
    monkeypatch.setattr(smoke_test.settings, "ENABLE_CUSTOMER_MEMORY", False)
    monkeypatch.setattr(smoke_test.settings, "ENABLE_OFFLINE_REVIEW", True)
    monkeypatch.setattr(smoke_test.settings, "ENABLE_HYBRID_RETRIEVAL", False)
    monkeypatch.setattr(smoke_test.settings, "YOUZAN_MOCK_MODE", False)

    result = smoke_test.check_runtime_feature_flags()

    assert result.passed is True
    assert "enabled=reply_guard, offline_review" in result.detail


def test_check_schema_passes_when_required_tables_exist(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "bot.db"
    _create_smoke_schema(db_path, smoke_test.REQUIRED_DATABASE_TABLES)
    monkeypatch.setattr(smoke_test.settings, "DB_PATH", str(db_path))

    result = smoke_test.check_schema()

    assert result.passed is True


def test_check_schema_reports_missing_production_tables(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "bot.db"
    old_tables = (
        "sessions",
        "messages",
        "knowledge_base",
        "human_transfers",
        "orders",
        "shop_config",
    )
    _create_smoke_schema(db_path, old_tables)
    monkeypatch.setattr(smoke_test.settings, "DB_PATH", str(db_path))

    result = smoke_test.check_schema()

    assert result.passed is False
    assert "youzan_webhook_events" in result.detail
    assert "wecom_kf_message_ledger" in result.detail


def test_check_schema_reports_unreadable_database(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "bot.db"
    db_path.write_text("not a sqlite database", encoding="utf-8")
    monkeypatch.setattr(smoke_test.settings, "DB_PATH", str(db_path))

    result = smoke_test.check_schema()

    assert result.passed is False
    assert "database_not_readable" in result.detail
    assert "DB_PATH" in result.detail


def test_check_database_file_uses_absolute_db_path(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "absolute.db"
    db_path.write_bytes(b"")
    monkeypatch.setattr(smoke_test.settings, "DB_PATH", str(db_path))

    result = smoke_test.check_database_file()

    assert result.passed is True
    assert result.detail == str(db_path)


def test_check_knowledge_rows_reports_missing_table(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "bot.db"
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY)")
    monkeypatch.setattr(smoke_test.settings, "DB_PATH", str(db_path))

    result = smoke_test.check_knowledge_rows()

    assert result.passed is False
    assert "查询失败" in result.detail
    assert "knowledge_base" in result.detail


def test_check_knowledge_rows_reports_unreadable_database(
    monkeypatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "bot.db"
    db_path.write_text("not a sqlite database", encoding="utf-8")
    monkeypatch.setattr(smoke_test.settings, "DB_PATH", str(db_path))

    result = smoke_test.check_knowledge_rows()

    assert result.passed is False
    assert "database_not_readable" in result.detail
    assert "DB_PATH" in result.detail


def test_check_embedding_file_requires_npy_and_json(monkeypatch, tmp_path) -> None:
    index_path = tmp_path / "embeddings"
    monkeypatch.setattr(smoke_test.settings, "EMBEDDING_INDEX_DIR", str(index_path))

    result = smoke_test.check_embedding_file()

    assert result.passed is False
    assert str(index_path.with_suffix(".npy")) in result.detail
    assert str(index_path.with_suffix(".json")) in result.detail

    _write_embedding_cache(index_path)

    result = smoke_test.check_embedding_file()

    assert result.passed is True
    assert "ready=" in result.detail


def test_check_embedding_file_reports_invalid_cache(monkeypatch, tmp_path) -> None:
    index_path = tmp_path / "embeddings"
    index_path.with_suffix(".npy").write_bytes(b"not a numpy cache")
    index_path.with_suffix(".json").write_text(
        '{"doc_keys": [], "ready": true}',
        encoding="utf-8",
    )
    monkeypatch.setattr(smoke_test.settings, "EMBEDDING_INDEX_DIR", str(index_path))

    result = smoke_test.check_embedding_file()

    assert result.passed is False
    assert "invalid_cache" in result.detail
    assert str(index_path.with_suffix(".npy")) in result.detail
    assert str(index_path.with_suffix(".json")) in result.detail


def test_check_channel_readiness_passes_when_channels_are_configured(
    monkeypatch,
) -> None:
    monkeypatch.setattr(smoke_test.settings, "YOUZAN_MOCK_MODE", False)
    monkeypatch.setattr(smoke_test.settings, "YOUZAN_CLIENT_ID", "youzan-client")
    monkeypatch.setattr(smoke_test.settings, "YOUZAN_CLIENT_SECRET", "youzan-secret")
    monkeypatch.setattr(smoke_test.settings, "YOUZAN_KDT_ID", "youzan-kdt")
    monkeypatch.setattr(smoke_test.settings, "WECOM_CORP_ID", "corp-id")
    monkeypatch.setattr(smoke_test.settings, "WECOM_AGENT_ID", "1000001")
    monkeypatch.setattr(smoke_test.settings, "WECOM_SECRET", "wecom-secret")
    monkeypatch.setattr(smoke_test.settings, "WECOM_TOKEN", "wecom-token")
    monkeypatch.setattr(smoke_test.settings, "WECOM_ENCODING_AES_KEY", "wecom-aes-key")
    monkeypatch.setattr(smoke_test.settings, "WECOM_KF_ID", "wk_test")
    monkeypatch.setattr(smoke_test.settings, "WECOM_BOT_PLUGIN_API_KEY", "plugin-key")
    monkeypatch.setattr(smoke_test.settings, "WECOM_STAFF_ID", "")
    monkeypatch.setattr(smoke_test.settings, "WECOM_KF_SERVICER_USERID", "servicer")

    result = smoke_test.check_channel_readiness()

    assert result.passed is True
    assert result.detail == "channels-ready"


def test_check_channel_readiness_reports_missing_channel_settings(
    monkeypatch,
) -> None:
    monkeypatch.setattr(smoke_test.settings, "YOUZAN_MOCK_MODE", False)
    monkeypatch.setattr(smoke_test.settings, "YOUZAN_CLIENT_ID", "")
    monkeypatch.setattr(smoke_test.settings, "YOUZAN_CLIENT_SECRET", "youzan-secret")
    monkeypatch.setattr(smoke_test.settings, "YOUZAN_KDT_ID", "")
    monkeypatch.setattr(smoke_test.settings, "WECOM_CORP_ID", "")
    monkeypatch.setattr(smoke_test.settings, "WECOM_AGENT_ID", "1000001")
    monkeypatch.setattr(smoke_test.settings, "WECOM_SECRET", "")
    monkeypatch.setattr(smoke_test.settings, "WECOM_TOKEN", "")
    monkeypatch.setattr(smoke_test.settings, "WECOM_ENCODING_AES_KEY", "")
    monkeypatch.setattr(smoke_test.settings, "WECOM_KF_ID", "")
    monkeypatch.setattr(smoke_test.settings, "WECOM_BOT_PLUGIN_API_KEY", "")
    monkeypatch.setattr(smoke_test.settings, "WECOM_STAFF_ID", "")
    monkeypatch.setattr(smoke_test.settings, "WECOM_KF_SERVICER_USERID", "")

    result = smoke_test.check_channel_readiness()

    assert result.passed is False
    assert "YOUZAN_CLIENT_ID" in result.detail
    assert "YOUZAN_KDT_ID" in result.detail
    assert "WECOM_CORP_ID" in result.detail
    assert "WECOM_SECRET" in result.detail
    assert "WECOM_TOKEN" in result.detail
    assert "WECOM_ENCODING_AES_KEY" in result.detail
    assert "WECOM_KF_ID" in result.detail
    assert "WECOM_BOT_PLUGIN_API_KEY" in result.detail
    assert "WECOM_STAFF_ID_OR_WECOM_KF_SERVICER_USERID" in result.detail


def test_check_admin_dist_observability_summary_passes_when_bundle_contains_marker(
    monkeypatch,
    tmp_path,
) -> None:
    dist_dir = tmp_path / "dist"
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir(parents=True)
    (assets_dir / "observability.js").write_text(
        'http.get("/observability/summary")',
        encoding="utf-8",
    )
    monkeypatch.setattr(smoke_test, "ADMIN_DIST_DIR", dist_dir)

    result = smoke_test.check_admin_dist_observability_summary()

    assert result.passed is True
    assert "/observability/summary" in result.detail


def test_check_admin_dist_observability_summary_fails_when_bundle_missing(
    monkeypatch,
    tmp_path,
) -> None:
    dist_dir = tmp_path / "dist"
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir(parents=True)
    (assets_dir / "old.js").write_text("console.log('old admin')", encoding="utf-8")
    monkeypatch.setattr(smoke_test, "ADMIN_DIST_DIR", dist_dir)

    result = smoke_test.check_admin_dist_observability_summary()

    assert result.passed is False
    assert "重新构建 web/admin" in result.detail


def test_build_readiness_detail_reports_failed_checks() -> None:
    payload = {
        "status": "degraded",
        "checks": {
            "admin_token_configured": True,
            "database_path_exists": False,
            "embedding_index_path_exists": False,
        },
    }

    detail = smoke_test.build_readiness_detail(payload)

    assert detail == "failed_checks=database_path_exists, embedding_index_path_exists"


def test_build_observability_summary_detail_reports_status_and_counts() -> None:
    payload = {
        "code": 0,
        "data": {
            "status": "attention",
            "counts": {"webhook_failures": 1, "slow_webhooks": 2},
        },
    }

    detail = smoke_test.build_observability_summary_detail(payload)

    assert (
        detail == "status=attention, counts={'webhook_failures': 1, 'slow_webhooks': 2}"
    )


async def test_check_service_reachability_passes_and_closes_writer(
    monkeypatch,
) -> None:
    writer = _FakeStreamWriter()

    async def fake_open_connection(host: str, port: int):
        assert host == "127.0.0.1"
        assert port == 18000
        return object(), writer

    monkeypatch.setattr(smoke_test.settings, "SERVER_HOST", "127.0.0.1")
    monkeypatch.setattr(smoke_test.settings, "SERVER_PORT", 18000)
    monkeypatch.setattr(smoke_test.asyncio, "open_connection", fake_open_connection)

    result = await smoke_test.check_service_reachability()

    assert result.passed is True
    assert result.name == smoke_test.SERVICE_REACHABILITY_NAME
    assert result.detail == "http://127.0.0.1:18000"
    assert writer.closed is True
    assert writer.waited is True


def test_build_skipped_http_results_uses_single_unreachable_reason() -> None:
    reachability_result = smoke_test.SmokeResult(
        smoke_test.SERVICE_REACHABILITY_NAME,
        False,
        "http://127.0.0.1:7001; connect_failed=refused",
    )

    results = smoke_test.build_skipped_http_results(reachability_result)

    assert [result.name for result in results] == list(
        smoke_test.HTTP_ENDPOINT_CHECK_NAMES
    )
    assert all(result.passed is False for result in results)
    assert all("服务不可达" in result.detail for result in results)
    assert all("connect_failed=refused" in result.detail for result in results)


async def test_run_smoke_checks_skips_http_endpoints_when_service_unreachable(
    monkeypatch,
) -> None:
    async def fake_check_service_reachability() -> smoke_test.SmokeResult:
        return smoke_test.SmokeResult(
            smoke_test.SERVICE_REACHABILITY_NAME,
            False,
            "http://127.0.0.1:7001; connect_failed=refused",
        )

    monkeypatch.setattr(
        smoke_test,
        "run_static_checks",
        lambda: [smoke_test.SmokeResult("static", True, "ready")],
    )
    monkeypatch.setattr(
        smoke_test,
        "check_service_reachability",
        fake_check_service_reachability,
    )
    monkeypatch.setattr(smoke_test.httpx, "AsyncClient", _ForbiddenAsyncClient)

    results = await smoke_test.run_smoke_checks()

    assert [result.name for result in results] == [
        "static",
        smoke_test.SERVICE_REACHABILITY_NAME,
        *smoke_test.HTTP_ENDPOINT_CHECK_NAMES,
    ]
    assert results[1].passed is False
    assert results[2].detail.startswith(smoke_test.SERVICE_UNREACHABLE_DETAIL)


async def test_run_http_only_smoke_checks_skips_static_and_admin_checks(
    monkeypatch,
) -> None:
    async def fake_check_service_reachability() -> smoke_test.SmokeResult:
        return smoke_test.SmokeResult(
            smoke_test.SERVICE_REACHABILITY_NAME,
            True,
            "https://bot.example.com:443",
        )

    async def fake_check_health_endpoint() -> smoke_test.SmokeResult:
        return smoke_test.SmokeResult("健康检查接口", True, "ok")

    async def fake_check_ready_endpoint() -> smoke_test.SmokeResult:
        return smoke_test.SmokeResult("就绪检查接口", True, "ready")

    async def forbidden_observability_summary() -> smoke_test.SmokeResult:
        raise AssertionError("http-only should not check admin observability")

    monkeypatch.setattr(
        smoke_test,
        "run_static_checks",
        lambda: (_ for _ in ()).throw(
            AssertionError("http-only should not run static checks")
        ),
    )
    monkeypatch.setattr(
        smoke_test,
        "check_service_reachability",
        fake_check_service_reachability,
    )
    monkeypatch.setattr(smoke_test, "check_health_endpoint", fake_check_health_endpoint)
    monkeypatch.setattr(smoke_test, "check_ready_endpoint", fake_check_ready_endpoint)
    monkeypatch.setattr(
        smoke_test,
        "check_observability_summary_endpoint",
        forbidden_observability_summary,
    )

    results = await smoke_test.run_http_only_smoke_checks()

    assert [result.name for result in results] == [
        smoke_test.SERVICE_REACHABILITY_NAME,
        "健康检查接口",
        "就绪检查接口",
    ]
    assert all(result.passed for result in results)


async def test_run_http_only_smoke_checks_skips_only_health_ready_when_unreachable(
    monkeypatch,
) -> None:
    async def fake_check_service_reachability() -> smoke_test.SmokeResult:
        return smoke_test.SmokeResult(
            smoke_test.SERVICE_REACHABILITY_NAME,
            False,
            "https://bot.example.com:443; connect_failed=refused",
        )

    monkeypatch.setattr(
        smoke_test,
        "check_service_reachability",
        fake_check_service_reachability,
    )
    monkeypatch.setattr(smoke_test.httpx, "AsyncClient", _ForbiddenAsyncClient)

    results = await smoke_test.run_http_only_smoke_checks()

    assert [result.name for result in results] == [
        smoke_test.SERVICE_REACHABILITY_NAME,
        *smoke_test.HTTP_ONLY_ENDPOINT_CHECK_NAMES,
    ]
    assert results[0].passed is False
    assert results[1].detail.startswith(smoke_test.SERVICE_UNREACHABLE_DETAIL)


async def test_check_ready_endpoint_passes_when_ready(monkeypatch) -> None:
    _FakeAsyncClient.requested_urls = []
    _FakeAsyncClient.response = _FakeResponse(
        200,
        {"status": "ready", "checks": {"admin_token_configured": True}},
    )
    monkeypatch.setattr(smoke_test.httpx, "AsyncClient", _FakeAsyncClient)

    result = await smoke_test.check_ready_endpoint()

    assert result.passed is True
    assert result.name == "就绪检查接口"
    assert _FakeAsyncClient.requested_urls[0].endswith(smoke_test.READY_PATH)


async def test_check_ready_endpoint_fails_when_degraded(monkeypatch) -> None:
    _FakeAsyncClient.response = _FakeResponse(
        200,
        {
            "status": "degraded",
            "checks": {
                "admin_token_configured": False,
                "mimo_api_key_configured": True,
            },
        },
    )
    monkeypatch.setattr(smoke_test.httpx, "AsyncClient", _FakeAsyncClient)

    result = await smoke_test.check_ready_endpoint()

    assert result.passed is False
    assert result.detail == "failed_checks=admin_token_configured"


async def test_check_observability_summary_endpoint_passes_with_admin_token(
    monkeypatch,
) -> None:
    _FakeAsyncClient.requested_urls = []
    _FakeAsyncClient.requested_headers = []
    _FakeAsyncClient.response = _FakeResponse(
        200,
        {
            "code": 0,
            "data": {
                "status": "ok",
                "counts": {"webhook_failures": 0},
            },
        },
    )
    monkeypatch.setattr(smoke_test.settings, "ADMIN_API_TOKEN", "strong-token")
    monkeypatch.setattr(smoke_test.httpx, "AsyncClient", _FakeAsyncClient)

    result = await smoke_test.check_observability_summary_endpoint()

    assert result.passed is True
    assert result.name == "观察台值守摘要接口"
    assert _FakeAsyncClient.requested_urls[0].endswith(
        smoke_test.OBSERVABILITY_SUMMARY_PATH
    )
    assert _FakeAsyncClient.requested_headers[0] == {
        "Authorization": "Bearer strong-token"
    }


async def test_check_observability_summary_endpoint_fails_on_bad_shape(
    monkeypatch,
) -> None:
    _FakeAsyncClient.response = _FakeResponse(
        200, {"code": 0, "data": {"status": "ok"}}
    )
    monkeypatch.setattr(smoke_test.httpx, "AsyncClient", _FakeAsyncClient)

    result = await smoke_test.check_observability_summary_endpoint()

    assert result.passed is False


def test_build_json_report_includes_metadata_and_failed_names(
    monkeypatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "bot.db"
    index_path = tmp_path / "embeddings"
    monkeypatch.setattr(smoke_test, "datetime", _FrozenDateTime)
    monkeypatch.setattr(smoke_test.settings, "DB_PATH", str(db_path))
    monkeypatch.setattr(smoke_test.settings, "EMBEDDING_INDEX_DIR", str(index_path))
    monkeypatch.setattr(smoke_test.settings, "SERVER_HOST", "127.0.0.1")
    monkeypatch.setattr(smoke_test.settings, "SERVER_PORT", 18000)
    results = [
        smoke_test.SmokeResult("ok", True, "ready"),
        smoke_test.SmokeResult("bad", False, "failed"),
    ]

    payload = smoke_test.build_json_report(results)

    assert payload["status"] == "failed"
    assert payload["total"] == 2
    assert payload["failed"] == 1
    assert payload["failed_names"] == ["bad"]
    assert payload["results"][1] == {
        "name": "bad",
        "passed": False,
        "detail": "failed",
    }
    assert payload["metadata"] == {
        "generated_at": "2026-06-11T11:20:00Z",
        "project_root": str(smoke_test.ROOT_DIR),
        "database_path": str(db_path),
        "index_path": str(index_path),
        "server_base_url": "http://127.0.0.1:18000",
        "app_version": smoke_test.APP_VERSION,
    }
    assert payload["recovery_hints"] == []


def test_build_recovery_hints_groups_failed_checks() -> None:
    results = [
        smoke_test.SmokeResult(smoke_test.DATABASE_SCHEMA_CHECK_NAME, False, "missing"),
        smoke_test.SmokeResult(smoke_test.KNOWLEDGE_ROWS_CHECK_NAME, False, "empty"),
        smoke_test.SmokeResult(smoke_test.EMBEDDING_FILE_CHECK_NAME, False, "missing"),
        smoke_test.SmokeResult(
            smoke_test.CHANNEL_READINESS_CHECK_NAME, False, "missing"
        ),
    ]

    hints = smoke_test.build_recovery_hints(results)

    assert [hint.title for hint in hints] == [
        "补齐数据库和知识数据",
        "补齐向量缓存",
        "补齐生产配置",
    ]
    assert [hint.key for hint in hints] == [
        "database_knowledge",
        "embedding_cache",
        "production_config",
    ]
    assert [hint.severity for hint in hints] == [
        "critical",
        "critical",
        "critical",
    ]
    assert hints[0].related_names == (
        smoke_test.DATABASE_SCHEMA_CHECK_NAME,
        smoke_test.KNOWLEDGE_ROWS_CHECK_NAME,
    )
    assert "preflight_production.py" in hints[0].action
    assert "rebuild_embeddings.py" in hints[1].action


def test_build_recovery_hints_collapses_unreachable_http_checks() -> None:
    results = [
        smoke_test.SmokeResult(
            smoke_test.SERVICE_REACHABILITY_NAME,
            False,
            "connect_failed=refused",
        ),
        *[
            smoke_test.SmokeResult(check_name, False, "skipped")
            for check_name in smoke_test.HTTP_ENDPOINT_CHECK_NAMES
        ],
    ]

    hints = smoke_test.build_recovery_hints(results)

    assert len(hints) == 1
    assert hints[0].key == "service_unreachable"
    assert hints[0].severity == "critical"
    assert hints[0].title == "启动并核对服务地址"
    assert hints[0].related_names == (
        smoke_test.SERVICE_REACHABILITY_NAME,
        *smoke_test.HTTP_ENDPOINT_CHECK_NAMES,
    )
    assert "同一个根因" in hints[0].reason


def test_build_json_report_includes_recovery_hints() -> None:
    payload = smoke_test.build_json_report(
        [
            smoke_test.SmokeResult(
                smoke_test.EMBEDDING_FILE_CHECK_NAME,
                False,
                "missing",
            )
        ]
    )

    assert payload["recovery_hints"][0]["title"] == "补齐向量缓存"
    assert payload["recovery_hints"][0]["key"] == "embedding_cache"
    assert payload["recovery_hints"][0]["severity"] == "critical"
    assert payload["recovery_hints"][0]["related_names"] == [
        smoke_test.EMBEDDING_FILE_CHECK_NAME
    ]


def test_json_report_does_not_leak_secret_values(monkeypatch) -> None:
    secret_values = (
        "admin-secret-value",
        "mimo-secret-value",
        "youzan-client-secret-value",
        "wecom-token-secret-value",
    )
    monkeypatch.setattr(smoke_test.settings, "ADMIN_API_TOKEN", secret_values[0])
    monkeypatch.setattr(smoke_test.settings, "MIMO_API_KEY", secret_values[1])
    monkeypatch.setattr(smoke_test.settings, "YOUZAN_CLIENT_SECRET", secret_values[2])
    monkeypatch.setattr(smoke_test.settings, "WECOM_TOKEN", secret_values[3])
    results = [
        smoke_test.check_required_settings(),
        smoke_test.check_channel_readiness(),
        smoke_test.SmokeResult("observability", False, "status=401"),
    ]

    payload = smoke_test.build_json_report(results)

    _assert_json_does_not_leak_secret_values(payload, secret_values)


async def test_main_prints_text_report_by_default(monkeypatch, capsys) -> None:
    async def fake_run_smoke_checks() -> list[smoke_test.SmokeResult]:
        return [
            smoke_test.SmokeResult("ok", True, "ready"),
            smoke_test.SmokeResult("bad", False, "failed"),
        ]

    monkeypatch.setattr(
        smoke_test,
        "run_smoke_checks",
        fake_run_smoke_checks,
    )

    exit_code = await smoke_test.main([])

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "Bakery Commerce Platform production smoke" in output
    assert f"app_version={smoke_test.APP_VERSION}" in output
    assert "total=2 failed=1" in output
    assert "PASS ok: ready" in output
    assert "FAIL bad: failed" in output


async def test_main_text_output_includes_recovery_hints(monkeypatch, capsys) -> None:
    async def fake_run_smoke_checks() -> list[smoke_test.SmokeResult]:
        return [
            smoke_test.SmokeResult(
                smoke_test.SERVICE_REACHABILITY_NAME,
                False,
                "connect_failed=refused",
            )
        ]

    monkeypatch.setattr(smoke_test, "run_smoke_checks", fake_run_smoke_checks)

    exit_code = await smoke_test.main([])

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "recovery_hints:" in output
    assert "[critical] service_unreachable" in output
    assert "启动并核对服务地址" in output
    assert smoke_test.SERVICE_REACHABILITY_NAME in output


async def test_main_json_output_is_machine_readable(monkeypatch) -> None:
    async def fake_run_smoke_checks() -> list[smoke_test.SmokeResult]:
        return [
            smoke_test.SmokeResult("ok", True, "ready"),
            smoke_test.SmokeResult("bad", False, "failed"),
        ]

    fake_stdout = _FakeStdout()
    monkeypatch.setattr(smoke_test.sys, "stdout", fake_stdout)
    monkeypatch.setattr(smoke_test, "datetime", _FrozenDateTime)
    monkeypatch.setattr(
        smoke_test,
        "run_smoke_checks",
        fake_run_smoke_checks,
    )

    exit_code = await smoke_test.main(["--json"])

    assert exit_code == 1
    payload = json.loads(fake_stdout.buffer.getvalue().decode("utf-8"))
    assert payload["status"] == "failed"
    assert payload["failed_names"] == ["bad"]
    assert payload["metadata"]["generated_at"] == "2026-06-11T11:20:00Z"
    assert payload["recovery_hints"] == []


async def test_main_json_output_uses_base_url_override(monkeypatch) -> None:
    async def fake_run_smoke_checks() -> list[smoke_test.SmokeResult]:
        return [smoke_test.SmokeResult("ok", True, "ready")]

    fake_stdout = _FakeStdout()
    monkeypatch.setattr(smoke_test.sys, "stdout", fake_stdout)
    monkeypatch.setattr(smoke_test, "datetime", _FrozenDateTime)
    monkeypatch.setattr(smoke_test, "run_smoke_checks", fake_run_smoke_checks)
    monkeypatch.setattr(smoke_test.settings, "SERVER_HOST", "127.0.0.1")
    monkeypatch.setattr(smoke_test.settings, "SERVER_PORT", 7001)

    exit_code = await smoke_test.main(
        ["--json", "--base-url", "https://bot.example.com"]
    )

    assert exit_code == 0
    payload = json.loads(fake_stdout.buffer.getvalue().decode("utf-8"))
    assert payload["metadata"]["server_base_url"] == "https://bot.example.com:443"
    assert smoke_test.settings.SERVER_HOST == "127.0.0.1"
    assert smoke_test.settings.SERVER_PORT == 7001


async def test_main_http_only_json_output_uses_remote_http_checks(monkeypatch) -> None:
    async def fake_run_http_only_smoke_checks() -> list[smoke_test.SmokeResult]:
        return [smoke_test.SmokeResult("remote", True, "ready")]

    async def forbidden_run_smoke_checks() -> list[smoke_test.SmokeResult]:
        raise AssertionError("http-only should not run full smoke")

    fake_stdout = _FakeStdout()
    monkeypatch.setattr(smoke_test.sys, "stdout", fake_stdout)
    monkeypatch.setattr(smoke_test, "datetime", _FrozenDateTime)
    monkeypatch.setattr(
        smoke_test,
        "run_http_only_smoke_checks",
        fake_run_http_only_smoke_checks,
    )
    monkeypatch.setattr(smoke_test, "run_smoke_checks", forbidden_run_smoke_checks)

    exit_code = await smoke_test.main(["--json", "--http-only"])

    assert exit_code == 0
    payload = json.loads(fake_stdout.buffer.getvalue().decode("utf-8"))
    assert payload["status"] == "passed"
    assert payload["results"][0]["name"] == "remote"


async def test_main_json_output_uses_runtime_path_overrides(
    monkeypatch,
    tmp_path,
) -> None:
    async def fake_run_smoke_checks() -> list[smoke_test.SmokeResult]:
        return [smoke_test.SmokeResult("ok", True, "ready")]

    default_db_path = tmp_path / "default" / "bot.db"
    default_index_path = tmp_path / "default" / "embeddings"
    target_db_path = tmp_path / "target" / "bot.db"
    target_index_path = tmp_path / "target" / "embeddings"
    fake_stdout = _FakeStdout()
    monkeypatch.setattr(smoke_test.sys, "stdout", fake_stdout)
    monkeypatch.setattr(smoke_test, "datetime", _FrozenDateTime)
    monkeypatch.setattr(smoke_test, "run_smoke_checks", fake_run_smoke_checks)
    monkeypatch.setattr(smoke_test.settings, "DB_PATH", str(default_db_path))
    monkeypatch.setattr(
        smoke_test.settings,
        "EMBEDDING_INDEX_DIR",
        str(default_index_path),
    )

    exit_code = await smoke_test.main(
        [
            "--json",
            "--db-path",
            str(target_db_path),
            "--index-path",
            str(target_index_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(fake_stdout.buffer.getvalue().decode("utf-8"))
    assert payload["metadata"]["database_path"] == str(target_db_path)
    assert payload["metadata"]["index_path"] == str(target_index_path)
    assert smoke_test.settings.DB_PATH == str(default_db_path)
    assert smoke_test.settings.EMBEDDING_INDEX_DIR == str(default_index_path)


async def test_main_rejects_invalid_base_url(capsys) -> None:
    exit_code = await smoke_test.main(["--base-url", "https://bot.example.com/ready"])

    assert exit_code == 2
    assert "根地址" in capsys.readouterr().err


async def test_main_json_output_can_be_written_to_file(
    monkeypatch,
    tmp_path,
) -> None:
    async def fake_run_smoke_checks() -> list[smoke_test.SmokeResult]:
        return [smoke_test.SmokeResult("ok", True, "ready")]

    report_path = tmp_path / "reports" / "smoke.json"
    monkeypatch.setattr(smoke_test, "datetime", _FrozenDateTime)
    monkeypatch.setattr(smoke_test, "run_smoke_checks", fake_run_smoke_checks)

    exit_code = await smoke_test.main(["--json", "--output", str(report_path)])

    assert exit_code == 0
    assert report_path.read_bytes().startswith(smoke_test.UTF8_BOM)
    payload = json.loads(report_path.read_text(encoding="utf-8-sig"))
    assert payload["status"] == "passed"
    assert payload["metadata"]["generated_at"] == "2026-06-11T11:20:00Z"


async def test_main_json_output_expands_timestamp_placeholder(
    monkeypatch,
    tmp_path,
) -> None:
    async def fake_run_smoke_checks() -> list[smoke_test.SmokeResult]:
        return [smoke_test.SmokeResult("ok", True, "ready")]

    report_template = tmp_path / "reports" / "smoke-{timestamp}.json"
    expected_path = tmp_path / "reports" / "smoke-20260611-112000.json"
    monkeypatch.setattr(smoke_test, "datetime", _FrozenDateTime)
    monkeypatch.setattr(smoke_test, "run_smoke_checks", fake_run_smoke_checks)

    exit_code = await smoke_test.main(["--json", "--output", str(report_template)])

    assert exit_code == 0
    assert expected_path.exists() is True
    assert report_template.exists() is False


def test_parse_args_help_mentions_timestamp_placeholder(capsys) -> None:
    try:
        smoke_test.parse_args(["--help"])
    except SystemExit as exc:
        assert exc.code == 0

    help_text = capsys.readouterr().out
    assert "{timestamp}" in help_text
    assert "YYYYMMDD-HHMMSS" in help_text
    assert "--db-path" in help_text
    assert "--index-path" in help_text
    assert "--http-only" in help_text


async def test_main_json_output_refuses_to_overwrite_file(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    async def fake_run_smoke_checks() -> list[smoke_test.SmokeResult]:
        return [smoke_test.SmokeResult("ok", True, "ready")]

    report_path = tmp_path / "smoke.json"
    report_path.write_text("existing", encoding="utf-8")
    monkeypatch.setattr(smoke_test, "run_smoke_checks", fake_run_smoke_checks)

    exit_code = await smoke_test.main(["--json", "--output", str(report_path)])

    assert exit_code == 2
    assert report_path.read_text(encoding="utf-8") == "existing"
    assert "拒绝覆盖" in capsys.readouterr().err


async def test_main_output_requires_json_flag(capsys, tmp_path) -> None:
    exit_code = await smoke_test.main(["--output", str(tmp_path / "smoke.json")])

    assert exit_code == 2
    assert "--output 必须配合 --json 使用" in capsys.readouterr().err
