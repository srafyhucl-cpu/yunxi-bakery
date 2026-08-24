"""上线前只读冒烟检查。"""

import argparse
import asyncio
import json
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import APP_VERSION, settings  # noqa: E402
from app.database import resolve_database_path  # noqa: E402
from app.readiness import (  # noqa: E402
    REQUIRED_DATABASE_TABLES,
    build_channel_readiness_checks,
    embedding_index_files_exist,
    resolve_embedding_path,
)
from scripts.preflight_production import is_readable_sqlite_database  # noqa: E402

HTTP_OK = 200
REQUEST_TIMEOUT_SECONDS = 5
SERVICE_REACHABILITY_TIMEOUT_SECONDS = 2
MIN_KNOWLEDGE_ROWS = 1
UTF8_BOM = b"\xef\xbb\xbf"
OUTPUT_TIMESTAMP_PLACEHOLDER = "{timestamp}"
OUTPUT_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"
HEALTH_STATUS_OK = "ok"
READY_STATUS_OK = "ready"
HEALTH_PATH = "/health"
READY_PATH = "/ready"
OBSERVABILITY_SUMMARY_PATH = "/api/v1/admin/observability/summary"
DEFAULT_ADMIN_TOKEN = "CHANGE_ME_IN_PRODUCTION_ENV"
ADMIN_DIST_DIR = ROOT_DIR / "web" / "admin" / "dist"
ADMIN_DIST_SUMMARY_MARKERS = (
    "/observability/summary",
    "上线值守",
    "慢 Webhook",
)
SERVICE_REACHABILITY_NAME = "服务端口可达性"
SERVICE_UNREACHABLE_DETAIL = (
    "服务不可达，已跳过 HTTP 接口检查；请先启动服务或核对 SERVER_HOST/SERVER_PORT"
)
HTTP_ENDPOINT_CHECK_NAMES = (
    "健康检查接口",
    "就绪检查接口",
    "观察台值守摘要接口",
)
HTTP_ONLY_ENDPOINT_CHECK_NAMES = (
    "健康检查接口",
    "就绪检查接口",
)
DATABASE_SCHEMA_CHECK_NAME = "数据库表结构"
KNOWLEDGE_ROWS_CHECK_NAME = "知识库数据"
EMBEDDING_FILE_CHECK_NAME = "向量索引文件"
REQUIRED_SETTINGS_CHECK_NAME = "关键环境变量"
CHANNEL_READINESS_CHECK_NAME = "生产通道配置"
ADMIN_DIST_SUMMARY_CHECK_NAME = "后台值守摘要产物"


CHANNEL_READINESS_SETTING_NAMES = {
    "youzan_client_id_configured": "YOUZAN_CLIENT_ID",
    "youzan_client_secret_configured": "YOUZAN_CLIENT_SECRET",
    "youzan_kdt_id_configured": "YOUZAN_KDT_ID",
    "youzan_production_mode_ready": "YOUZAN_MOCK_MODE_FALSE_AND_YOUZAN_CREDENTIALS",
    "wecom_corp_id_configured": "WECOM_CORP_ID",
    "wecom_agent_id_configured": "WECOM_AGENT_ID",
    "wecom_secret_configured": "WECOM_SECRET",
    "wecom_callback_token_configured": "WECOM_TOKEN",
    "wecom_encoding_aes_key_configured": "WECOM_ENCODING_AES_KEY",
    "wecom_kf_id_configured": "WECOM_KF_ID",
    "wecom_bot_plugin_api_key_configured": "WECOM_BOT_PLUGIN_API_KEY",
    "wecom_intelligent_bot_callback_token_configured": (
        "WECOM_INTELLIGENT_BOT_TOKEN_OR_WECOM_TOKEN"
    ),
    "wecom_intelligent_bot_encoding_aes_key_configured": (
        "WECOM_INTELLIGENT_BOT_ENCODING_AES_KEY_OR_WECOM_ENCODING_AES_KEY"
    ),
    "handoff_staff_userid_ready": "WECOM_STAFF_ID_OR_WECOM_KF_SERVICER_USERID",
}


@dataclass(frozen=True)
class SmokeResult:
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class SmokeRecoveryHint:
    key: str
    severity: str
    title: str
    reason: str
    action: str
    related_names: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "severity": self.severity,
            "title": self.title,
            "reason": self.reason,
            "action": self.action,
            "related_names": list(self.related_names),
        }


