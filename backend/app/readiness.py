"""生产就绪检查工具。"""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from app.config import settings
from app.database import resolve_database_path

DEFAULT_ADMIN_TOKEN = "CHANGE_ME_IN_PRODUCTION_ENV"
ROOT_DIR = Path(__file__).resolve().parent.parent
ADMIN_DIST_DIR = ROOT_DIR / "web" / "admin" / "dist"
ADMIN_DIST_ASSET_SUFFIXES = frozenset({".js", ".css"})
ADMIN_DIST_SUMMARY_MARKERS = (
    "/observability/summary",
    "上线值守",
    "慢 Webhook",
)


REQUIRED_DATABASE_TABLES = (
    "sessions",
    "messages",
    "knowledge_base",
    "knowledge_retrieval_logs",
    "human_transfers",
    "orders",
    "shop_config",
    "youzan_products",
    "youzan_orders",
    "youzan_webhook_events",
    "content_change_history",
    "customer_master",
    "customer_identity_links",
    "customer_source_snapshots",
    "customer_merge_reviews",
    "customer_profiles",
    "conversation_summaries",
    "customer_groups",
    "group_campaigns",
    "group_registrations",
    "conversation_reviews",
    "knowledge_gaps",
    "wecom_kf_sync_states",
    "wecom_kf_message_ledger",
    "payment_transactions",
    "order_events",
    "miniapp_addresses",
    "miniapp_address_audit",
    "inbox_events",
    "customer_consent_ledger",
    "member_balance",
    "points_ledger",
    "coupon_inventory",
    "stored_value_recharge",
    "balance_ledger",
)
REQUIRED_DATABASE_COLUMNS = {
    "knowledge_base": (
        "audience",
        "review_status",
        "valid_from",
        "valid_until",
        "reviewed_by",
        "reviewed_at",
    ),
}


def build_readiness_checks() -> dict[str, bool]:
    database_path = Path(resolve_database_path())
    embedding_index_path = resolve_runtime_path(settings.EMBEDDING_INDEX_DIR)
    checks = {
        "admin_token_configured": _is_configured_secret(settings.ADMIN_API_TOKEN)
        and settings.ADMIN_API_TOKEN != DEFAULT_ADMIN_TOKEN
        and _is_configured_secret(settings.ADMIN_SESSION_SECRET),
        "mimo_api_key_configured": _is_configured_secret(settings.MIMO_API_KEY),
        "database_path_exists": database_path.exists(),
        "database_schema_ready": _database_schema_ready(database_path),
        "embedding_index_path_exists": embedding_index_files_exist(
            embedding_index_path
        ),
    }
    checks.update(build_channel_readiness_checks())
    checks.update(build_admin_frontend_readiness_checks())
    return checks


def resolve_runtime_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else ROOT_DIR / path


def resolve_embedding_path(path_value: str | Path) -> Path:
    return resolve_runtime_path(path_value)


def embedding_index_files_exist(index_path: str | Path) -> bool:
    base_path = resolve_runtime_path(index_path)
    npy_path = base_path.with_suffix(".npy")
    json_path = base_path.with_suffix(".json")
    if not npy_path.exists() or not json_path.exists():
        return False
    try:
        import numpy as np

        np.load(npy_path, allow_pickle=False)
        with open(json_path, "r", encoding="utf-8") as file_obj:
            meta = json.load(file_obj)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(meta, dict):
        return False
    return isinstance(meta.get("doc_keys"), list) and isinstance(
        meta.get("ready"), bool
    )


def build_channel_readiness_checks() -> dict[str, bool]:
    return {
        "youzan_client_id_configured": _is_configured_secret(settings.YOUZAN_CLIENT_ID),
        "youzan_client_secret_configured": _is_configured_secret(
            settings.YOUZAN_CLIENT_SECRET
        ),
        "youzan_kdt_id_configured": _is_configured_secret(settings.YOUZAN_KDT_ID),
        "youzan_production_mode_ready": (
            not settings.YOUZAN_MOCK_MODE
            and _is_configured_secret(settings.YOUZAN_CLIENT_ID)
            and _is_configured_secret(settings.YOUZAN_CLIENT_SECRET)
            and _is_configured_secret(settings.YOUZAN_KDT_ID)
        ),
        "wecom_corp_id_configured": _is_configured_secret(settings.WECOM_CORP_ID),
        "wecom_agent_id_configured": _is_configured_secret(settings.WECOM_AGENT_ID),
        "wecom_secret_configured": _is_configured_secret(settings.WECOM_SECRET),
        "wecom_callback_token_configured": _is_configured_secret(settings.WECOM_TOKEN),
        "wecom_encoding_aes_key_configured": _is_configured_secret(
            settings.WECOM_ENCODING_AES_KEY
        ),
        "wecom_kf_id_configured": _is_configured_secret(settings.WECOM_KF_ID),
        "wecom_bot_plugin_api_key_configured": _is_configured_secret(
            settings.WECOM_BOT_PLUGIN_API_KEY
        ),
        "wecom_intelligent_bot_callback_token_configured": _is_configured_secret(
            settings.WECOM_INTELLIGENT_BOT_TOKEN
        )
        or _is_configured_secret(settings.WECOM_TOKEN),
        "wecom_intelligent_bot_encoding_aes_key_configured": _is_configured_secret(
            settings.WECOM_INTELLIGENT_BOT_ENCODING_AES_KEY
        )
        or _is_configured_secret(settings.WECOM_ENCODING_AES_KEY),
        "handoff_staff_userid_ready": _is_configured_secret(settings.WECOM_STAFF_ID)
        or _is_configured_secret(settings.WECOM_KF_SERVICER_USERID),
    }


