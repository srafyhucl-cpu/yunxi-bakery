"""生产同步前只读预检报告。"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import APP_VERSION, settings  # noqa: E402
from app.readiness import (  # noqa: E402
    REQUIRED_DATABASE_TABLES,
    build_readiness_checks,
    embedding_index_files_exist,
    get_missing_database_columns,
)
from scripts import check_project  # noqa: E402

MIN_ACTIVE_KNOWLEDGE_ROWS = 1
UTF8_BOM = b"\xef\xbb\xbf"
OUTPUT_TIMESTAMP_PLACEHOLDER = "{timestamp}"
OUTPUT_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"
DEFAULT_SMOKE_BASE_URL = "http://127.0.0.1:7001"
RECOVERY_PLAN_CONFIG_KEYS = frozenset(
    {
        "admin_token_configured",
        "mimo_api_key_configured",
        "youzan_client_id_configured",
        "youzan_client_secret_configured",
        "youzan_kdt_id_configured",
        "youzan_production_mode_ready",
        "wecom_corp_id_configured",
        "wecom_agent_id_configured",
        "wecom_secret_configured",
        "wecom_callback_token_configured",
        "wecom_encoding_aes_key_configured",
        "wecom_kf_id_configured",
        "wecom_bot_plugin_api_key_configured",
        "wecom_intelligent_bot_callback_token_configured",
        "wecom_intelligent_bot_encoding_aes_key_configured",
        "handoff_staff_userid_ready",
    }
)
DATABASE_PLAN_KEYS = frozenset(
    {
        "database_path_exists",
        "database_schema_ready",
        "database.required_tables",
        "database.required_columns",
    }
)
KNOWLEDGE_PLAN_KEYS = frozenset({"knowledge.active_rows"})
EMBEDDING_PLAN_KEYS = frozenset(
    {"embedding_index_path_exists", "embedding.cache_files"}
)
FRONTEND_PLAN_KEYS = frozenset(
    {
        "admin_frontend_index_exists",
        "admin_frontend_assets_exist",
        "admin_frontend_observability_summary_built",
    }
)
BUSINESS_CONTRACT_PLAN_KEYS = frozenset({"business_contracts.static_checks"})
BUSINESS_CONTRACT_LABELS: tuple[tuple[str, str], ...] = (
    (
        "check_employee_agent_capability_contracts.py",
        "employee_agent_capability_contracts",
    ),
    ("check_customer_rag_golden_cases.py", "customer_rag_golden_cases"),
    ("check_knowledge_governance_plan.py", "knowledge_governance_plan"),
    (
        "check_customer_memory_governance_plan.py",
        "customer_memory_governance_plan",
    ),
    (
        "check_customer_observability_contract.py",
        "customer_observability_contract",
    ),
    (
        "check_miniapp_page_api_contract.py",
        "miniapp_page_api_contract",
    ),
    (
        "check_github_reference_implementation_plan.py",
        "github_reference_implementation_plan",
    ),
)

READINESS_ACTIONS = {
    "admin_token_configured": "设置非默认 ADMIN_API_TOKEN，并设置 ADMIN_SESSION_SECRET。",
    "mimo_api_key_configured": "设置 MIMO_API_KEY。",
    "database_path_exists": "确认 DB_PATH 指向生产数据库文件。",
    "database_schema_ready": "先查看 recovery_plan 或运行 scripts/apply_migrations.py dry-run；确认目标库路径后再 --apply。",
    "database.required_columns": "先运行 scripts/apply_migrations.py dry-run 核对目标库；确认无误后再 --apply 补齐缺失字段。",
    "embedding_index_path_exists": (
        "先查看 recovery_plan；知识库确认有有效数据后运行 scripts/rebuild_embeddings.py "
        "dry-run，确认目标路径后再 --apply，或同步 embeddings.npy/json。"
    ),
    "youzan_client_id_configured": "设置 YOUZAN_CLIENT_ID。",
    "youzan_client_secret_configured": "设置 YOUZAN_CLIENT_SECRET。",
    "youzan_kdt_id_configured": "设置 YOUZAN_KDT_ID。",
    "youzan_production_mode_ready": "确认 YOUZAN_MOCK_MODE=False 且有赞凭证完整。",
    "wecom_corp_id_configured": "设置 WECOM_CORP_ID。",
    "wecom_agent_id_configured": "设置 WECOM_AGENT_ID。",
    "wecom_secret_configured": "设置 WECOM_SECRET。",
    "wecom_callback_token_configured": "设置 WECOM_TOKEN，用于企微回调验签。",
    "wecom_encoding_aes_key_configured": "设置 WECOM_ENCODING_AES_KEY，用于企微回调解密。",
    "wecom_kf_id_configured": "设置 WECOM_KF_ID。",
    "wecom_bot_plugin_api_key_configured": "设置 WECOM_BOT_PLUGIN_API_KEY，用于企微智能机器人插件鉴权。",
    "wecom_intelligent_bot_callback_token_configured": "设置 WECOM_INTELLIGENT_BOT_TOKEN，或复用 WECOM_TOKEN。",
    "wecom_intelligent_bot_encoding_aes_key_configured": "设置 WECOM_INTELLIGENT_BOT_ENCODING_AES_KEY，或复用 WECOM_ENCODING_AES_KEY。",
    "handoff_staff_userid_ready": "设置 WECOM_STAFF_ID 或 WECOM_KF_SERVICER_USERID。",
    "wecom_employee_auth_ready": "生产必须开启 WECOM_EMPLOYEE_AUTH_REQUIRED，并配置员工用户、企业 ID 和运营用户白名单。",
    "admin_frontend_index_exists": "在 web/admin 执行 npm run build:production。",
    "admin_frontend_assets_exist": "在 web/admin 执行 npm run build:production。",
    "admin_frontend_observability_summary_built": "重新构建或同步最新 web/admin/dist。",
}


@dataclass(frozen=True)
class PreflightCheck:
    key: str
    title: str
    passed: bool
    detail: str
    action: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "title": self.title,
            "passed": self.passed,
            "detail": self.detail,
            "action": self.action,
        }


@dataclass(frozen=True)
class PreflightPlanStep:
    order: int
    key: str
    severity: str
    title: str
    reason: str
    command: str
    apply_command: str
    verify_command: str
    related_keys: tuple[str, ...]
    apply_mutates_state: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "order": self.order,
            "key": self.key,
            "severity": self.severity,
            "title": self.title,
            "reason": self.reason,
            "command": self.command,
            "apply_command": self.apply_command,
            "verify_command": self.verify_command,
            "related_keys": list(self.related_keys),
            "apply_mutates_state": self.apply_mutates_state,
        }


def resolve_project_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else ROOT_DIR / path


def is_readable_sqlite_database(database_path: Path) -> bool:
    if not database_path.exists():
        return False
    try:
        with closing(sqlite3.connect(database_path)) as conn:
            conn.execute("PRAGMA schema_version").fetchone()
    except sqlite3.Error:
        return False
    return True


def get_missing_database_tables(database_path: Path) -> list[str]:
    if not database_path.exists():
        return list(REQUIRED_DATABASE_TABLES)
    placeholders = ", ".join("?" for _ in REQUIRED_DATABASE_TABLES)
    query = (
        "SELECT name FROM sqlite_master WHERE type = ? "
        + "AND name IN ("
        + placeholders
        + ")"
    )
    try:
        with closing(sqlite3.connect(database_path)) as conn:
            cursor = conn.execute(query, ("table", *REQUIRED_DATABASE_TABLES))
            existing_tables = {str(row[0]) for row in cursor.fetchall()}
    except sqlite3.Error:
        return list(REQUIRED_DATABASE_TABLES)
    return sorted(set(REQUIRED_DATABASE_TABLES) - existing_tables)


def count_active_knowledge_rows(database_path: Path) -> int:
    if not database_path.exists():
        return 0
    try:
        with closing(sqlite3.connect(database_path)) as conn:
            cursor = conn.execute(
                "SELECT COUNT(id) FROM knowledge_base WHERE is_active = ?",
                (1,),
            )
            return int(cursor.fetchone()[0])
    except sqlite3.Error:
        return 0


def build_readiness_preflight_checks(
    *,
    database_path: Path | None = None,
    index_path: Path | None = None,
) -> list[PreflightCheck]:
    checks = build_readiness_checks()
    if database_path is not None:
        checks["database_path_exists"] = database_path.exists()
        checks["database_schema_ready"] = not get_missing_database_tables(database_path)
    if index_path is not None:
        checks["embedding_index_path_exists"] = embedding_index_files_exist(index_path)
    if any(
        str(value).strip()
        for value in (settings.WECOM_TOKEN, settings.WECOM_INTELLIGENT_BOT_TOKEN)
    ):
        checks["wecom_employee_auth_ready"] = (
            settings.WECOM_EMPLOYEE_AUTH_REQUIRED
            and bool(settings.WECOM_EMPLOYEE_ALLOWED_USERS.strip())
            and bool(settings.WECOM_EMPLOYEE_CORP_ID.strip())
            and bool(settings.WECOM_EMPLOYEE_OPS_USERS.strip())
        )
    return [
        PreflightCheck(
            key=key,
            title=f"readiness.{key}",
            passed=passed,
            detail="ready" if passed else "failed",
            action="" if passed else READINESS_ACTIONS.get(key, "查看 /ready 失败项。"),
        )
        for key, passed in checks.items()
    ]


def build_database_detail_check(db_path_value: str | None = None) -> PreflightCheck:
    database_path = resolve_project_path(db_path_value or settings.DB_PATH)
    if database_path.exists() and not is_readable_sqlite_database(database_path):
        return PreflightCheck(
            key="database.readable",
            title="数据库文件可读性",
            passed=False,
            detail="database_not_readable",
            action="目标文件不是可读 SQLite 数据库；先核对 DB 路径或恢复数据库文件，不要直接执行 --apply。",
        )
    missing_tables = get_missing_database_tables(database_path)
    return PreflightCheck(
        key="database.required_tables",
        title="数据库关键表明细",
        passed=not missing_tables,
        detail="missing=" + ", ".join(missing_tables) if missing_tables else "ready",
        action=""
        if not missing_tables
        else "先运行 scripts/apply_migrations.py dry-run 核对目标库；确认无误后再 --apply 补齐缺失表。",
    )


def build_database_columns_detail_check(
    db_path_value: str | None = None,
) -> PreflightCheck:
    database_path = resolve_project_path(db_path_value or settings.DB_PATH)
    if database_path.exists() and not is_readable_sqlite_database(database_path):
        return PreflightCheck(
            key="database.readable",
            title="数据库文件可读性",
            passed=False,
            detail="database_not_readable",
            action="目标文件不是可读 SQLite 数据库；先核对 DB 路径或恢复数据库文件，不要直接执行 --apply。",
        )
    missing_columns = get_missing_database_columns(database_path)
    return PreflightCheck(
        key="database.required_columns",
        title="数据库关键字段明细",
        passed=not missing_columns,
        detail="missing=" + ", ".join(missing_columns) if missing_columns else "ready",
        action=""
        if not missing_columns
        else "先运行 scripts/apply_migrations.py dry-run 核对目标库；确认无误后再 --apply 补齐缺失字段。",
    )


def build_knowledge_detail_check(db_path_value: str | None = None) -> PreflightCheck:
    database_path = resolve_project_path(db_path_value or settings.DB_PATH)
    if database_path.exists() and not is_readable_sqlite_database(database_path):
        return PreflightCheck(
            key="knowledge.active_rows",
            title="知识库有效数据",
            passed=False,
            detail="database_not_readable",
            action="先核对 DB 路径或恢复数据库文件；数据库可读后再检查知识库有效数据。",
        )
    active_rows = count_active_knowledge_rows(database_path)
    return PreflightCheck(
        key="knowledge.active_rows",
        title="知识库有效数据",
        passed=active_rows >= MIN_ACTIVE_KNOWLEDGE_ROWS,
        detail=f"active_rows={active_rows}",
        action=""
        if active_rows
        else (
            "先同步有赞商品到 RAG；若需要最低可服务兜底，先运行 "
            "scripts/seed_baseline_knowledge.py dry-run，确认目标库后再 --apply，"
            "之后重建向量。"
        ),
    )


def build_embedding_detail_check(index_path_value: str | None = None) -> PreflightCheck:
    index_path = resolve_project_path(index_path_value or settings.EMBEDDING_INDEX_DIR)
    expected_paths = [index_path.with_suffix(".npy"), index_path.with_suffix(".json")]
    missing_paths = [str(path) for path in expected_paths if not path.exists()]
    if not missing_paths and not embedding_index_files_exist(index_path):
        return PreflightCheck(
            key="embedding.cache_files",
            title="向量索引缓存文件",
            passed=False,
            detail="invalid_cache=" + ", ".join(str(path) for path in expected_paths),
            action=(
                "向量缓存文件存在但不可读或元数据不合法；先运行 "
                "scripts/rebuild_embeddings.py dry-run，确认目标路径后再 --apply。"
            ),
        )
    index_path = resolve_project_path(index_path_value or settings.EMBEDDING_INDEX_DIR)
    expected_paths = [index_path.with_suffix(".npy"), index_path.with_suffix(".json")]
    missing_paths = [str(path) for path in expected_paths if not path.exists()]
    cache_ready = embedding_index_files_exist(index_path)
    if missing_paths:
        return PreflightCheck(
            key="embedding.cache_files",
            title="向量索引缓存文件",
            passed=False,
            detail="expected=" + ", ".join(str(path) for path in expected_paths),
            action=(
                "先查看 recovery_plan；知识库导入后运行 scripts/rebuild_embeddings.py "
                "dry-run，确认目标路径后再 --apply，或同步缺失文件: "
                + ", ".join(missing_paths)
            ),
        )
    if not cache_ready:
        return PreflightCheck(
            key="embedding.cache_files",
            title="向量索引缓存文件",
            passed=False,
            detail="expected=" + ", ".join(str(path) for path in expected_paths),
            action=(
                "向量缓存文件存在但不可读或元数据不合法；先运行 "
                "scripts/rebuild_embeddings.py dry-run，确认目标路径后再 --apply。"
            ),
        )
    return PreflightCheck(
        key="embedding.cache_files",
        title="向量索引缓存文件",
        passed=embedding_index_files_exist(index_path),
        detail="expected=" + ", ".join(str(path) for path in expected_paths),
        action=""
        if not missing_paths
        else "先查看 recovery_plan；知识库导入后运行 scripts/rebuild_embeddings.py dry-run，"
        "确认目标路径后再 --apply，或同步缺失文件: " + ", ".join(missing_paths),
    )


def build_business_contract_check() -> PreflightCheck:
    contract_results = check_project.run_contract_checks()
    failed_results = [result for result in contract_results if not result.passed]
    detail_parts = [
        f"total={len(contract_results)}",
        f"failed={len(failed_results)}",
        "checks=" + _format_business_contract_results(contract_results),
    ]
    if failed_results:
        failed_names = ", ".join(
            _business_contract_label(result.name) for result in failed_results
        )
        detail_parts.append(f"failed_names={failed_names}")
    return PreflightCheck(
        key="business_contracts.static_checks",
        title="业务合约静态检查",
        passed=not failed_results,
        detail=" ".join(detail_parts),
        action=""
        if not failed_results
        else (
            "运行 python scripts/check_project.py --skip-tests；修复员工助手能力合约、"
            "客户 RAG golden cases、知识治理计划、客户长期记忆治理计划或"
            "客户机器人可观测合约、MiniApp 页面 API 覆盖合约或"
            "GitHub 参考实施计划后再预检。"
        ),
    )


def _format_business_contract_results(
    contract_results: list[check_project.CheckResult],
) -> str:
    return ", ".join(
        f"{_business_contract_label(result.name)}:{'passed' if result.passed else 'failed'}"
        for result in contract_results
    )


def _business_contract_label(result_name: str) -> str:
    for script_name, label in BUSINESS_CONTRACT_LABELS:
        if script_name in result_name:
            return label
    return result_name


def build_preflight_checks(
    db_path_value: str | None = None,
    index_path_value: str | None = None,
) -> list[PreflightCheck]:
    database_path = resolve_project_path(db_path_value) if db_path_value else None
    index_path = resolve_project_path(index_path_value) if index_path_value else None
    return [
        *build_readiness_preflight_checks(
            database_path=database_path,
            index_path=index_path,
        ),
        build_database_detail_check(db_path_value),
        build_database_columns_detail_check(db_path_value),
        build_knowledge_detail_check(db_path_value),
        build_embedding_detail_check(index_path_value),
        build_business_contract_check(),
    ]


def build_report_metadata(
    db_path_value: str | None = None,
    index_path_value: str | None = None,
    smoke_base_url: str = DEFAULT_SMOKE_BASE_URL,
) -> dict[str, str]:
    database_path = resolve_project_path(db_path_value or settings.DB_PATH)
    index_path = resolve_project_path(index_path_value or settings.EMBEDDING_INDEX_DIR)
    generated_at = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    return {
        "generated_at": generated_at,
        "project_root": str(ROOT_DIR),
        "database_path": str(database_path),
        "index_path": str(index_path),
        "smoke_base_url": smoke_base_url,
        "app_version": APP_VERSION,
    }


def _quoted_path(path: Path) -> str:
    return '"' + str(path) + '"'


def validate_smoke_base_url(smoke_base_url: str) -> None:
    parsed_url = urlparse(smoke_base_url)
    if parsed_url.scheme not in {"http", "https"}:
        raise ValueError("--smoke-base-url 仅支持 http 或 https。")
    if not parsed_url.hostname:
        raise ValueError("--smoke-base-url 必须包含主机名。")
    if parsed_url.path not in {"", "/"} or parsed_url.params or parsed_url.query:
        raise ValueError("--smoke-base-url 只接受根地址，不要包含路径、参数或查询串。")


def _preflight_command(
    database_path: Path,
    index_path: Path,
    smoke_base_url: str = DEFAULT_SMOKE_BASE_URL,
) -> str:
    return (
        "python scripts/preflight_production.py "
        f"--db-path {_quoted_path(database_path)} "
        f"--index-path {_quoted_path(index_path)} "
        f"--smoke-base-url {smoke_base_url}"
    )


def _smoke_json_command(
    database_path: Path,
    index_path: Path,
    smoke_base_url: str,
) -> str:
    return (
        "python scripts/smoke_test.py --json "
        f"--base-url {smoke_base_url} "
        f"--db-path {_quoted_path(database_path)} "
        f"--index-path {_quoted_path(index_path)} "
        "--output reports/smoke-after-{timestamp}.json"
    )


def _smoke_text_command(
    database_path: Path,
    index_path: Path,
    smoke_base_url: str,
) -> str:
    return (
        "python scripts/smoke_test.py "
        f"--base-url {smoke_base_url} "
        f"--db-path {_quoted_path(database_path)} "
        f"--index-path {_quoted_path(index_path)}"
    )


def _matching_failed_keys(
    failed_keys: set[str], plan_keys: frozenset[str]
) -> tuple[str, ...]:
    return tuple(sorted(failed_keys & plan_keys))


def build_recovery_plan(
    checks: list[PreflightCheck],
    db_path_value: str | None = None,
    index_path_value: str | None = None,
    smoke_base_url: str = DEFAULT_SMOKE_BASE_URL,
) -> list[PreflightPlanStep]:
    failed_keys = {check.key for check in checks if not check.passed}
    if not failed_keys:
        return []

    database_path = resolve_project_path(db_path_value or settings.DB_PATH)
    index_path = resolve_project_path(index_path_value or settings.EMBEDDING_INDEX_DIR)
    verify_command = _preflight_command(database_path, index_path, smoke_base_url)
    steps: list[PreflightPlanStep] = []

    if "database.readable" in failed_keys:
        steps.append(
            PreflightPlanStep(
                order=len(steps) + 1,
                key="database_file",
                severity="critical",
                title="核对数据库文件",
                reason="目标 DB 路径存在但不是可读 SQLite 数据库，继续迁移可能覆盖或误修错误文件。",
                command="核对 --db-path 指向真实生产数据库；必要时先从备份恢复数据库文件。",
                apply_command="修正 DB_PATH 或恢复数据库后，再运行 python scripts/preflight_production.py。",
                verify_command=verify_command,
                related_keys=("database.readable",),
                apply_mutates_state=True,
            )
        )
        failed_keys = (
            failed_keys
            - DATABASE_PLAN_KEYS
            - KNOWLEDGE_PLAN_KEYS
            - EMBEDDING_PLAN_KEYS
            - {"database.readable"}
        )

    config_keys = _matching_failed_keys(failed_keys, RECOVERY_PLAN_CONFIG_KEYS)
    if config_keys:
        steps.append(
            PreflightPlanStep(
                order=len(steps) + 1,
                key="config",
                severity="critical",
                title="补齐运行配置",
                reason="生产通道或人工接手配置仍有缺口。",
                command="检查 .env 或部署平台环境变量；本步骤不自动改写配置。",
                apply_command="按失败项设置环境变量后重启服务。",
                verify_command=verify_command,
                related_keys=config_keys,
                apply_mutates_state=True,
            )
        )

    database_keys = _matching_failed_keys(failed_keys, DATABASE_PLAN_KEYS)
    if database_keys:
        migration_command = (
            "python scripts/apply_migrations.py --db-path "
            f"{_quoted_path(database_path)}"
        )
        migration_apply_command = migration_command + " --apply"
        if "database_path_exists" in database_keys and not database_path.exists():
            migration_apply_command += " --allow-create"
        steps.append(
            PreflightPlanStep(
                order=len(steps) + 1,
                key="database_schema",
                severity="critical",
                title="补齐数据库结构",
                reason="关键表缺失会阻断会话、转人工、画像、质检和企微同步链路。",
                command=migration_command,
                apply_command=migration_apply_command,
                verify_command=verify_command,
                related_keys=database_keys,
                apply_mutates_state=True,
            )
        )

    knowledge_keys = _matching_failed_keys(failed_keys, KNOWLEDGE_PLAN_KEYS)
    if knowledge_keys:
        seed_command = (
            "python scripts/seed_baseline_knowledge.py --db-path "
            f"{_quoted_path(database_path)}"
        )
        steps.append(
            PreflightPlanStep(
                order=len(steps) + 1,
                key="knowledge_seed",
                severity="critical",
                title="导入可服务知识",
                reason="知识库为空时 AI 只能转人工，无法稳定回答基础客服问题。",
                command=seed_command,
                apply_command=seed_command + " --apply",
                verify_command=verify_command,
                related_keys=knowledge_keys,
                apply_mutates_state=True,
            )
        )

    embedding_keys = _matching_failed_keys(failed_keys, EMBEDDING_PLAN_KEYS)
    if embedding_keys:
        rebuild_command = (
            "python scripts/rebuild_embeddings.py "
            f"--db-path {_quoted_path(database_path)} "
            f"--index-path {_quoted_path(index_path)}"
        )
        steps.append(
            PreflightPlanStep(
                order=len(steps) + 1,
                key="embedding_cache",
                severity="critical",
                title="重建向量缓存",
                reason="缺少 embeddings.npy/json 时检索增强不可用，回答质量会明显退化。",
                command=rebuild_command,
                apply_command=rebuild_command + " --apply",
                verify_command=verify_command,
                related_keys=embedding_keys,
                apply_mutates_state=True,
            )
        )

    frontend_keys = _matching_failed_keys(failed_keys, FRONTEND_PLAN_KEYS)
    if frontend_keys:
        steps.append(
            PreflightPlanStep(
                order=len(steps) + 1,
                key="admin_dist",
                severity="warning",
                title="构建后台产物",
                reason="后台 dist 缺失或过旧会让值守摘要和管理台展示与后端不一致。",
                command="cd web/admin; npm run build:production",
                apply_command="同步或保留最新 web/admin/dist 到生产环境。",
                verify_command=verify_command,
                related_keys=frontend_keys,
                apply_mutates_state=True,
            )
        )

    business_contract_keys = _matching_failed_keys(
        failed_keys,
        BUSINESS_CONTRACT_PLAN_KEYS,
    )
    if business_contract_keys:
        steps.append(
            PreflightPlanStep(
                order=len(steps) + 1,
                key="business_contracts",
                severity="critical",
                title="修复业务合约门禁",
                reason="客户 RAG、知识治理、长期记忆治理、客户机器人可观测、MiniApp 页面 API 覆盖或员工助手能力合约静态检查失败，发布会绕过已冻结边界。",
                command="python scripts/check_project.py --skip-tests",
                apply_command="修复失败合约对应的 fixture、治理计划或能力合约后，重新运行统一质量门禁。",
                verify_command=verify_command,
                related_keys=business_contract_keys,
                apply_mutates_state=False,
            )
        )

    steps.append(
        PreflightPlanStep(
            order=len(steps) + 1,
            key="final_validation",
            severity="critical",
            title="最终上线验证",
            reason="所有修复动作完成后，需要用同一目标路径复查并执行冒烟。",
            command=verify_command,
            apply_command=_smoke_text_command(
                database_path,
                index_path,
                smoke_base_url,
            ),
            verify_command=(
                _smoke_json_command(database_path, index_path, smoke_base_url)
            ),
            related_keys=tuple(sorted(failed_keys)),
            apply_mutates_state=False,
        )
    )
    return steps


def print_report(
    checks: list[PreflightCheck],
    db_path_value: str | None = None,
    index_path_value: str | None = None,
    smoke_base_url: str = DEFAULT_SMOKE_BASE_URL,
) -> None:
    failed_checks = [check for check in checks if not check.passed]
    metadata = build_report_metadata(db_path_value, index_path_value, smoke_base_url)
    print("Platform production preflight")
    print(f"generated_at={metadata['generated_at']}")
    print(f"project_root={metadata['project_root']}")
    print(f"db_path={metadata['database_path']}")
    print(f"index_path={metadata['index_path']}")
    print(f"smoke_base_url={metadata['smoke_base_url']}")
    print(f"app_version={metadata['app_version']}")
    print(f"total={len(checks)} failed={len(failed_checks)}")
    for check in checks:
        status = "PASS" if check.passed else "FAIL"
        print(f"{status} {check.key}: {check.detail}")
        if check.action:
            print(f"  action: {check.action}")
    plan = build_recovery_plan(
        checks,
        db_path_value,
        index_path_value,
        smoke_base_url,
    )
    if plan:
        print("recovery_plan:")
        for step in plan:
            print(
                f"  {step.order}. [{step.severity}] {step.key} - {step.title}: {step.reason}"
            )
            print(f"     check: {step.command}")
            mutation_label = "yes" if step.apply_mutates_state else "no"
            print(f"     apply(mutates_state={mutation_label}): {step.apply_command}")
            print(f"     verify: {step.verify_command}")


def build_json_report(
    checks: list[PreflightCheck],
    db_path_value: str | None = None,
    index_path_value: str | None = None,
    smoke_base_url: str = DEFAULT_SMOKE_BASE_URL,
) -> dict[str, object]:
    failed_checks = [check for check in checks if not check.passed]
    plan = build_recovery_plan(
        checks,
        db_path_value,
        index_path_value,
        smoke_base_url,
    )
    return {
        "status": "ready" if not failed_checks else "failed",
        "metadata": build_report_metadata(
            db_path_value,
            index_path_value,
            smoke_base_url,
        ),
        "total": len(checks),
        "failed": len(failed_checks),
        "checks": [check.to_dict() for check in checks],
        "failed_keys": [check.key for check in failed_checks],
        "plan": [step.to_dict() for step in plan],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Platform production preflight")
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出机器可读 JSON，便于部署脚本保存或解析。",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="覆盖预检使用的 SQLite 数据库路径，默认读取 DB_PATH。",
    )
    parser.add_argument(
        "--index-path",
        default=None,
        help="覆盖预检使用的向量索引基路径，默认读取 EMBEDDING_INDEX_DIR。",
    )
    parser.add_argument(
        "--smoke-base-url",
        default=DEFAULT_SMOKE_BASE_URL,
        help=(
            "覆盖 recovery_plan 最终冒烟命令使用的服务根地址；"
            "只影响报告中的 smoke 命令，不改变本次预检目标。"
        ),
    )
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "配合 --json 使用，将报告写入指定文件；目标文件已存在时会拒绝覆盖；"
            "支持 {timestamp} 自动展开为 YYYYMMDD-HHMMSS。"
        ),
    )
    return parser.parse_args(argv)


def expand_output_path(output_path_value: str) -> Path:
    timestamp = datetime.now().strftime(OUTPUT_TIMESTAMP_FORMAT)
    expanded_value = output_path_value.replace(OUTPUT_TIMESTAMP_PLACEHOLDER, timestamp)
    return Path(expanded_value)


def write_json_report(output_path: Path, json_bytes: bytes) -> None:
    if output_path.exists():
        raise FileExistsError(f"报告文件已存在，拒绝覆盖: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(UTF8_BOM + json_bytes)


def ensure_output_path_available(output_path_value: str) -> None:
    output_path = expand_output_path(output_path_value)
    if output_path.exists():
        raise FileExistsError(f"报告文件已存在，拒绝覆盖: {output_path}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        validate_smoke_base_url(args.smoke_base_url)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.output and not args.json:
        print("--output 必须配合 --json 使用。", file=sys.stderr)
        return 2
    if args.output:
        try:
            output_path = expand_output_path(args.output)
            ensure_output_path_available(str(output_path))
        except FileExistsError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    else:
        output_path = None
    checks = build_preflight_checks(args.db_path, args.index_path)
    if args.json:
        json_bytes = (
            json.dumps(
                build_json_report(
                    checks,
                    args.db_path,
                    args.index_path,
                    args.smoke_base_url,
                ),
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        ).encode("utf-8")
        if args.output:
            try:
                assert output_path is not None
                write_json_report(output_path, json_bytes)
            except FileExistsError as exc:
                print(str(exc), file=sys.stderr)
                return 2
        else:
            sys.stdout.buffer.write(json_bytes)
    else:
        print_report(checks, args.db_path, args.index_path, args.smoke_base_url)
    return 1 if any(not check.passed for check in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