@dataclass(frozen=True)
class SmokeTarget:
    scheme: str
    host: str
    port: int

    @property
    def base_url(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"

    def url_for(self, path: str = "") -> str:
        return self.base_url + path


@dataclass(frozen=True)
class SmokeRuntimePaths:
    database_path: Path
    index_path: Path


SMOKE_TARGET_OVERRIDE: SmokeTarget | None = None
SMOKE_RUNTIME_PATHS_OVERRIDE: SmokeRuntimePaths | None = None


def get_smoke_target() -> SmokeTarget:
    if SMOKE_TARGET_OVERRIDE is not None:
        return SMOKE_TARGET_OVERRIDE
    return SmokeTarget("http", settings.SERVER_HOST, settings.SERVER_PORT)


def parse_base_url(base_url: str) -> SmokeTarget:
    parsed_url = urlparse(base_url)
    if parsed_url.scheme not in {"http", "https"}:
        raise ValueError("--base-url 仅支持 http 或 https。")
    if not parsed_url.hostname:
        raise ValueError("--base-url 必须包含主机名。")
    if parsed_url.path not in {"", "/"} or parsed_url.params or parsed_url.query:
        raise ValueError("--base-url 只接受根地址，不要包含路径、参数或查询串。")
    default_port = 443 if parsed_url.scheme == "https" else 80
    return SmokeTarget(
        scheme=parsed_url.scheme,
        host=parsed_url.hostname,
        port=parsed_url.port or default_port,
    )


def set_smoke_target_override(base_url: str | None) -> None:
    global SMOKE_TARGET_OVERRIDE
    SMOKE_TARGET_OVERRIDE = parse_base_url(base_url) if base_url else None


def resolve_project_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else ROOT_DIR / path


def get_smoke_runtime_paths() -> SmokeRuntimePaths:
    if SMOKE_RUNTIME_PATHS_OVERRIDE is not None:
        return SMOKE_RUNTIME_PATHS_OVERRIDE
    return SmokeRuntimePaths(
        database_path=Path(resolve_database_path()),
        index_path=resolve_embedding_path(settings.EMBEDDING_INDEX_DIR),
    )


def set_smoke_runtime_paths_override(
    db_path_value: str | None,
    index_path_value: str | None,
) -> None:
    global SMOKE_RUNTIME_PATHS_OVERRIDE
    if db_path_value is None and index_path_value is None:
        SMOKE_RUNTIME_PATHS_OVERRIDE = None
        return
    current_paths = get_smoke_runtime_paths()
    SMOKE_RUNTIME_PATHS_OVERRIDE = SmokeRuntimePaths(
        database_path=(
            resolve_project_path(db_path_value)
            if db_path_value is not None
            else current_paths.database_path
        ),
        index_path=(
            resolve_project_path(index_path_value)
            if index_path_value is not None
            else current_paths.index_path
        ),
    )


def check_env_file() -> SmokeResult:
    env_path = ROOT_DIR / ".env"
    return SmokeResult(".env 文件存在", env_path.exists(), str(env_path))


def check_database_file() -> SmokeResult:
    db_path = get_smoke_runtime_paths().database_path
    return SmokeResult("数据库文件存在", db_path.exists(), str(db_path))


def get_existing_tables(conn: sqlite3.Connection) -> set[str]:
    placeholders = ", ".join("?" for _ in REQUIRED_DATABASE_TABLES)
    query = (
        "SELECT name FROM sqlite_master WHERE type = ? "
        + "AND name IN ("
        + placeholders
        + ") ORDER BY name ASC"
    )
    cursor = conn.execute(
        query,
        ("table", *REQUIRED_DATABASE_TABLES),
    )
    return {row[0] for row in cursor.fetchall()}


def check_schema() -> SmokeResult:
    db_path = get_smoke_runtime_paths().database_path
    if not db_path.exists():
        return SmokeResult(DATABASE_SCHEMA_CHECK_NAME, False, "数据库文件不存在")
    if not is_readable_sqlite_database(db_path):
        return SmokeResult(
            DATABASE_SCHEMA_CHECK_NAME,
            False,
            "database_not_readable; verify DB_PATH or restore database file",
        )
    with closing(sqlite3.connect(db_path)) as conn:
        existing_tables = get_existing_tables(conn)
    missing_tables = sorted(set(REQUIRED_DATABASE_TABLES) - existing_tables)
    detail = (
        "缺失表: " + ", ".join(missing_tables) if missing_tables else "关键表已存在"
    )
    return SmokeResult(DATABASE_SCHEMA_CHECK_NAME, not missing_tables, detail)


def check_knowledge_rows() -> SmokeResult:
    db_path = get_smoke_runtime_paths().database_path
    if not db_path.exists():
        return SmokeResult(KNOWLEDGE_ROWS_CHECK_NAME, False, "数据库文件不存在")
    if not is_readable_sqlite_database(db_path):
        return SmokeResult(
            KNOWLEDGE_ROWS_CHECK_NAME,
            False,
            "database_not_readable; verify DB_PATH or restore database file",
        )
    try:
        with closing(sqlite3.connect(db_path)) as conn:
            cursor = conn.execute(
                "SELECT COUNT(id) FROM knowledge_base WHERE is_active = ?", (1,)
            )
            row_count = int(cursor.fetchone()[0])
    except sqlite3.Error as exc:
        return SmokeResult(KNOWLEDGE_ROWS_CHECK_NAME, False, f"查询失败: {exc}")
    is_enough = row_count >= MIN_KNOWLEDGE_ROWS
    return SmokeResult(KNOWLEDGE_ROWS_CHECK_NAME, is_enough, f"active rows={row_count}")


def check_embedding_file() -> SmokeResult:
    embedding_path = get_smoke_runtime_paths().index_path
    expected_paths = (
        embedding_path.with_suffix(".npy"),
        embedding_path.with_suffix(".json"),
    )
    missing_paths = [str(path) for path in expected_paths if not path.exists()]
    if missing_paths:
        return SmokeResult(
            EMBEDDING_FILE_CHECK_NAME,
            False,
            "missing=" + ", ".join(missing_paths),
        )
    if not embedding_index_files_exist(embedding_path):
        return SmokeResult(
            EMBEDDING_FILE_CHECK_NAME,
            False,
            "invalid_cache=" + ", ".join(str(path) for path in expected_paths),
        )
    expected_files = (
        str(embedding_path.with_suffix(".npy")),
        str(embedding_path.with_suffix(".json")),
    )
    return SmokeResult(
        EMBEDDING_FILE_CHECK_NAME,
        True,
        "ready=" + ", ".join(expected_files),
    )


def check_required_settings() -> SmokeResult:
    missing_names: list[str] = []
    if not settings.ADMIN_API_TOKEN or settings.ADMIN_API_TOKEN == DEFAULT_ADMIN_TOKEN:
        missing_names.append("ADMIN_API_TOKEN")
    if not settings.MIMO_API_KEY:
        missing_names.append("MIMO_API_KEY")
    detail = "缺失: " + ", ".join(missing_names) if missing_names else "关键配置已设置"
    return SmokeResult(REQUIRED_SETTINGS_CHECK_NAME, not missing_names, detail)


def check_runtime_feature_flags() -> SmokeResult:
    flags = {
        "reply_guard": settings.ENABLE_REPLY_GUARD,
        "customer_memory": settings.ENABLE_CUSTOMER_MEMORY,
        "offline_review": settings.ENABLE_OFFLINE_REVIEW,
        "hybrid_retrieval": settings.ENABLE_HYBRID_RETRIEVAL,
        "youzan_mock_mode": settings.YOUZAN_MOCK_MODE,
    }
    enabled_names = [name for name, enabled in flags.items() if enabled]
    detail = "enabled=" + (", ".join(enabled_names) if enabled_names else "none")
    return SmokeResult("运行特性开关（只显示）", True, detail)


def check_channel_readiness() -> SmokeResult:
    checks = build_channel_readiness_checks()
    missing_names = [
        CHANNEL_READINESS_SETTING_NAMES[check_name]
        for check_name, is_ready in checks.items()
        if not is_ready
    ]
    detail = (
        "missing=" + ", ".join(missing_names) if missing_names else ("channels-ready")
    )
    return SmokeResult(CHANNEL_READINESS_CHECK_NAME, not missing_names, detail)


def check_admin_dist_observability_summary() -> SmokeResult:
    assets_dir = ADMIN_DIST_DIR / "assets"
    if not assets_dir.exists():
        return SmokeResult(
            ADMIN_DIST_SUMMARY_CHECK_NAME, False, f"目录不存在: {assets_dir}"
        )
    text_parts: list[str] = []
    for asset_path in assets_dir.glob("*"):
        if asset_path.suffix not in {".js", ".css"}:
            continue
        text_parts.append(asset_path.read_text(encoding="utf-8", errors="ignore"))
    bundle_text = "\n".join(text_parts)
    matched_markers = [
        marker for marker in ADMIN_DIST_SUMMARY_MARKERS if marker in bundle_text
    ]
    is_built = bool(matched_markers)
    detail = (
        "包含标记: " + ", ".join(matched_markers)
        if is_built
        else "dist 未包含观察台值守摘要，请重新构建 web/admin"
    )
    return SmokeResult(ADMIN_DIST_SUMMARY_CHECK_NAME, is_built, detail)


async def check_health_endpoint() -> SmokeResult:
    url = _build_server_url(HEALTH_PATH)
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        return SmokeResult("健康检查接口", False, _format_http_error(exc))
    if response.status_code != HTTP_OK:
        return SmokeResult("健康检查接口", False, f"status={response.status_code}")
    payload = response.json()
    is_ok = payload.get("status") == HEALTH_STATUS_OK
    return SmokeResult("健康检查接口", is_ok, str(payload))


def build_readiness_detail(payload: dict[str, object]) -> str:
    checks = payload.get("checks")
    if not isinstance(checks, dict):
        return str(payload)
    failed_names = [name for name, passed in checks.items() if passed is not True]
    if not failed_names:
        return str(payload)
    return "failed_checks=" + ", ".join(failed_names)


def build_observability_summary_detail(payload: dict[str, object]) -> str:
    data = payload.get("data")
    if not isinstance(data, dict):
        return str(payload)
    status = data.get("status", "unknown")
    counts = data.get("counts")
    return (
        f"status={status}, counts={counts}" if isinstance(counts, dict) else str(data)
    )


async def check_ready_endpoint() -> SmokeResult:
    url = _build_server_url(READY_PATH)
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        return SmokeResult("就绪检查接口", False, _format_http_error(exc))
    if response.status_code != HTTP_OK:
        return SmokeResult("就绪检查接口", False, f"status={response.status_code}")
    payload = response.json()
    is_ready = payload.get("status") == READY_STATUS_OK
    return SmokeResult("就绪检查接口", is_ready, build_readiness_detail(payload))


async def check_observability_summary_endpoint() -> SmokeResult:
    url = _build_server_url(OBSERVABILITY_SUMMARY_PATH)
    headers = {"Authorization": f"Bearer {settings.ADMIN_API_TOKEN}"}
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        return SmokeResult("观察台值守摘要接口", False, _format_http_error(exc))
    if response.status_code != HTTP_OK:
        return SmokeResult(
            "观察台值守摘要接口", False, f"status={response.status_code}"
        )
    payload = response.json()
    data = payload.get("data")
    has_summary_shape = (
        payload.get("code") == 0
        and isinstance(data, dict)
        and isinstance(data.get("status"), str)
        and isinstance(data.get("counts"), dict)
    )
    return SmokeResult(
        "观察台值守摘要接口",
        has_summary_shape,
        build_observability_summary_detail(payload),
    )


def run_static_checks() -> list[SmokeResult]:
    return [
        check_env_file(),
        check_database_file(),
        check_schema(),
        check_knowledge_rows(),
        check_embedding_file(),
        check_required_settings(),
        check_runtime_feature_flags(),
        check_channel_readiness(),
        check_admin_dist_observability_summary(),
    ]


def _build_server_url(path: str = "") -> str:
    return get_smoke_target().url_for(path)


async def check_service_reachability() -> SmokeResult:
    target = get_smoke_target()
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(target.host, target.port),
            timeout=SERVICE_REACHABILITY_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        return SmokeResult(
            SERVICE_REACHABILITY_NAME,
            False,
            f"{_build_server_url()}; timeout={SERVICE_REACHABILITY_TIMEOUT_SECONDS}s",
        )
    except OSError as exc:
        return SmokeResult(
            SERVICE_REACHABILITY_NAME,
            False,
            f"{_build_server_url()}; {_format_service_reachability_error(exc)}",
        )
    writer.close()
    await writer.wait_closed()
    return SmokeResult(SERVICE_REACHABILITY_NAME, True, _build_server_url())


def build_skipped_http_results(reachability_result: SmokeResult) -> list[SmokeResult]:
    detail = f"{SERVICE_UNREACHABLE_DETAIL}: {reachability_result.detail}"
    return [
        SmokeResult(check_name, False, detail)
        for check_name in HTTP_ENDPOINT_CHECK_NAMES
    ]


def build_skipped_http_only_results(
    reachability_result: SmokeResult,
) -> list[SmokeResult]:
    detail = f"{SERVICE_UNREACHABLE_DETAIL}: {reachability_result.detail}"
    return [
        SmokeResult(check_name, False, detail)
        for check_name in HTTP_ONLY_ENDPOINT_CHECK_NAMES
    ]


def _format_http_error(exc: httpx.HTTPError) -> str:
    detail = str(exc) or exc.__class__.__name__
    return f"请求失败: {detail}"


def _format_service_reachability_error(exc: OSError) -> str:
    detail = str(exc) or exc.__class__.__name__
    return f"connect_failed={detail}"


def print_results(results: list[SmokeResult]) -> None:
    metadata = build_report_metadata()
    recovery_hints = build_recovery_hints(results)
    print("Bakery Commerce Platform production smoke")
    print(f"generated_at={metadata['generated_at']}")
    print(f"project_root={metadata['project_root']}")
    print(f"db_path={metadata['database_path']}")
    print(f"index_path={metadata['index_path']}")
    print(f"server_base_url={metadata['server_base_url']}")
    print(f"app_version={metadata['app_version']}")
    print(f"total={len(results)} failed={sum(not result.passed for result in results)}")
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"{status} {result.name}: {result.detail}")
    if recovery_hints:
        print("recovery_hints:")
        for index, hint in enumerate(recovery_hints, start=1):
            related_names = ", ".join(hint.related_names)
            print(
                f"  {index}. [{hint.severity}] {hint.key} - {hint.title}: {hint.reason}"
            )
            print(f"     action: {hint.action}")
            print(f"     related: {related_names}")


