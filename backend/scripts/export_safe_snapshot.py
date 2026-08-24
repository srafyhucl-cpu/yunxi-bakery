"""从生产 SQLite 快照导出仅含允许表和允许列的评测库。"""

from __future__ import annotations

import argparse
import re
import sqlite3
from contextlib import closing
from pathlib import Path

KNOWN_SOURCE_TABLES = frozenset(
    {
        "_schema_version",
        "analytics_events",
        "content_change_history",
        "conversation_reviews",
        "conversation_summaries",
        "customer_groups",
        "customer_identity_links",
        "customer_master",
        "customer_merge_reviews",
        "customer_profiles",
        "customer_source_snapshots",
        "group_campaigns",
        "group_registrations",
        "human_transfers",
        "knowledge_base",
        "knowledge_gaps",
        "knowledge_retrieval_logs",
        "messages",
        "miniapp_address_audit",
        "miniapp_addresses",
        "order_events",
        "orders",
        "sessions",
        "shop_config",
        "wecom_kf_message_ledger",
        "wecom_kf_sync_states",
        "youzan_orders",
        "youzan_product_categories",
        "youzan_products",
        "youzan_webhook_events",
    }
)

ALLOWED_COLUMNS = {
    "knowledge_base": (
        "id",
        "category",
        "content_type",
        "title",
        "content",
        "keywords",
        "priority",
        "is_active",
        "audience",
        "review_status",
        "valid_from",
        "valid_until",
        "youzan_item_id",
    ),
    "youzan_products": (
        "item_id",
        "title",
        "alias",
        "price_fen",
        "stock",
        "image",
        "is_active",
        "skus_json",
        "item_props_json",
        "desc",
        "tags",
        "tag_ids_json",
        "classification_ids_json",
        "group_ids_json",
        "second_group_ids_json",
        "leaf_category_ids_json",
        "item_no",
        "updated_at",
    ),
    "youzan_product_categories": (
        "tag_id",
        "title",
        "sort",
        "product_count",
        "is_public",
        "updated_at",
    ),
}

CREATE_STATEMENTS = {
    "knowledge_base": """
        CREATE TABLE knowledge_base (
            id INTEGER PRIMARY KEY,
            category TEXT NOT NULL,
            content_type TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            keywords TEXT,
            priority INTEGER,
            is_active INTEGER,
            audience TEXT,
            review_status TEXT,
            valid_from TEXT,
            valid_until TEXT,
            youzan_item_id TEXT
        )
    """,
    "youzan_products": """
        CREATE TABLE youzan_products (
            item_id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            alias TEXT NOT NULL,
            price_fen INTEGER NOT NULL,
            stock INTEGER NOT NULL,
            image TEXT,
            is_active INTEGER,
            skus_json TEXT,
            item_props_json TEXT,
            desc TEXT,
            tags TEXT,
            tag_ids_json TEXT,
            classification_ids_json TEXT,
            group_ids_json TEXT,
            second_group_ids_json TEXT,
            leaf_category_ids_json TEXT,
            item_no TEXT,
            updated_at TEXT NOT NULL
        )
    """,
    "youzan_product_categories": """
        CREATE TABLE youzan_product_categories (
            tag_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            sort INTEGER,
            product_count INTEGER,
            is_public INTEGER,
            updated_at TEXT
        )
    """,
}

SENSITIVE_PATTERNS = (
    re.compile(r"(?<!\d)1\d{10}(?!\d)"),
    re.compile(r"(?i)(?:openid|unionid|gh_[a-z0-9_-]{8,})"),
)


def _table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = ?", ("table",)
    ).fetchall()
    return {str(row[0]) for row in rows if not str(row[0]).startswith("sqlite_")}


def _validate_source_tables(connection: sqlite3.Connection) -> None:
    unknown_tables = _table_names(connection) - KNOWN_SOURCE_TABLES
    if unknown_tables:
        names = ", ".join(sorted(unknown_tables))
        raise ValueError(f"源库包含未登记表，拒绝导出: {names}")


def _validate_source_columns(
    connection: sqlite3.Connection, table_name: str, columns: tuple[str, ...]
) -> None:
    actual_columns = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM pragma_table_info(?)", (table_name,)
        ).fetchall()
    }
    missing_columns = set(columns) - actual_columns
    if missing_columns:
        names = ", ".join(sorted(missing_columns))
        raise ValueError(f"表 {table_name} 缺少允许列，拒绝导出: {names}")


def _assert_safe_values(
    table_name: str, columns: tuple[str, ...], rows: list[tuple[object, ...]]
) -> None:
    for row in rows:
        for column_name, value in zip(columns, row):
            if not isinstance(value, str):
                continue
            if any(pattern.search(value) for pattern in SENSITIVE_PATTERNS):
                raise ValueError(
                    f"导出数据疑似包含个人标识: {table_name}.{column_name}"
                )


def export_safe_snapshot(source_path: Path, destination_path: Path) -> dict[str, int]:
    """将源库中的允许表和允许列复制到一个全新的 SQLite 库。"""
    if not source_path.is_file():
        raise FileNotFoundError(f"源快照不存在: {source_path}")
    if destination_path.exists():
        raise FileExistsError(f"目标文件已存在，拒绝覆盖: {destination_path}")

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with (
            closing(sqlite3.connect(source_path)) as source,
            closing(sqlite3.connect(destination_path)) as destination,
        ):
            _validate_source_tables(source)
            counts: dict[str, int] = {}
            for table_name, columns in ALLOWED_COLUMNS.items():
                _validate_source_columns(source, table_name, columns)
                quoted_columns = ", ".join(f"[{column}]" for column in columns)
                rows = source.execute(
                    "SELECT " + quoted_columns + " FROM [" + table_name + "]"
                ).fetchall()
                _assert_safe_values(table_name, columns, rows)
                destination.execute(CREATE_STATEMENTS[table_name])
                placeholders = ", ".join("?" for _ in columns)
                destination.executemany(
                    "INSERT INTO ["
                    + table_name
                    + "] ("
                    + quoted_columns
                    + ") VALUES ("
                    + placeholders
                    + ")",
                    rows,
                )
                counts[table_name] = len(rows)
            destination.commit()
            integrity = destination.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise ValueError(f"目标库完整性检查失败: {integrity}")
        return counts
    except Exception:
        if destination_path.exists():
            destination_path.unlink()
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导出安全评测快照")
    parser.add_argument("source", type=Path, help="源 SQLite 快照")
    parser.add_argument("destination", type=Path, help="新的安全评测库")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    counts = export_safe_snapshot(args.source, args.destination)
    for table_name, count in counts.items():
        print(f"{table_name}={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
