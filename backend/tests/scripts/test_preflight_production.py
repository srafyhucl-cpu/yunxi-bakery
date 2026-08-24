from __future__ import annotations

import importlib.util
import io
import json
import sqlite3
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path
from types import ModuleType

import numpy as np

KNOWLEDGE_BASE_GOVERNANCE_COLUMNS_SQL = (
    "audience TEXT DEFAULT 'all', "
    "review_status TEXT DEFAULT 'published', "
    "valid_from TEXT DEFAULT '', "
    "valid_until TEXT DEFAULT '', "
    "reviewed_by TEXT DEFAULT '', "
    "reviewed_at TEXT DEFAULT ''"
)


def load_preflight_module() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "preflight_production.py"
    )
    spec = importlib.util.spec_from_file_location("preflight_production", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 6, 11, 10, 30, 0, tzinfo=tz)


def _create_required_tables(module: ModuleType, db_path: Path) -> None:
    with closing(sqlite3.connect(db_path)) as conn, conn:
        for table_name in module.REQUIRED_DATABASE_TABLES:
            assert table_name.replace("_", "").isalnum()
            if table_name == "knowledge_base":
                conn.execute(
                    "CREATE TABLE knowledge_base ("
                    "id INTEGER PRIMARY KEY, "
                    "is_active INTEGER DEFAULT 1, "
                    + KNOWLEDGE_BASE_GOVERNANCE_COLUMNS_SQL
                    + ")"
                )
            else:
                conn.execute("CREATE TABLE " + table_name + " (id TEXT PRIMARY KEY)")


def _assert_json_does_not_leak_secret_values(
    payload: dict[str, object],
    secret_values: tuple[str, ...],
) -> None:
    serialized_payload = json.dumps(payload, ensure_ascii=False)
    for secret_value in secret_values:
        assert secret_value not in serialized_payload


def _write_embedding_cache(index_path: Path) -> None:
    np.save(index_path.with_suffix(".npy"), np.array([], dtype=np.float32))
    index_path.with_suffix(".json").write_text(
        '{"doc_keys": [], "ready": true, "data_hash": "test"}',
        encoding="utf-8",
    )


def test_get_missing_database_tables_reports_only_missing_tables(
    tmp_path: Path,
) -> None:
    preflight = load_preflight_module()
    db_path = tmp_path / "bot.db"
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE messages (id TEXT PRIMARY KEY)")

    missing_tables = preflight.get_missing_database_tables(db_path)

    assert "sessions" not in missing_tables
    assert "messages" not in missing_tables
    assert "knowledge_base" in missing_tables
    assert "knowledge_retrieval_logs" in missing_tables
    assert "wecom_kf_message_ledger" in missing_tables


def test_build_knowledge_detail_check_reports_empty_database(
    monkeypatch,
    tmp_path: Path,
) -> None:
    preflight = load_preflight_module()
    db_path = tmp_path / "bot.db"
    _create_required_tables(preflight, db_path)
    monkeypatch.setattr(preflight.settings, "DB_PATH", str(db_path))

    check = preflight.build_knowledge_detail_check()

    assert check.key == "knowledge.active_rows"
    assert check.passed is False
    assert check.detail == "active_rows=0"
    assert "RAG" in check.action
    assert "dry-run" in check.action


def test_build_embedding_detail_check_requires_cache_pair(
    monkeypatch,
    tmp_path: Path,
) -> None:
    preflight = load_preflight_module()
    index_path = tmp_path / "embeddings"
    np.save(index_path.with_suffix(".npy"), np.array([], dtype=np.float32))
    monkeypatch.setattr(preflight.settings, "EMBEDDING_INDEX_DIR", str(index_path))

    check = preflight.build_embedding_detail_check()

    assert check.passed is False
    assert "recovery_plan" in check.action
    assert "dry-run" in check.action
    assert str(index_path.with_suffix(".json")) in check.action

    index_path.with_suffix(".json").write_text(
        '{"doc_keys": [], "ready": true}',
        encoding="utf-8",
    )

    check = preflight.build_embedding_detail_check()

    assert check.passed is True
    assert check.action == ""