def build_report_metadata() -> dict[str, str]:
    generated_at = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    return {
        "generated_at": generated_at,
        "project_root": str(ROOT_DIR),
        "database_path": str(get_smoke_runtime_paths().database_path),
        "index_path": str(get_smoke_runtime_paths().index_path),
        "server_base_url": _build_server_url(),
        "app_version": APP_VERSION,
    }


def build_json_report(results: list[SmokeResult]) -> dict[str, object]:
    failed_results = [result for result in results if not result.passed]
    return {
        "status": "passed" if not failed_results else "failed",
        "metadata": build_report_metadata(),
        "total": len(results),
        "failed": len(failed_results),
        "results": [result.to_dict() for result in results],
        "failed_names": [result.name for result in failed_results],
        "recovery_hints": [
            recovery_hint.to_dict() for recovery_hint in build_recovery_hints(results)
        ],
    }


def _failed_result_names(results: list[SmokeResult]) -> set[str]:
    return {result.name for result in results if not result.passed}


def _related_failed_names(
    failed_names: set[str],
    expected_names: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(name for name in expected_names if name in failed_names)


def build_recovery_hints(results: list[SmokeResult]) -> list[SmokeRecoveryHint]:
    failed_names = _failed_result_names(results)
    hints: list[SmokeRecoveryHint] = []

    database_related_names = _related_failed_names(
        failed_names,
        (DATABASE_SCHEMA_CHECK_NAME, KNOWLEDGE_ROWS_CHECK_NAME),
    )
    if database_related_names:
        hints.append(
            SmokeRecoveryHint(
                key="database_knowledge",
                severity="critical",
                title="补齐数据库和知识数据",
                reason="数据库结构或有效知识不足会让智能客服无法稳定回答，也会影响转人工、画像和企微同步。",
                action=(
                    "先运行 scripts/preflight_production.py 查看 recovery_plan；"
                    "按计划 dry-run 后再确认是否执行迁移、知识导入和向量重建。"
                ),
                related_names=database_related_names,
            )
        )

    embedding_related_names = _related_failed_names(
        failed_names,
        (EMBEDDING_FILE_CHECK_NAME,),
    )
    if embedding_related_names:
        hints.append(
            SmokeRecoveryHint(
                key="embedding_cache",
                severity="critical",
                title="补齐向量缓存",
                reason="向量缓存缺失或损坏会让 RAG 检索增强不可用，回答质量会明显退化。",
                action=(
                    "确认知识库已有有效数据后运行 scripts/rebuild_embeddings.py dry-run；"
                    "目标路径无误且 active_docs>0 时再显式加 --apply。"
                ),
                related_names=embedding_related_names,
            )
        )

    config_related_names = _related_failed_names(
        failed_names,
        (REQUIRED_SETTINGS_CHECK_NAME, CHANNEL_READINESS_CHECK_NAME),
    )
    if config_related_names:
        hints.append(
            SmokeRecoveryHint(
                key="production_config",
                severity="critical",
                title="补齐生产配置",
                reason="关键密钥、生产通道或人工接手人缺失会阻断真实客户消息处理。",
                action=(
                    "核对生产 .env 或部署平台环境变量；"
                    "补齐后重启服务，再重新运行 preflight 和 smoke。"
                ),
                related_names=config_related_names,
            )
        )

    frontend_related_names = _related_failed_names(
        failed_names,
        (ADMIN_DIST_SUMMARY_CHECK_NAME,),
    )
    if frontend_related_names:
        hints.append(
            SmokeRecoveryHint(
                key="admin_dist",
                severity="warning",
                title="重新构建后台产物",
                reason="后台 dist 缺失或过旧会让管理台无法看到最新值守摘要。",
                action="在 web/admin 执行 npm run build:production，或同步最新 dist 到生产环境。",
                related_names=frontend_related_names,
            )
        )

    service_related_names = _related_failed_names(
        failed_names,
        (SERVICE_REACHABILITY_NAME, *HTTP_ENDPOINT_CHECK_NAMES),
    )
    if service_related_names:
        hints.append(
            SmokeRecoveryHint(
                key="service_unreachable",
                severity="critical",
                title="启动并核对服务地址",
                reason="服务端口不可达时，HTTP 接口检查会被跳过；这是同一个根因，不是多条独立故障。",
                action=(
                    "先确认 FastAPI 服务已启动，并核对 --base-url、SERVER_HOST、SERVER_PORT；"
                    "服务可达后再复跑 smoke。"
                ),
                related_names=service_related_names,
            )
        )

    return hints


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bakery Commerce Platform production smoke test"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出机器可读 JSON，便于上线后留档或部署脚本解析。",
    )
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "配合 --json 使用，将报告写入指定文件；目标文件已存在时会拒绝覆盖；"
            "支持 {timestamp} 自动展开为 YYYYMMDD-HHMMSS。"
        ),
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help=(
            "临时覆盖本次冒烟目标服务根地址，例如 http://127.0.0.1:7001 "
            "或 https://bot.example.com；不会改写 .env。"
        ),
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="临时覆盖本次冒烟使用的数据库文件路径；不会改写 .env，也不会执行迁移。",
    )
    parser.add_argument(
        "--index-path",
        default=None,
        help="临时覆盖本次冒烟使用的向量索引基路径；会检查 .npy/.json 配对文件。",
    )
    parser.add_argument(
        "--http-only",
        action="store_true",
        help="只检查服务可达性、/health 和 /ready，不读取本地数据库或环境配置。",
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


async def run_smoke_checks() -> list[SmokeResult]:
    results = run_static_checks()
    reachability_result = await check_service_reachability()
    results.append(reachability_result)
    if not reachability_result.passed:
        results.extend(build_skipped_http_results(reachability_result))
        return results
    results.append(await check_health_endpoint())
    results.append(await check_ready_endpoint())
    results.append(await check_observability_summary_endpoint())
    return results


async def run_http_only_smoke_checks() -> list[SmokeResult]:
    reachability_result = await check_service_reachability()
    results = [reachability_result]
    if not reachability_result.passed:
        results.extend(build_skipped_http_only_results(reachability_result))
        return results
    results.append(await check_health_endpoint())
    results.append(await check_ready_endpoint())
    return results


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        set_smoke_target_override(args.base_url)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    set_smoke_runtime_paths_override(args.db_path, args.index_path)
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
    results = (
        await run_http_only_smoke_checks()
        if args.http_only
        else await run_smoke_checks()
    )
    if args.json:
        json_bytes = (
            json.dumps(build_json_report(results), ensure_ascii=False, indent=2) + "\n"
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
        print_results(results)
    return 1 if any(not result.passed for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
