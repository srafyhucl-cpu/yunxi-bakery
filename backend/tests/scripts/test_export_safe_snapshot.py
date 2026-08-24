"""安全评测快照导出的数据边界合同测试。"""

import importlib.util
import sqlite3
from pathlib import Path

import pytest


def load_exporter():
    script_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "export_safe_snapshot.py"
    )
    spec = importlib.util.spec_from_file_location("export_safe_snapshot", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def create_source_database(path: Path, *, include_unknown_table: bool = False) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE knowledge_base (
                id INTEGER PRIMARY KEY, category TEXT, content_type TEXT,
                title TEXT, content TEXT, keywords TEXT, priority INTEGER,
                is_active INTEGER, audience TEXT, review_status TEXT,
                valid_from TEXT, valid_until TEXT, youzan_item_id TEXT,
                created_by TEXT
            );
            CREATE TABLE youzan_products (
                item_id INTEGER PRIMARY KEY, title TEXT, alias TEXT,
                price_fen INTEGER, stock INTEGER, image TEXT, is_active INTEGER,
                skus_json TEXT, item_props_json TEXT, desc TEXT, tags TEXT,
                tag_ids_json TEXT, classification_ids_json TEXT,
                group_ids_json TEXT, second_group_ids_json TEXT,
                leaf_category_ids_json TEXT, item_no TEXT, updated_at TEXT,
                last_sync_ref TEXT
            );
            CREATE TABLE youzan_product_categories (
                tag_id TEXT PRIMARY KEY, title TEXT, sort INTEGER,
                product_count INTEGER, is_public INTEGER, updated_at TEXT
            );
            CREATE TABLE messages (id TEXT, content TEXT, channel_msg_id TEXT);
            CREATE TABLE miniapp_addresses (id TEXT, address TEXT);
            CREATE TABLE customer_profiles (id TEXT, profile TEXT);
            CREATE TABLE conversation_summaries (id TEXT, summary TEXT);
            CREATE TABLE group_registrations (id TEXT, opengid TEXT);
            CREATE TABLE customer_identity_links (id TEXT, open_id TEXT);
            CREATE TABLE customer_master (id TEXT, phone TEXT);
            """
        )
        connection.execute(
            """
            INSERT INTO knowledge_base VALUES
            (1, 'faq', 'faq', '配送规则', '仅用于测试的脱敏知识',
             '配送', 1, 1, 'all', 'published', '', '', '', '13800138000')
            """
        )
        connection.execute(
            """
            INSERT INTO youzan_products VALUES
            (1001, '草莓蛋糕', 'strawberry', 19900, 5, '', 1, '[]', '[]',
             '商品描述', '', '[]', '[]', '[]', '[]', '[]', '', '2026-07-11',
             'gh_sensitive_ref')
            """
        )
        connection.execute(
            "INSERT INTO youzan_product_categories VALUES (?, ?, ?, ?, ?, ?)",
            ("cake", "蛋糕", 1, 1, 1, "2026-07-11"),
        )
        if include_unknown_table:
            connection.execute("CREATE TABLE newly_added_table (id TEXT)")
        connection.commit()


def test_export_creates_only_allowed_tables_and_columns(tmp_path: Path) -> None:
    exporter = load_exporter()
    source_path = tmp_path / "source.db"
    destination_path = tmp_path / "safe.db"
    create_source_database(source_path)

    counts = exporter.export_safe_snapshot(source_path, destination_path)

    assert counts == {
        "knowledge_base": 1,
        "youzan_products": 1,
        "youzan_product_categories": 1,
    }
    with sqlite3.connect(destination_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert tables == {
            "knowledge_base",
            "youzan_products",
            "youzan_product_categories",
        }
        assert "created_by" not in {
            row[1] for row in connection.execute("PRAGMA table_info(knowledge_base)")
        }
        assert "last_sync_ref" not in {
            row[1] for row in connection.execute("PRAGMA table_info(youzan_products)")
        }
        values = list(connection.execute("SELECT title, content FROM knowledge_base"))
        values.extend(connection.execute("SELECT title, desc FROM youzan_products"))
        assert all("13800138000" not in str(value) for row in values for value in row)
        assert all(
            "gh_sensitive_ref" not in str(value) for row in values for value in row
        )


def test_export_fails_closed_for_unknown_source_table(tmp_path: Path) -> None:
    exporter = load_exporter()
    source_path = tmp_path / "source.db"
    destination_path = tmp_path / "safe.db"
    create_source_database(source_path, include_unknown_table=True)

    with pytest.raises(ValueError, match="未登记表"):
        exporter.export_safe_snapshot(source_path, destination_path)
    assert not destination_path.exists()


def test_export_fails_closed_for_sensitive_allowed_value(tmp_path: Path) -> None:
    exporter = load_exporter()
    source_path = tmp_path / "source.db"
    destination_path = tmp_path / "safe.db"
    create_source_database(source_path)
    with sqlite3.connect(source_path) as connection:
        connection.execute(
            "UPDATE knowledge_base SET content = ?", ("请联系 13800138000",)
        )
        connection.commit()

    with pytest.raises(ValueError, match="个人标识"):
        exporter.export_safe_snapshot(source_path, destination_path)
    assert not destination_path.exists()