def test_build_embedding_detail_check_reports_invalid_cache(
    monkeypatch,
    tmp_path: Path,
) -> None:
    preflight = load_preflight_module()
    index_path = tmp_path / "embeddings"
    index_path.with_suffix(".npy").write_bytes(b"not a numpy cache")
    index_path.with_suffix(".json").write_text(
        '{"doc_keys": [], "ready": true}',
        encoding="utf-8",
    )
    monkeypatch.setattr(preflight.settings, "EMBEDDING_INDEX_DIR", str(index_path))

    check = preflight.build_embedding_detail_check()

    assert check.passed is False
    assert "invalid_cache" in check.detail
    assert "rebuild_embeddings.py dry-run" in check.action
    assert "--apply" in check.action


def test_build_preflight_checks_includes_actionable_readiness_failures(
    monkeypatch,
    tmp_path: Path,
) -> None:
    preflight = load_preflight_module()
    db_path = tmp_path / "bot.db"
    monkeypatch.setattr(preflight.settings, "DB_PATH", str(db_path))
    monkeypatch.setattr(preflight.settings, "WECOM_STAFF_ID", "")
    monkeypatch.setattr(preflight.settings, "WECOM_KF_SERVICER_USERID", "")
    monkeypatch.setattr(preflight.settings, "WECOM_BOT_PLUGIN_API_KEY", "")

    checks = preflight.build_preflight_checks()
    checks_by_key = {check.key: check for check in checks}

    assert checks_by_key["database_path_exists"].passed is False
    assert checks_by_key["database_path_exists"].action
    assert "recovery_plan" in checks_by_key["database_schema_ready"].action
    assert checks_by_key["wecom_bot_plugin_api_key_configured"].passed is False
    assert (
        "WECOM_BOT_PLUGIN_API_KEY"
        in checks_by_key["wecom_bot_plugin_api_key_configured"].action
    )
    assert checks_by_key["handoff_staff_userid_ready"].passed is False
    assert "WECOM_STAFF_ID" in checks_by_key["handoff_staff_userid_ready"].action
    assert checks_by_key["business_contracts.static_checks"].passed is True


def test_production_preflight_requires_employee_auth_allowlist(monkeypatch) -> None:
    preflight = load_preflight_module()
    monkeypatch.setattr(preflight.settings, "WECOM_TOKEN", "wecom-token")
    monkeypatch.setattr(preflight.settings, "WECOM_INTELLIGENT_BOT_TOKEN", "")
    monkeypatch.setattr(preflight.settings, "WECOM_EMPLOYEE_AUTH_REQUIRED", False)
    monkeypatch.setattr(preflight.settings, "WECOM_EMPLOYEE_ALLOWED_USERS", "user-1")
    monkeypatch.setattr(preflight.settings, "WECOM_EMPLOYEE_CORP_ID", "corp-1")
    monkeypatch.setattr(preflight.settings, "WECOM_EMPLOYEE_OPS_USERS", "user-1")

    checks = preflight.build_readiness_preflight_checks()
    checks_by_key = {check.key: check for check in checks}

    assert checks_by_key["wecom_employee_auth_ready"].passed is False
    assert (
        "WECOM_EMPLOYEE_AUTH_REQUIRED"
        in checks_by_key["wecom_employee_auth_ready"].action
    )


