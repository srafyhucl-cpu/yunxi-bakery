"""生产同步前只读预检报告。"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sqlite3
import sys
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
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

try:
    from scripts import check_project  # noqa: E402
except ImportError:
    check_project = None

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
        "wecom_employee_auth_ready",
        "mock_payment_disabled",
        "wechat_pay_configured",
        "edge_protection_shared_ready",
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
    "mimo_api_key_configured": "设置 MIMO_API_KEY。",  # pragma: allowlist secret
    "database_path_exists": "确认 DB_PATH 指向生产数据库文件。",
    "database_schema_ready": "先查看 recovery_plan 或运行 scripts/apply_migrations.py dry-run；确认目标库路径后再 --apply。",
    "database.required_columns": "先运行 scripts/apply_migrations.py dry-run 核对目标库；确认无误后再 --apply 补齐缺失字段。",
    "embedding_index_path_exists": (
        "先查看 recovery_plan；知识库确认有有效数据后运行 scripts/rebuild_embeddings.py "
        "dry-run，确认目标路径后再 --apply，或同步 embeddings.npy/json。"
    ),
    "youzan_client_id_configured": "设置 YOUZAN_CLIENT_ID。",
    "youzan_client_secret_configured": "设置 YOUZAN_CLIENT_SECRET。",  # pragma: allowlist secret
    "youzan_kdt_id_configured": "设置 YOUZAN_KDT_ID。",
    "youzan_production_mode_ready": "确认 YOUZAN_MOCK_MODE=False 且有赞凭证完整。",
    "wecom_corp_id_configured": "设置 WECOM_CORP_ID。",
    "wecom_agent_id_configured": "设置 WECOM_AGENT_ID。",
    "wecom_secret_configured": "设置 WECOM_SECRET。",  # pragma: allowlist secret
    "wecom_callback_token_configured": "设置 WECOM_TOKEN，用于企微回调验签。",
    "wecom_encoding_aes_key_configured": "设置 WECOM_ENCODING_AES_KEY，用于企微回调解密。",
    "wecom_kf_id_configured": "设置 WECOM_KF_ID。",
    "wecom_bot_plugin_api_key_configured": "设置 WECOM_BOT_PLUGIN_API_KEY，用于企微智能机器人插件鉴权。",  # pragma: allowlist secret
    "wecom_intelligent_bot_callback_token_configured": "设置 WECOM_INTELLIGENT_BOT_TOKEN，或复用 WECOM_TOKEN。",
    "wecom_intelligent_bot_encoding_aes_key_configured": "设置 WECOM_INTELLIGENT_BOT_ENCODING_AES_KEY，或复用 WECOM_ENCODING_AES_KEY。",
    "handoff_staff_userid_ready": "设置 WECOM_STAFF_ID 或 WECOM_KF_SERVICER_USERID。",
    "wecom_employee_auth_ready": "生产必须开启 WECOM_EMPLOYEE_AUTH_REQUIRED，并配置员工用户、企业 ID 和运营用户白名单。",
    "mock_payment_disabled": "生产必须关闭 ALLOW_MOCK_PAYMENT，mock 只允许显式测试环境。",
    "wechat_pay_configured": "设置 WECHAT_PAY_ENABLED 并补齐商户号、回调地址、证书与 APIv3 密钥。",
    "edge_protection_shared_ready": "生产要求共享防护时设置 EDGE_PROTECTION_BACKEND=redis 并配置 EDGE_REDIS_URL；单机本地保持 sqlite 并明确不用于多机。",
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


# ── 最小商用安全红线（内联实现） ──────────────────────────────────────────────
# 背景：统一质量门禁脚本归档后，生产预检曾在“门禁脚本缺失”时直接判定无违规，
# 形成假绿。这里内联实现一组最小商用红线规则：任一命中即判失败，
# 保证预检永远 fail-closed，不再出现“检查缺失 => 通过”。
# 规则只覆盖会直接影响商用交易闭环、账目准确与分层架构的硬红线，
# 不恢复整套已归档的元治理脚本体系。

APP_DIR = ROOT_DIR / "app"
MINIMAL_RED_LINE_SELECT_STAR = re.compile(r"SELECT\s+\*", re.IGNORECASE)
# 只匹配 f-string 片段自身以 SQL 关键字开头的情况（与归档门禁口径一致）。
MINIMAL_RED_LINE_SQL_FSTRING_LITERAL = re.compile(
    r"f[\"'](?:SELECT|INSERT|UPDATE|DELETE)\b",
    re.IGNORECASE,
)
MINIMAL_RED_LINE_HIT_LIMIT = 20
INLINE_RED_LINE_MODE = "inline_minimal"
CHECK_PROJECT_MODE = "check_project"


@dataclass(frozen=True)
class MinimalRedLineRule:
    """最小商用红线规则定义。"""

    name: str
    scope: str
    detector: Callable[["_RedLineFileContext"], list[str]]


@dataclass(frozen=True)
class MinimalRedLineCheck:
    """单条商用红线的检查结果。"""

    name: str
    passed: bool
    hits: tuple[str, ...]

    @property
    def violation_count(self) -> int:
        return len(self.hits)


@dataclass(frozen=True)
class _RedLineFileContext:
    """单个待检查文件的上下文。"""

    rel_path: str
    source: str
    tree: ast.AST


def _iter_app_python_files(app_dir: Path) -> list[Path]:
    """收集 app 目录下的 Python 文件，跳过 __pycache__。"""
    return sorted(
        path for path in app_dir.rglob("*.py") if "__pycache__" not in path.parts
    )


def _relative_app_path(file_path: Path, app_dir: Path) -> str:
    """把文件路径转成相对 app 根目录的 posix 路径，便于报告定位。"""
    try:
        return file_path.relative_to(app_dir).as_posix()
    except ValueError:
        return file_path.as_posix()


def _is_root_api_compat_file(rel_path: str) -> bool:
    """判断是否为根 API 兼容文件（只允许做兼容转发，不得承载真实 Router）。"""
    parts = rel_path.split("/")
    if len(parts) != 2 or parts[0] != "api":
        return False
    file_name = parts[1]
    if not file_name.endswith(".py"):
        return False
    stem = file_name[:-3]
    if stem == "__init__":
        return False
    return (
        stem.startswith("admin_")
        or stem.startswith("miniapp_")
        or stem.startswith("webhook")
        or stem in {"wecom", "channel_router"}
    )


def _scope_matches(scope: str, rel_path: str) -> bool:
    """判断文件是否落在规则作用域内。"""
    if scope == "app":
        return True
    if scope == "api":
        return rel_path.startswith("api/")
    if scope == "service":
        return rel_path.startswith("service/")
    if scope == "models":
        return rel_path.startswith("models/")
    if scope == "root_api_compat":
        return _is_root_api_compat_file(rel_path)
    return False


def _docstring_constant_ids(tree: ast.AST) -> frozenset[int]:
    """收集文档字符串常量节点，避免把说明文字误判成 SQL 违规。"""
    docstring_ids: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node,
            (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            continue
        body = getattr(node, "body", [])
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            docstring_ids.add(id(first.value))
    return frozenset(docstring_ids)


def _detect_select_star(context: _RedLineFileContext) -> list[str]:
    """禁止 SELECT *：只检查真实 SQL 字符串常量，忽略注释与文档字符串。"""
    docstring_ids = _docstring_constant_ids(context.tree)
    hits: list[str] = []
    for node in ast.walk(context.tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in docstring_ids:
            continue
        if MINIMAL_RED_LINE_SELECT_STAR.search(node.value):
            hits.append(f"{context.rel_path}:{node.lineno}")
    return hits


def _detect_sql_fstring(context: _RedLineFileContext) -> list[str]:
    """禁止 SQL f-string 拼接：必须使用 ? 参数化绑定。

    只判定 f-string 片段自身以 SQL 关键字开头的情况，与归档门禁口径一致；
    隐式拼接的普通 SQL 片段（例如 "SELECT ..." f"WHERE {...}"）不算违规。
    """
    hits: list[str] = []
    for node in ast.walk(context.tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        segment = ast.get_source_segment(context.source, node) or ""
        if MINIMAL_RED_LINE_SQL_FSTRING_LITERAL.search(segment):
            hits.append(f"{context.rel_path}:{node.lineno}")
    return hits


def _detect_silent_except(context: _RedLineFileContext) -> list[str]:
    """禁止静默吞异常：except 分支必须记录 logger.error 而不是静默 pass。

    与归档门禁口径一致，判定同一行内出现的 except ...: pass 形式。
    """
    hits: list[str] = []
    for node in ast.walk(context.tree):
        if not isinstance(node, ast.ExceptHandler) or not node.body:
            continue
        statements = node.body
        if len(statements) != 1 or not isinstance(statements[0], ast.Pass):
            continue
        if statements[0].lineno == node.lineno:
            hits.append(f"{context.rel_path}:{node.lineno}")
    return hits


def _detect_print_call(context: _RedLineFileContext) -> list[str]:
    """禁止生产代码 print 调试：统一使用 logger.debug / logger.info。"""
    hits: list[str] = []
    for node in ast.walk(context.tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
        ):
            hits.append(f"{context.rel_path}:{node.lineno}")
    return hits


def _detect_optional_union(context: _RedLineFileContext) -> list[str]:
    """禁止 Optional/Union 注解：改用 X | None 与 X | Y。"""
    hits: list[str] = []
    for node in ast.walk(context.tree):
        if not isinstance(node, ast.Subscript):
            continue
        target = node.value
        if isinstance(target, ast.Name) and target.id in {"Optional", "Union"}:
            hits.append(f"{context.rel_path}:{node.lineno}")
        elif isinstance(target, ast.Attribute) and target.attr in {"Optional", "Union"}:
            hits.append(f"{context.rel_path}:{node.lineno}")
    return hits


def _detect_api_repository_import(context: _RedLineFileContext) -> list[str]:
    """api 层禁止绕过 service 层直接访问 repository 层。"""
    hits: list[str] = []
    for node in ast.walk(context.tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("app.repository"):
                hits.append(f"{context.rel_path}:{node.lineno}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("app.repository"):
                    hits.append(f"{context.rel_path}:{node.lineno}")
    return hits


def _detect_service_aiosqlite_import(context: _RedLineFileContext) -> list[str]:
    """service 层禁止直连 aiosqlite：数据库访问必须统一经过 repository 层。"""
    hits: list[str] = []
    for node in ast.walk(context.tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] == "aiosqlite":
                hits.append(f"{context.rel_path}:{node.lineno}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "aiosqlite":
                    hits.append(f"{context.rel_path}:{node.lineno}")
    return hits


def _detect_models_reverse_import(context: _RedLineFileContext) -> list[str]:
    """models 层禁止反向引用 api / service / repository 上层模块。"""
    hits: list[str] = []
    for node in ast.walk(context.tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith(("app.api", "app.service", "app.repository")):
                hits.append(f"{context.rel_path}:{node.lineno}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(("app.api", "app.service", "app.repository")):
                    hits.append(f"{context.rel_path}:{node.lineno}")
    return hits


def _detect_root_api_router(context: _RedLineFileContext) -> list[str]:
    """根 API 兼容文件只做转发，不得承载真实 Router 实现。"""
    hits: list[str] = []
    for node in ast.walk(context.tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] == "fastapi":
                hits.append(f"{context.rel_path}:{node.lineno}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "fastapi":
                    hits.append(f"{context.rel_path}:{node.lineno}")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "APIRouter":
                hits.append(f"{context.rel_path}:{node.lineno}")
            elif isinstance(func, ast.Attribute) and func.attr == "APIRouter":
                hits.append(f"{context.rel_path}:{node.lineno}")
        elif (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "router"
        ):
            hits.append(f"{context.rel_path}:{node.lineno}")
    return hits


MINIMAL_RED_LINE_RULES: tuple[MinimalRedLineRule, ...] = (
    MinimalRedLineRule("禁止 SELECT 星号", "app", _detect_select_star),
    MinimalRedLineRule(
        "禁止 api 层直接导入 repository",
        "api",
        _detect_api_repository_import,
    ),
    MinimalRedLineRule(
        "禁止 service 层直连 aiosqlite",
        "service",
        _detect_service_aiosqlite_import,
    ),
    MinimalRedLineRule(
        "禁止 models 层反向引用上层模块",
        "models",
        _detect_models_reverse_import,
    ),
    MinimalRedLineRule("禁止 SQL f-string 拼接", "app", _detect_sql_fstring),
    MinimalRedLineRule("禁止静默吞异常", "app", _detect_silent_except),
    MinimalRedLineRule("禁止生产代码 print 调试", "app", _detect_print_call),
    MinimalRedLineRule("禁止 Optional/Union 注解", "app", _detect_optional_union),
    MinimalRedLineRule(
        "根 API 兼容文件不得承载真实 Router",
        "root_api_compat",
        _detect_root_api_router,
    ),
)

INLINE_RED_LINE_ACTION = (
    "按预检 detail 中的规则名与文件行修复商用红线："
    "SQL 必须显式列出字段并使用 ? 参数化绑定；"
    "api 层必须经 service 层、service 层必须经 repository 层、"
    "models 层不得反向引用上层模块；"
    "异常必须记录 logger.error 而不是静默 pass；"
    "生产代码不得使用 print()；"
    "类型注解使用 X | None 与 X | Y；"
    "根 API 兼容文件只做转发不得承载真实 Router。"
    "修复后重新运行 python scripts/preflight_production.py；"
    "如需恢复更完整的业务合约覆盖，请恢复仓库既有的专门合约检查入口，"
    "不要为此新建元治理脚本。"
)


def _run_minimal_red_line_checks(app_dir: Path) -> list[MinimalRedLineCheck]:
    """内联执行最小商用安全红线静态检查，命中任一规则即失败。

    每个文件只解析一次 AST，再逐条规则判定，避免重复解析拖慢生产预检。
    """
    hits_by_rule: dict[str, list[str]] = {
        rule.name: [] for rule in MINIMAL_RED_LINE_RULES
    }
    file_paths = _iter_app_python_files(app_dir)
    if not file_paths:
        # 扫描范围缺失时必须判失败，避免“扫不到文件 => 全部通过”的假绿。
        missing_hit = f"{app_dir.as_posix()}:0:未找到可检查的 Python 文件"
        return [
            MinimalRedLineCheck(
                name=rule.name,
                passed=False,
                hits=(missing_hit,),
            )
            for rule in MINIMAL_RED_LINE_RULES
        ]
    for file_path in file_paths:
        rel_path = _relative_app_path(file_path, app_dir)
        applicable_rules = [
            rule
            for rule in MINIMAL_RED_LINE_RULES
            if _scope_matches(rule.scope, rel_path)
        ]
        if not applicable_rules:
            continue
        source = file_path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError:
            # 无法解析说明文件本身已损坏，按 fail-closed 处理。
            for rule in applicable_rules:
                hits_by_rule[rule.name].append(
                    f"{rel_path}:1:语法错误，无法执行红线检查"
                )
            continue
        context = _RedLineFileContext(rel_path=rel_path, source=source, tree=tree)
        for rule in applicable_rules:
            hits_by_rule[rule.name].extend(rule.detector(context))
    return [
        MinimalRedLineCheck(
            name=rule.name,
            passed=not hits_by_rule[rule.name],
            hits=tuple(hits_by_rule[rule.name]),
        )
        for rule in MINIMAL_RED_LINE_RULES
    ]


def _business_contract_mode() -> str:
    """返回业务合约静态检查的运行模式。"""
    if check_project is not None and hasattr(check_project, "run_contract_checks"):
        return CHECK_PROJECT_MODE
    return INLINE_RED_LINE_MODE


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
    """构建业务合约静态检查结果；门禁脚本缺失时回退到内联最小红线，仍然 fail-closed。"""
    if _business_contract_mode() == CHECK_PROJECT_MODE:
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

    inline_results = _run_minimal_red_line_checks(APP_DIR)
    failed_rules = [rule for rule in inline_results if not rule.passed]
    violation_count = sum(rule.violation_count for rule in failed_rules)
    detail_parts = [
        f"mode={INLINE_RED_LINE_MODE}",
        f"violations={violation_count}",
        "checks="
        + ", ".join(
            f"{rule.name}:{'passed' if rule.passed else 'failed'}"
            for rule in inline_results
        ),
    ]
    if failed_rules:
        hit_texts = [
            hit
            for rule in failed_rules
            for hit in rule.hits[:MINIMAL_RED_LINE_HIT_LIMIT]
        ]
        truncated = violation_count > len(hit_texts)
        detail_parts.append("hits=" + "; ".join(hit_texts))
        if truncated:
            detail_parts.append(f"hits_truncated={violation_count - len(hit_texts)}")
    return PreflightCheck(
        key="business_contracts.static_checks",
        title="业务合约静态检查",
        passed=not failed_rules,
        detail=" ".join(detail_parts),
        action="" if not failed_rules else INLINE_RED_LINE_ACTION,
    )


def _format_business_contract_results(
    contract_results: list[Any],
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


def build_edge_backend_availability_check() -> PreflightCheck:
    """共享防护后端存活探测：配置共享才探测，不可用直接失败。"""
    from app.service.edge_protection import is_edge_protection_shared, ping_edge_backend

    if not is_edge_protection_shared():
        return PreflightCheck(
            key="edge_protection_backend_available",
            title="共享防护后端可用性",
            passed=True,
            detail="local_mode",
            action="",
        )
    import asyncio as asyncio_lib

    available = asyncio_lib.run(ping_edge_backend(timeout_seconds=2.0))
    return PreflightCheck(
        key="edge_protection_backend_available",
        title="共享防护后端可用性",
        passed=available,
        detail="ready" if available else "unreachable",
        action=""
        if available
        else "检查 EDGE_REDIS_URL 指向的 Redis 是否可达；不可达时生产不得上线。",
    )


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
        build_edge_backend_availability_check(),
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
        if _business_contract_mode() == CHECK_PROJECT_MODE:
            business_command = "python scripts/check_project.py --skip-tests"
            business_reason = (
                "客户 RAG、知识治理、长期记忆治理、客户机器人可观测、"
                "MiniApp 页面 API 覆盖或员工助手能力合约静态检查失败，"
                "发布会绕过已冻结边界。"
            )
            business_apply = (
                "修复失败合约对应的 fixture、治理计划或能力合约后，"
                "重新运行统一质量门禁。"
            )
        else:
            business_command = "python scripts/preflight_production.py"
            business_reason = (
                "最小商用安全红线静态检查失败：SQL 写法、分层依赖、异常处理、"
                "调试输出、类型注解或根 API 兼容入口存在越线，"
                "发布会绕过已冻结的商用边界。"
            )
            business_apply = (
                "按预检 detail 中的规则名与文件行修复商用红线后，"
                "重新运行 python scripts/preflight_production.py。"
            )
        steps.append(
            PreflightPlanStep(
                order=len(steps) + 1,
                key="business_contracts",
                severity="critical",
                title="修复业务合约门禁",
                reason=business_reason,
                command=business_command,
                apply_command=business_apply,
                verify_command=verify_command,
                related_keys=business_contract_keys,
                apply_mutates_state=False,
            )
        )

    edge_backend_keys = _matching_failed_keys(
        failed_keys, frozenset({"edge_protection_backend_available"})
    )
    if edge_backend_keys:
        steps.append(
            PreflightPlanStep(
                order=len(steps) + 1,
                key="edge_backend",
                severity="critical",
                title="恢复共享防护后端",
                reason="共享限流与登录防护后端不可达，生产流量将无统一防护。",
                command="检查 EDGE_REDIS_URL 指向的 Redis 服务状态与网络可达性。",
                apply_command="恢复 Redis 服务后重新预检；未恢复前不得上线。",
                verify_command=verify_command,
                related_keys=edge_backend_keys,
                apply_mutates_state=True,
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
    parser = argparse.ArgumentParser(
        description="生产同步前只读预检报告",
        epilog="存在阻断项时停止执行，由人工接手处理。",
    )
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
