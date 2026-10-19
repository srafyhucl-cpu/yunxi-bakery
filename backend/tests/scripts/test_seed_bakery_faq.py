"""bakery FAQ 种子导入脚本测试。

覆盖：夹具内容合法性、dry-run 不写库、apply 写入 30 条、重复导入幂等、
主题覆盖与商品库存/价格表标记清理。
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sqlite3
import sys
from collections import Counter
from contextlib import closing
from pathlib import Path
from types import ModuleType

from app.database import close_db, init_db

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "seed_bakery_faq.py"
FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "bakery_faq_30.json"
EXPECTED_ENTRY_COUNT = 30
ALLOWED_CATEGORIES = {"faq", "policy", "after_sales"}
REQUIRED_TEXT_FIELDS = ("source_ref", "category", "title", "content", "keywords")
FORBIDDEN_MARKERS = (
    "当前可用库存",
    "实时库存",
    "可售库存",
    "[UMP:",
    "价格表",
    "库存表",
)


def load_seed_bakery_faq_module() -> ModuleType:
    """按文件路径加载种子脚本模块。"""
    spec = importlib.util.spec_from_file_location("seed_bakery_faq", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_fixture_payload() -> list[dict]:
    """读取 FAQ 种子夹具。"""
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    return payload


async def _create_database(db_path: Path) -> None:
    """用真实 init_db 建库（含迁移），不做任何 mock。"""
    conn = await init_db(str(db_path))
    await close_db(conn)


def _fetch_rows(db_path: Path) -> list[sqlite3.Row]:
    """读取知识库全部行。"""
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT id, category, content_type, title, content, keywords, priority, "
            "is_active, last_sync_source, last_sync_ref, content_origin, created_by, "
            "updated_by, vector_sync_status, audience, review_status "
            "FROM knowledge_base ORDER BY id"
        ).fetchall()


def _count_rows(db_path: Path) -> int:
    """统计知识库行数。"""
    with closing(sqlite3.connect(db_path)) as conn:
        cursor = conn.execute("SELECT COUNT(id) FROM knowledge_base")
        return int(cursor.fetchone()[0])


def test_fixture_contains_exactly_thirty_valid_entries() -> None:
    """夹具必须是 30 条、分类合法、必填字段非空且 source_ref 唯一。"""
    payload = load_fixture_payload()

    assert len(payload) == EXPECTED_ENTRY_COUNT
    seen_refs: set[str] = set()
    for item in payload:
        assert set(item) == {
            "source_ref",
            "category",
            "title",
            "content",
            "keywords",
            "priority",
        }
        for field_name in REQUIRED_TEXT_FIELDS:
            assert isinstance(item[field_name], str)
            assert item[field_name].strip()
        assert item["category"] in ALLOWED_CATEGORIES
        assert isinstance(item["priority"], int)
        assert item["source_ref"] not in seen_refs
        seen_refs.add(item["source_ref"])


def test_fixture_covers_high_frequency_service_topics() -> None:
    """30 条必须覆盖配送、退改、过敏原、保存、发票、储值认领等高频主题。"""
    payload = load_fixture_payload()
    titles = {item["title"] for item in payload}
    haystack = " ".join(
        f"{item['title']} {item['keywords']} {item['content']}" for item in payload
    )

    for topic in ("配送", "退改", "过敏原", "保存", "发票", "储值"):
        assert topic in haystack
    assert "配送范围与运费" in titles
    assert "退改规则" in titles
    assert "有过敏原或饮食限制怎么办？" in titles
    assert "奶油品质与保存方式" in titles
    assert "发票与企业团购" in titles
    assert "储值余额与会员认领" in titles


def test_fixture_has_no_inventory_or_price_table_markers() -> None:
    """夹具不得包含商品实时库存或价格表等易过期内容。"""
    payload = load_fixture_payload()

    for item in payload:
        blob = f"{item['title']} {item['content']} {item['keywords']}"
        for marker in FORBIDDEN_MARKERS:
            assert marker not in blob
        assert item["category"] != "product"


async def test_dry_run_does_not_write_rows(tmp_path: Path) -> None:
    """dry-run 只报告，不写知识库。"""
    module = load_seed_bakery_faq_module()
    db_path = tmp_path / "bot.db"
    await _create_database(db_path)

    report = await module.seed_bakery_faq(
        db_path=str(db_path),
        fixture_path=str(FIXTURE_PATH),
        should_apply=False,
    )

    assert report.schema_ready is True
    assert report.applied is False
    assert report.total_entries == EXPECTED_ENTRY_COUNT
    assert report.inserted_count == 0
    assert report.skipped_count == 0
    assert report.active_rows_before == 0
    assert report.active_rows_after == 0
    assert _count_rows(db_path) == 0


async def test_apply_inserts_thirty_entries_with_expected_fields(
    tmp_path: Path,
) -> None:
    """apply 写入 30 条，关键字段与夹具内容一致。"""
    module = load_seed_bakery_faq_module()
    db_path = tmp_path / "bot.db"
    await _create_database(db_path)
    payload = load_fixture_payload()
    payload_by_ref = {item["source_ref"]: item for item in payload}

    report = await module.seed_bakery_faq(
        db_path=str(db_path),
        fixture_path=str(FIXTURE_PATH),
        should_apply=True,
    )

    assert report.schema_ready is True
    assert report.applied is True
    assert report.inserted_count == EXPECTED_ENTRY_COUNT
    assert report.skipped_count == 0
    assert report.active_rows_before == 0
    assert report.active_rows_after == EXPECTED_ENTRY_COUNT

    rows = _fetch_rows(db_path)
    assert len(rows) == EXPECTED_ENTRY_COUNT
    for row in rows:
        expected = payload_by_ref[row["last_sync_ref"]]
        assert row["category"] == expected["category"]
        assert row["content_type"] == "faq"
        assert row["title"] == expected["title"]
        assert row["content"] == expected["content"]
        assert row["keywords"] == expected["keywords"]
        assert row["priority"] == expected["priority"]
        assert row["is_active"] == 1
        assert row["last_sync_source"] == "bakery_faq_seed_v1"
        assert row["content_origin"] == "youzan_knowledge_base"
        assert row["created_by"] == "seed_bakery_faq"
        assert row["updated_by"] == "seed_bakery_faq"
        assert row["vector_sync_status"] == "pending"
        assert row["audience"] == "all"
        assert row["review_status"] == "published"

    assert {row["last_sync_ref"] for row in rows} == set(payload_by_ref)
    assert report.category_counts == dict(
        sorted(Counter(row["category"] for row in rows).items())
    )


async def test_repeated_apply_skips_all_entries(tmp_path: Path) -> None:
    """重复 apply 全部跳过，总数不变。"""
    module = load_seed_bakery_faq_module()
    db_path = tmp_path / "bot.db"
    await _create_database(db_path)

    first_report = await module.seed_bakery_faq(
        db_path=str(db_path),
        fixture_path=str(FIXTURE_PATH),
        should_apply=True,
    )
    second_report = await module.seed_bakery_faq(
        db_path=str(db_path),
        fixture_path=str(FIXTURE_PATH),
        should_apply=True,
    )

    assert first_report.inserted_count == EXPECTED_ENTRY_COUNT
    assert second_report.inserted_count == 0
    assert second_report.skipped_count == EXPECTED_ENTRY_COUNT
    assert second_report.all_entries_present is True
    assert _count_rows(db_path) == EXPECTED_ENTRY_COUNT


async def test_dry_run_reports_existing_entries_as_skipped(tmp_path: Path) -> None:
    """已导入后再 dry-run 应报告全部跳过且不新增行。"""
    module = load_seed_bakery_faq_module()
    db_path = tmp_path / "bot.db"
    await _create_database(db_path)
    await module.seed_bakery_faq(
        db_path=str(db_path),
        fixture_path=str(FIXTURE_PATH),
        should_apply=True,
    )

    report = await module.seed_bakery_faq(
        db_path=str(db_path),
        fixture_path=str(FIXTURE_PATH),
        should_apply=False,
    )

    assert report.applied is False
    assert report.skipped_count == EXPECTED_ENTRY_COUNT
    assert report.all_entries_present is True
    assert _count_rows(db_path) == EXPECTED_ENTRY_COUNT


async def test_invalid_fixture_is_refused_without_writing(tmp_path: Path) -> None:
    """夹具条数或分类不合法时拒绝导入且不写库。"""
    module = load_seed_bakery_faq_module()
    db_path = tmp_path / "bot.db"
    await _create_database(db_path)
    broken_fixture = tmp_path / "broken.json"
    broken_fixture.write_text(
        json.dumps(
            [
                {
                    "source_ref": "prod_1",
                    "category": "product",
                    "title": "标题",
                    "content": "内容",
                    "keywords": "关键词",
                    "priority": 10,
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = await module.seed_bakery_faq(
        db_path=str(db_path),
        fixture_path=str(broken_fixture),
        should_apply=True,
    )

    assert report.status == "failed"
    assert report.validation_errors
    assert report.inserted_count == 0
    assert _count_rows(db_path) == 0


def test_main_json_output_is_machine_readable(tmp_path: Path, capsys) -> None:
    """--json 输出可被机器解析。"""
    module = load_seed_bakery_faq_module()
    db_path = tmp_path / "bot.db"

    exit_code = module.main(["--db-path", str(db_path), "--json"])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert payload["metadata"]["seed_source"] == "bakery_faq_seed_v1"
    assert payload["report"]["total_entries"] == EXPECTED_ENTRY_COUNT
    assert payload["report"]["inserted_count"] == 0


def test_main_apply_writes_report_file_and_refuses_overwrite(
    tmp_path: Path, capsys
) -> None:
    """--output 写报告并拒绝覆盖已存在文件。"""
    module = load_seed_bakery_faq_module()
    db_path = tmp_path / "bot.db"
    report_path = tmp_path / "reports" / "bakery-faq.json"

    exit_code = module.main(
        ["--db-path", str(db_path), "--apply", "--json", "--output", str(report_path)]
    )

    assert exit_code == 0
    assert report_path.read_bytes().startswith(module.UTF8_BOM)
    payload = json.loads(report_path.read_text(encoding="utf-8-sig"))
    assert payload["report"]["inserted_count"] == EXPECTED_ENTRY_COUNT
    assert payload["report"]["active_rows_after"] == EXPECTED_ENTRY_COUNT

    exit_code = module.main(
        ["--db-path", str(db_path), "--apply", "--json", "--output", str(report_path)]
    )

    assert exit_code == 2
    assert "拒绝覆盖" in capsys.readouterr().err


def test_main_output_requires_json_flag(tmp_path: Path, capsys) -> None:
    """--output 必须配合 --json 使用。"""
    module = load_seed_bakery_faq_module()

    exit_code = module.main(["--output", str(tmp_path / "bakery-faq.json")])

    assert exit_code == 2
    assert "--output 必须配合 --json 使用" in capsys.readouterr().err


def test_main_dry_run_on_existing_database_reports_pending_entries(
    tmp_path: Path, capsys
) -> None:
    """库已存在时 dry-run 报告待写入条数，不写库。"""
    module = load_seed_bakery_faq_module()
    db_path = tmp_path / "bot.db"
    asyncio.run(_create_database(db_path))

    exit_code = module.main(["--db-path", str(db_path)])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "mode=dry-run" in output
    assert "total_entries=30" in output
    assert "inserted_count=0" in output
    assert "then rerun with --apply" in output
    assert _count_rows(db_path) == 0