def test_build_preflight_checks_uses_path_overrides(
    monkeypatch,
    tmp_path: Path,
) -> None:
    preflight = load_preflight_module()
    default_db_path = tmp_path / "default" / "bot.db"
    target_db_path = tmp_path / "target" / "bot.db"
    target_index_path = tmp_path / "target" / "embeddings"
    target_db_path.parent.mkdir()
    _create_required_tables(preflight, target_db_path)
    with closing(sqlite3.connect(target_db_path)) as conn, conn:
        conn.execute("INSERT INTO knowledge_base (is_active) VALUES (?)", (1,))
    _write_embedding_cache(target_index_path)

    monkeypatch.setattr(preflight.settings, "DB_PATH", str(default_db_path))
    monkeypatch.setattr(
        preflight.settings,
        "EMBEDDING_INDEX_DIR",
        str(tmp_path / "default" / "embeddings"),
    )

    checks = preflight.build_preflight_checks(
        str(target_db_path),
        str(target_index_path),
    )
    checks_by_key = {check.key: check for check in checks}

    assert checks_by_key["database_path_exists"].passed is True
    assert checks_by_key["database_schema_ready"].passed is True
    assert checks_by_key["database.required_tables"].passed is True
    assert checks_by_key["database.required_columns"].passed is True
    assert checks_by_key["knowledge.active_rows"].detail == "active_rows=1"
    assert checks_by_key["embedding_index_path_exists"].passed is True
    assert checks_by_key["embedding.cache_files"].passed is True
    assert checks_by_key["business_contracts.static_checks"].passed is True
    assert (
        "employee_agent_capability_contracts:passed"
        in checks_by_key["business_contracts.static_checks"].detail
    )
    assert (
        "customer_rag_golden_cases:passed"
        in checks_by_key["business_contracts.static_checks"].detail
    )
    assert (
        "knowledge_governance_plan:passed"
        in checks_by_key["business_contracts.static_checks"].detail
    )
    assert (
        "customer_memory_governance_plan:passed"
        in checks_by_key["business_contracts.static_checks"].detail
    )
    assert (
        "customer_observability_contract:passed"
        in checks_by_key["business_contracts.static_checks"].detail
    )
    assert (
        "miniapp_page_api_contract:passed"
        in checks_by_key["business_contracts.static_checks"].detail
    )
    assert (
        "github_reference_implementation_plan:passed"
        in checks_by_key["business_contracts.static_checks"].detail
    )


def test_build_business_contract_check_reports_failures(monkeypatch) -> None:
    preflight = load_preflight_module()

    monkeypatch.setattr(
        preflight.check_project,
        "run_contract_checks",
        lambda: [
            preflight.check_project.CheckResult("customer-rag", True, []),
            preflight.check_project.CheckResult("knowledge-plan", False, []),
        ],
    )

    check = preflight.build_business_contract_check()

    assert check.key == "business_contracts.static_checks"
    assert check.passed is False
    assert "total=2" in check.detail
    assert "failed=1" in check.detail
    assert "checks=customer-rag:passed, knowledge-plan:failed" in check.detail
    assert "knowledge-plan" in check.detail
    assert "check_project.py --skip-tests" in check.action


def test_main_returns_failure_when_any_preflight_check_fails(
    monkeypatch,
    capsys,
) -> None:
    preflight = load_preflight_module()
    monkeypatch.setattr(
        preflight,
        "build_preflight_checks",
        lambda db_path=None, index_path=None: [
            preflight.PreflightCheck("ok", "ok", True, "ready", ""),
            preflight.PreflightCheck("bad", "bad", False, "failed", "fix it"),
        ],
    )

    exit_code = preflight.main([])

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "failed=1" in output
    assert "action: fix it" in output


def test_main_json_output_is_machine_readable(
    monkeypatch,
) -> None:
    preflight = load_preflight_module()
    output_buffer = io.BytesIO()

    class FakeStdout:
        buffer = output_buffer

    monkeypatch.setattr(
        preflight,
        "build_preflight_checks",
        lambda db_path=None, index_path=None: [
            preflight.PreflightCheck("ok", "OK", True, "ready", ""),
            preflight.PreflightCheck("bad", "Bad", False, "failed", "fix it"),
        ],
    )
    monkeypatch.setattr(preflight, "datetime", _FrozenDateTime)
    monkeypatch.setattr(preflight.sys, "stdout", FakeStdout())

    exit_code = preflight.main(["--json"])

    assert exit_code == 1
    payload = json.loads(output_buffer.getvalue().decode("utf-8"))
    assert payload["status"] == "failed"
    assert payload["total"] == 2
    assert payload["failed"] == 1
    assert payload["failed_keys"] == ["bad"]
    assert payload["checks"][1]["action"] == "fix it"
    assert payload["metadata"]["generated_at"] == "2026-06-11T10:30:00Z"
    assert payload["metadata"]["project_root"] == str(preflight.ROOT_DIR)
    assert payload["metadata"]["app_version"] == preflight.APP_VERSION
    assert payload["metadata"]["smoke_base_url"] == preflight.DEFAULT_SMOKE_BASE_URL
    assert payload["plan"]