def _database_schema_ready(database_path: Path) -> bool:
    if not database_path.exists():
        return False

    placeholders = ", ".join("?" for _ in REQUIRED_DATABASE_TABLES)
    query = (
        "SELECT name FROM sqlite_master WHERE type = ? "
        + "AND name IN ("
        + placeholders
        + ")"
    )
    try:
        with closing(sqlite3.connect(database_path)) as conn:
            cursor = conn.execute(
                query,
                ("table", *REQUIRED_DATABASE_TABLES),
            )
            existing_tables = {str(row[0]) for row in cursor.fetchall()}
            if not set(REQUIRED_DATABASE_TABLES).issubset(existing_tables):
                return False
            return not _get_missing_database_columns(conn)
    except sqlite3.Error:
        return False


def get_missing_database_columns(database_path: Path) -> list[str]:
    if not database_path.exists():
        return [
            f"{table_name}.{column_name}"
            for table_name, columns in REQUIRED_DATABASE_COLUMNS.items()
            for column_name in columns
        ]
    try:
        with closing(sqlite3.connect(database_path)) as conn:
            return _get_missing_database_columns(conn)
    except sqlite3.Error:
        return [
            f"{table_name}.{column_name}"
            for table_name, columns in REQUIRED_DATABASE_COLUMNS.items()
            for column_name in columns
        ]


def _get_missing_database_columns(conn: sqlite3.Connection) -> list[str]:
    missing_columns: list[str] = []
    for table_name, required_columns in REQUIRED_DATABASE_COLUMNS.items():
        cursor = conn.execute("PRAGMA table_info(" + table_name + ")")
        existing_columns = {str(row[1]) for row in cursor.fetchall()}
        missing_columns.extend(
            f"{table_name}.{column_name}"
            for column_name in required_columns
            if column_name not in existing_columns
        )
    return sorted(missing_columns)


def build_admin_frontend_readiness_checks() -> dict[str, bool]:
    assets_dir = ADMIN_DIST_DIR / "assets"
    return {
        "admin_frontend_index_exists": (ADMIN_DIST_DIR / "index.html").exists(),
        "admin_frontend_assets_exist": assets_dir.exists(),
        "admin_frontend_observability_summary_built": (
            _admin_frontend_observability_summary_built(assets_dir)
        ),
    }


def _admin_frontend_observability_summary_built(assets_dir: Path) -> bool:
    if not assets_dir.exists():
        return False

    for asset_path in assets_dir.glob("*"):
        if asset_path.suffix not in ADMIN_DIST_ASSET_SUFFIXES:
            continue
        asset_text = asset_path.read_text(encoding="utf-8", errors="ignore")
        if any(marker in asset_text for marker in ADMIN_DIST_SUMMARY_MARKERS):
            return True
    return False


def build_runtime_feature_flags(
    offline_review_running: bool = False,
) -> dict[str, bool]:
    return {
        "reply_guard": settings.ENABLE_REPLY_GUARD,
        "customer_memory": settings.ENABLE_CUSTOMER_MEMORY,
        "offline_review": (
            settings.ENABLE_OFFLINE_QA
            or settings.ENABLE_OFFLINE_KNOWLEDGE_GAP
            or settings.ENABLE_OFFLINE_MEMORY
        ),
        "offline_qa": settings.ENABLE_OFFLINE_QA,
        "offline_knowledge_gap": settings.ENABLE_OFFLINE_KNOWLEDGE_GAP,
        "offline_memory": settings.ENABLE_OFFLINE_MEMORY,
        "offline_review_running": offline_review_running,
        "hybrid_retrieval": settings.ENABLE_HYBRID_RETRIEVAL,
        "youzan_mock_mode": settings.YOUZAN_MOCK_MODE,
    }


def _is_configured_secret(value: object) -> bool:
    return bool(str(value or "").strip())