def test_json_report_does_not_leak_secret_values(monkeypatch) -> None:
    preflight = load_preflight_module()
    secret_values = (
        "admin-secret-value",
        "mimo-secret-value",
        "youzan-client-secret-value",
        "wecom-token-secret-value",
    )
    monkeypatch.setattr(preflight.settings, "ADMIN_API_TOKEN", secret_values[0])
    monkeypatch.setattr(preflight.settings, "MIMO_API_KEY", secret_values[1])
    monkeypatch.setattr(preflight.settings, "YOUZAN_CLIENT_SECRET", secret_values[2])
    monkeypatch.setattr(preflight.settings, "WECOM_TOKEN", secret_values[3])
    checks = preflight.build_preflight_checks()

    payload = preflight.build_json_report(checks)

    _assert_json_does_not_leak_secret_values(payload, secret_values)


def test_main_json_output_can_be_written_to_file(monkeypatch, tmp_path: Path) -> None:
    preflight = load_preflight_module()
    report_path = tmp_path / "reports" / "preflight.json"
    monkeypatch.setattr(
        preflight,
        "build_preflight_checks",
        lambda db_path=None, index_path=None: [
            preflight.PreflightCheck("ok", "OK", True, "ready", ""),
        ],
    )
    monkeypatch.setattr(preflight, "datetime", _FrozenDateTime)

    exit_code = preflight.main(["--json", "--output", str(report_path)])

    assert exit_code == 0
    assert report_path.read_bytes().startswith(preflight.UTF8_BOM)
    payload = json.loads(report_path.read_text(encoding="utf-8-sig"))
    assert payload["status"] == "ready"
    assert payload["metadata"]["generated_at"] == "2026-06-11T10:30:00Z"


def test_main_json_output_expands_timestamp_placeholder(
    monkeypatch,
    tmp_path: Path,
) -> None:
    preflight = load_preflight_module()
    report_template = tmp_path / "reports" / "preflight-{timestamp}.json"
    expected_path = tmp_path / "reports" / "preflight-20260611-103000.json"
    monkeypatch.setattr(
        preflight,
        "build_preflight_checks",
        lambda db_path=None, index_path=None: [
            preflight.PreflightCheck("ok", "OK", True, "ready", ""),
        ],
    )
    monkeypatch.setattr(preflight, "datetime", _FrozenDateTime)

    exit_code = preflight.main(["--json", "--output", str(report_template)])

    assert exit_code == 0
    assert expected_path.exists() is True
    assert report_template.exists() is False


def test_parse_args_help_mentions_timestamp_placeholder(capsys) -> None:
    preflight = load_preflight_module()

    try:
        preflight.parse_args(["--help"])
    except SystemExit as exc:
        assert exc.code == 0

    help_text = capsys.readouterr().out
    assert "{timestamp}" in help_text
    assert "YYYYMMDD-HHMMSS" in help_text


def test_main_json_output_refuses_to_overwrite_file(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    preflight = load_preflight_module()
    report_path = tmp_path / "preflight.json"
    report_path.write_text("existing", encoding="utf-8")
    monkeypatch.setattr(
        preflight,
        "build_preflight_checks",
        lambda db_path=None, index_path=None: [
            preflight.PreflightCheck("ok", "OK", True, "ready", ""),
        ],
    )

    exit_code = preflight.main(["--json", "--output", str(report_path)])

    assert exit_code == 2
    assert report_path.read_text(encoding="utf-8") == "existing"
    assert "拒绝覆盖" in capsys.readouterr().err


def test_main_output_requires_json_flag(capsys, tmp_path: Path) -> None:
    preflight = load_preflight_module()

    exit_code = preflight.main(["--output", str(tmp_path / "preflight.json")])

    assert exit_code == 2
    assert "--output 必须配合 --json 使用" in capsys.readouterr().err


def test_main_rejects_invalid_smoke_base_url(capsys) -> None:
    preflight = load_preflight_module()

    exit_code = preflight.main(["--smoke-base-url", "https://bot.example.com/ready"])

    assert exit_code == 2
    assert "--smoke-base-url" in capsys.readouterr().err


def test_build_recovery_plan_orders_database_knowledge_and_embedding_steps(
    tmp_path: Path,
) -> None:
    preflight = load_preflight_module()
    db_path = tmp_path / "prod" / "bot.db"
    index_path = tmp_path / "prod" / "embeddings"
    checks = [
        preflight.PreflightCheck(
            "database.required_tables",
            "database",
            False,
            "missing=knowledge_base",
            "run migrations",
        ),
        preflight.PreflightCheck(
            "knowledge.active_rows",
            "knowledge",
            False,
            "active_rows=0",
            "seed knowledge",
        ),
        preflight.PreflightCheck(
            "embedding.cache_files",
            "embedding",
            False,
            "expected=embeddings",
            "rebuild embeddings",
        ),
    ]

    plan = preflight.build_recovery_plan(checks, str(db_path), str(index_path))

    assert [step.title for step in plan] == [
        "补齐数据库结构",
        "导入可服务知识",
        "重建向量缓存",
        "最终上线验证",
    ]
    assert [step.key for step in plan] == [
        "database_schema",
        "knowledge_seed",
        "embedding_cache",
        "final_validation",
    ]
    assert [step.severity for step in plan] == [
        "critical",
        "critical",
        "critical",
        "critical",
    ]
    assert "scripts/apply_migrations.py" in plan[0].command
    assert "scripts/seed_baseline_knowledge.py" in plan[1].command
    assert "scripts/rebuild_embeddings.py" in plan[2].command
    assert str(db_path) in plan[0].apply_command
    assert str(index_path) in plan[2].apply_command
    assert all("--apply" not in step.command for step in plan[:3])
    assert all(step.verify_command for step in plan)
    assert all(step.apply_mutates_state is True for step in plan[:3])
    assert plan[-1].apply_mutates_state is False
    assert (
        plan[-1].apply_command == "python scripts/smoke_test.py "
        f'--base-url http://127.0.0.1:7001 --db-path "{db_path}" '
        f'--index-path "{index_path}"'
    )
    assert (
        plan[-1].verify_command == "python scripts/smoke_test.py --json "
        f'--base-url http://127.0.0.1:7001 --db-path "{db_path}" '
        f'--index-path "{index_path}" --output reports/smoke-after-{{timestamp}}.json'
    )


def test_build_recovery_plan_allows_database_create_only_when_file_missing(
    tmp_path: Path,
) -> None:
    preflight = load_preflight_module()
    missing_db_path = tmp_path / "missing" / "bot.db"
    existing_db_path = tmp_path / "existing.db"
    existing_db_path.write_bytes(b"")
    index_path = tmp_path / "embeddings"

    missing_plan = preflight.build_recovery_plan(
        [
            preflight.PreflightCheck(
                "database_path_exists",
                "database",
                False,
                "failed",
                "create database",
            )
        ],
        str(missing_db_path),
        str(index_path),
    )
    existing_plan = preflight.build_recovery_plan(
        [
            preflight.PreflightCheck(
                "database.required_tables",
                "database",
                False,
                "missing=knowledge_base",
                "run migrations",
            )
        ],
        str(existing_db_path),
        str(index_path),
    )

    assert "--allow-create" in missing_plan[0].apply_command
    assert "--allow-create" not in existing_plan[0].apply_command


def test_build_database_detail_check_reports_unreadable_database(
    tmp_path: Path,
) -> None:
    preflight = load_preflight_module()
    db_path = tmp_path / "bot.db"
    db_path.write_text("not a sqlite database", encoding="utf-8")

    check = preflight.build_database_detail_check(str(db_path))

    assert check.key == "database.readable"
    assert check.passed is False
    assert check.detail == "database_not_readable"
    assert "--apply" in check.action
    assert "不要直接执行" in check.action


def test_build_database_columns_detail_check_reports_missing_columns(
    tmp_path: Path,
) -> None:
    preflight = load_preflight_module()
    db_path = tmp_path / "bot.db"
    _create_required_tables(preflight, db_path)
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("ALTER TABLE knowledge_base RENAME TO old_knowledge_base")
        conn.execute(
            "CREATE TABLE knowledge_base ("
            "id INTEGER PRIMARY KEY, "
            "is_active INTEGER DEFAULT 1)"
        )
        conn.execute("DROP TABLE old_knowledge_base")

    check = preflight.build_database_columns_detail_check(str(db_path))

    assert check.key == "database.required_columns"
    assert check.passed is False
    assert "knowledge_base.audience" in check.detail
    assert "apply_migrations.py" in check.action


def test_build_knowledge_detail_check_reports_unreadable_database(
    tmp_path: Path,
) -> None:
    preflight = load_preflight_module()
    db_path = tmp_path / "bot.db"
    db_path.write_text("not a sqlite database", encoding="utf-8")

    check = preflight.build_knowledge_detail_check(str(db_path))

    assert check.key == "knowledge.active_rows"
    assert check.passed is False
    assert check.detail == "database_not_readable"
    assert "seed_baseline_knowledge.py" not in check.action
    assert "--apply" not in check.action


def test_build_recovery_plan_prioritizes_unreadable_database(
    tmp_path: Path,
) -> None:
    preflight = load_preflight_module()
    db_path = tmp_path / "bad.db"
    index_path = tmp_path / "embeddings"
    checks = [
        preflight.PreflightCheck(
            "database.readable",
            "database",
            False,
            "database_not_readable",
            "fix database",
        ),
        preflight.PreflightCheck(
            "database.required_tables",
            "database",
            False,
            "missing=knowledge_base",
            "run migrations",
        ),
        preflight.PreflightCheck(
            "knowledge.active_rows",
            "knowledge",
            False,
            "active_rows=0",
            "seed knowledge",
        ),
        preflight.PreflightCheck(
            "embedding.cache_files",
            "embedding",
            False,
            "expected=embeddings",
            "rebuild embeddings",
        ),
    ]

    plan = preflight.build_recovery_plan(checks, str(db_path), str(index_path))

    assert plan[0].related_keys == ("database.readable",)
    assert plan[0].key == "database_file"
    assert plan[0].severity == "critical"
    assert all("apply_migrations.py" not in step.apply_command for step in plan)
    assert all("seed_baseline_knowledge.py" not in step.apply_command for step in plan)
    assert all("rebuild_embeddings.py" not in step.apply_command for step in plan)


def test_build_recovery_plan_includes_admin_frontend_build_step(
    tmp_path: Path,
) -> None:
    preflight = load_preflight_module()
    db_path = tmp_path / "prod" / "bot.db"
    index_path = tmp_path / "prod" / "embeddings"
    checks = [
        preflight.PreflightCheck(
            "admin_frontend_observability_summary_built",
            "admin frontend",
            False,
            "failed",
            "build admin",
        )
    ]

    plan = preflight.build_recovery_plan(checks, str(db_path), str(index_path))

    assert [step.title for step in plan] == ["构建后台产物", "最终上线验证"]
    assert plan[0].key == "admin_dist"
    assert plan[0].severity == "warning"
    assert plan[0].command == "cd web/admin; npm run build:production"
    assert "web/admin/dist" in plan[0].apply_command
    assert plan[0].related_keys == ("admin_frontend_observability_summary_built",)


def test_build_recovery_plan_includes_business_contract_step(
    tmp_path: Path,
) -> None:
    preflight = load_preflight_module()
    db_path = tmp_path / "prod" / "bot.db"
    index_path = tmp_path / "prod" / "embeddings"
    checks = [
        preflight.PreflightCheck(
            "business_contracts.static_checks",
            "business contracts",
            False,
            "failed=1",
            "run contract checks",
        )
    ]

    plan = preflight.build_recovery_plan(checks, str(db_path), str(index_path))

    assert [step.title for step in plan] == ["修复业务合约门禁", "最终上线验证"]
    assert plan[0].key == "business_contracts"
    assert plan[0].severity == "critical"
    assert plan[0].command == "python scripts/check_project.py --skip-tests"
    assert plan[0].apply_mutates_state is False
    assert plan[0].related_keys == ("business_contracts.static_checks",)


def test_build_json_report_includes_recovery_plan_with_overrides(
    monkeypatch,
    tmp_path: Path,
) -> None:
    preflight = load_preflight_module()
    db_path = tmp_path / "snapshot.db"
    index_path = tmp_path / "snapshot_embeddings"
    monkeypatch.setattr(preflight, "datetime", _FrozenDateTime)
    checks = [
        preflight.PreflightCheck(
            "wecom_bot_plugin_api_key_configured",
            "wecom bot",
            False,
            "failed",
            "set plugin key",
        )
    ]

    payload = preflight.build_json_report(checks, str(db_path), str(index_path))

    assert payload["status"] == "failed"
    assert payload["plan"][0]["title"] == "补齐运行配置"
    assert payload["plan"][0]["key"] == "config"
    assert payload["plan"][0]["severity"] == "critical"
    assert payload["plan"][0]["related_keys"] == ["wecom_bot_plugin_api_key_configured"]
    assert payload["plan"][0]["apply_mutates_state"] is True
    assert payload["plan"][-1]["key"] == "final_validation"
    assert payload["plan"][-1]["severity"] == "critical"
    assert payload["plan"][-1]["apply_mutates_state"] is False
    assert str(db_path) in payload["plan"][0]["verify_command"]
    assert str(index_path) in payload["plan"][0]["verify_command"]
    assert payload["metadata"] == {
        "generated_at": "2026-06-11T10:30:00Z",
        "project_root": str(preflight.ROOT_DIR),
        "database_path": str(db_path),
        "index_path": str(index_path),
        "smoke_base_url": preflight.DEFAULT_SMOKE_BASE_URL,
        "app_version": preflight.APP_VERSION,
    }


def test_build_json_report_uses_smoke_base_url_override(
    tmp_path: Path,
) -> None:
    preflight = load_preflight_module()
    db_path = tmp_path / "prod.db"
    index_path = tmp_path / "prod_embeddings"
    checks = [
        preflight.PreflightCheck(
            "knowledge.active_rows",
            "knowledge",
            False,
            "active_rows=0",
            "seed knowledge",
        )
    ]

    payload = preflight.build_json_report(
        checks,
        str(db_path),
        str(index_path),
        "https://bot.example.com",
    )

    final_step = payload["plan"][-1]
    assert payload["metadata"]["smoke_base_url"] == "https://bot.example.com"
    assert "--base-url https://bot.example.com" in final_step["apply_command"]
    assert "--base-url https://bot.example.com" in final_step["verify_command"]


def test_print_report_includes_metadata(monkeypatch, tmp_path: Path, capsys) -> None:
    preflight = load_preflight_module()
    db_path = tmp_path / "prod.db"
    index_path = tmp_path / "prod_embeddings"
    monkeypatch.setattr(preflight, "datetime", _FrozenDateTime)

    preflight.print_report(
        [preflight.PreflightCheck("ok", "OK", True, "ready", "")],
        str(db_path),
        str(index_path),
    )

    output = capsys.readouterr().out
    assert "generated_at=2026-06-11T10:30:00Z" in output
    assert f"project_root={preflight.ROOT_DIR}" in output
    assert f"db_path={db_path}" in output
    assert f"index_path={index_path}" in output
    assert f"smoke_base_url={preflight.DEFAULT_SMOKE_BASE_URL}" in output
    assert f"app_version={preflight.APP_VERSION}" in output


def test_print_report_marks_apply_mutation_state(
    tmp_path: Path,
    capsys,
) -> None:
    preflight = load_preflight_module()
    db_path = tmp_path / "prod.db"
    index_path = tmp_path / "prod_embeddings"
    checks = [
        preflight.PreflightCheck(
            "knowledge.active_rows",
            "knowledge",
            False,
            "active_rows=0",
            "seed knowledge",
        )
    ]

    preflight.print_report(checks, str(db_path), str(index_path))

    output = capsys.readouterr().out
    assert "[critical] knowledge_seed" in output
    assert "[critical] final_validation" in output
    assert "apply(mutates_state=yes):" in output
    assert "apply(mutates_state=no):" in output
