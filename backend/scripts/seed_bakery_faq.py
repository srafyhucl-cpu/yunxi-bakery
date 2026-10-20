"""芸熙烘焙 30 条通用 FAQ 种子导入脚本。

把生产知识库里已固化的通用 FAQ / 政策 / 售后条目固化为一份可重复导入的 JSON 夹具
（tests/fixtures/bakery_faq_30.json），供本地与生产环境重复执行：

- 幂等键：last_sync_source=bakery_faq_seed_v1 与 last_sync_ref=source_ref；
- --apply 才会写库：先 init_db 初始化/迁移目标库，再在单个事务内插入缺失条目；
- 默认 dry-run：以只读方式打开现有库并给出报告，绝不写库；
- 只读 JSON 夹具，不访问有赞 API，也不连接生产库。

用法（先干跑再入库）：
    python scripts/seed_bakery_faq.py --db-path data/bot.db
    python scripts/seed_bakery_faq.py --db-path data/bot.db --apply
    python scripts/seed_bakery_faq.py --db-path data/bot.db --apply --json --output reports/bakery-faq-{timestamp}.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
from collections import Counter
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import pathname2url

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import settings  # noqa: E402
from app.database import close_db, init_db  # noqa: E402
from app.models.knowledge import (  # noqa: E402
    KnowledgeAudience,
    KnowledgeCategory,
    KnowledgeContentType,
    KnowledgeReviewStatus,
    VectorSyncStatus,
)
from scripts.preflight_production import (  # noqa: E402
    OUTPUT_TIMESTAMP_FORMAT,
    OUTPUT_TIMESTAMP_PLACEHOLDER,
    UTF8_BOM,
    resolve_project_path,
)

FAQ_SEED_SOURCE = "bakery_faq_seed_v1"
FAQ_SEED_ORIGIN = "youzan_knowledge_base"
FAQ_SEED_ACTOR = "seed_bakery_faq"
DEFAULT_FIXTURE_PATH = ROOT_DIR / "tests" / "fixtures" / "bakery_faq_30.json"
EXPECTED_ENTRY_COUNT = 30
ALLOWED_CATEGORIES = (
    KnowledgeCategory.FAQ.value,
    KnowledgeCategory.POLICY.value,
    KnowledgeCategory.AFTER_SALES.value,
)
REQUIRED_TEXT_FIELDS = ("source_ref", "category", "title", "content", "keywords")
EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_USAGE = 2
INSERT_STATEMENT = (
    "INSERT INTO knowledge_base ("
    "category, content_type, title, content, keywords, priority, is_active, "
    "last_sync_source, last_sync_ref, content_origin, created_by, updated_by, "
    "vector_sync_status, audience, review_status"
    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


@dataclass(frozen=True)
class BakeryFaqEntry:
    """一条可导入的 FAQ 种子条目。"""

    source_ref: str
    category: str
    title: str
    content: str
    keywords: str
    priority: int


@dataclass(frozen=True)
class BakeryFaqSeedReport:
    """种子导入报告，供人工复核与机器解析。"""

    database_path: Path
    fixture_path: Path
    applied: bool
    schema_ready: bool
    total_entries: int
    inserted_count: int
    skipped_count: int
    active_rows_before: int
    active_rows_after: int
    category_counts: dict[str, int] = field(default_factory=dict)
    validation_errors: tuple[str, ...] = ()

    @property
    def all_entries_present(self) -> bool:
        """30 条是否已全部存在于目标库。"""
        return (
            self.schema_ready
            and not self.validation_errors
            and self.total_entries > 0
            and self.skipped_count == self.total_entries
        )

    @property
    def status(self) -> str:
        """报告状态：failed / ready / applied / already_present。"""
        if not self.schema_ready or self.validation_errors:
            return "failed"
        if self.all_entries_present:
            return "already_present"
        if self.applied:
            return "applied" if self.inserted_count > 0 else "unchanged"
        return "ready"

    def to_dict(self) -> dict[str, object]:
        return {
            "database_path": str(self.database_path),
            "fixture_path": str(self.fixture_path),
            "applied": self.applied,
            "schema_ready": self.schema_ready,
            "total_entries": self.total_entries,
            "inserted_count": self.inserted_count,
            "skipped_count": self.skipped_count,
            "active_rows_before": self.active_rows_before,
            "active_rows_after": self.active_rows_after,
            "category_counts": dict(self.category_counts),
            "validation_errors": list(self.validation_errors),
            "all_entries_present": self.all_entries_present,
        }


def parse_args(argv: list[str]) -> argparse.Namespace:
    """解析命令行参数；默认 dry-run，不写库。"""
    parser = argparse.ArgumentParser(description="Seed bakery FAQ knowledge entries")
    parser.add_argument(
        "--db-path",
        default=settings.DB_PATH,
        help="目标 SQLite 数据库路径，默认读取 DB_PATH。",
    )
    parser.add_argument(
        "--fixture",
        default=str(DEFAULT_FIXTURE_PATH),
        help="FAQ 种子 JSON 夹具路径，默认 tests/fixtures/bakery_faq_30.json。",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="只校验并输出报告，不写库（默认行为）。",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="校验通过后实际写入缺失条目；重复执行只跳过已存在条目。",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出机器可读 JSON，便于导入前后留档或部署脚本解析。",
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


def load_fixture_entries(fixture_path: Path) -> tuple[list[BakeryFaqEntry], list[str]]:
    """读取并校验夹具，返回条目与校验错误列表。"""
    try:
        raw_bytes = fixture_path.read_bytes()
    except OSError as exc:
        return [], [f"无法读取夹具文件 {fixture_path}: {exc}"]
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [], [f"夹具不是合法 UTF-8 JSON: {exc}"]
    return validate_raw_entries(payload)


def validate_raw_entries(payload: object) -> tuple[list[BakeryFaqEntry], list[str]]:
    """校验夹具结构：条数、分类、必填字段、source_ref 唯一性。"""
    errors: list[str] = []
    if not isinstance(payload, list):
        return [], ["夹具顶层必须是数组"]

    entries: list[BakeryFaqEntry] = []
    seen_refs: set[str] = set()
    for index, raw_item in enumerate(payload):
        if not isinstance(raw_item, dict):
            errors.append(f"第 {index + 1} 条不是对象")
            continue
        item_errors = _validate_raw_item(index, raw_item, seen_refs)
        if item_errors:
            errors.extend(item_errors)
            continue
        entries.append(
            BakeryFaqEntry(
                source_ref=str(raw_item["source_ref"]).strip(),
                category=str(raw_item["category"]).strip(),
                title=str(raw_item["title"]).strip(),
                content=str(raw_item["content"]).strip(),
                keywords=str(raw_item["keywords"]).strip(),
                priority=int(raw_item["priority"]),
            )
        )

    if len(payload) != EXPECTED_ENTRY_COUNT:
        errors.append(f"夹具条数应为 {EXPECTED_ENTRY_COUNT}，实际为 {len(payload)}")
    if len({entry.source_ref for entry in entries}) != len(entries):
        errors.append("夹具存在重复的 source_ref")
    return entries, errors


def _validate_raw_item(index: int, raw_item: dict, seen_refs: set[str]) -> list[str]:
    """校验单条夹具条目，返回错误列表。"""
    errors: list[str] = []
    position = index + 1
    for field_name in REQUIRED_TEXT_FIELDS:
        value = raw_item.get(field_name)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"第 {position} 条缺少必填字段 {field_name}")
    category = raw_item.get("category")
    if isinstance(category, str) and category.strip() not in ALLOWED_CATEGORIES:
        errors.append(
            f"第 {position} 条分类非法: {category.strip()}，允许值 {list(ALLOWED_CATEGORIES)}"
        )
    priority = raw_item.get("priority")
    if not isinstance(priority, int) or isinstance(priority, bool):
        errors.append(f"第 {position} 条 priority 必须是整数")
    source_ref = raw_item.get("source_ref")
    if isinstance(source_ref, str) and source_ref.strip():
        if source_ref.strip() in seen_refs:
            errors.append(f"第 {position} 条 source_ref 重复: {source_ref.strip()}")
        seen_refs.add(source_ref.strip())
    return errors


def count_active_rows(conn: sqlite3.Connection) -> int:
    """统计知识库启用条目数。"""
    cursor = conn.execute(
        "SELECT COUNT(id) FROM knowledge_base WHERE is_active = ?",
        (1,),
    )
    return int(cursor.fetchone()[0])


def get_existing_refs(conn: sqlite3.Connection) -> set[str]:
    """取出本脚本已导入过的 source_ref 集合，作为幂等判定依据。"""
    cursor = conn.execute(
        "SELECT last_sync_ref FROM knowledge_base WHERE last_sync_source = ?",
        (FAQ_SEED_SOURCE,),
    )
    return {str(row[0]) for row in cursor.fetchall()}


def insert_entry(conn: sqlite3.Connection, entry: BakeryFaqEntry) -> None:
    """写入一条 FAQ 种子条目。"""
    conn.execute(
        INSERT_STATEMENT,
        (
            entry.category,
            KnowledgeContentType.FAQ.value,
            entry.title,
            entry.content,
            entry.keywords,
            entry.priority,
            1,
            FAQ_SEED_SOURCE,
            entry.source_ref,
            FAQ_SEED_ORIGIN,
            FAQ_SEED_ACTOR,
            FAQ_SEED_ACTOR,
            VectorSyncStatus.PENDING.value,
            KnowledgeAudience.ALL.value,
            KnowledgeReviewStatus.PUBLISHED.value,
        ),
    )


def _build_report(
    *,
    database_path: Path,
    fixture_path: Path,
    applied: bool,
    schema_ready: bool,
    entries: list[BakeryFaqEntry],
    inserted_count: int,
    skipped_count: int,
    active_rows_before: int,
    active_rows_after: int,
    validation_errors: list[str],
) -> BakeryFaqSeedReport:
    """汇总导入报告。"""
    category_counts = Counter(entry.category for entry in entries)
    return BakeryFaqSeedReport(
        database_path=database_path,
        fixture_path=fixture_path,
        applied=applied,
        schema_ready=schema_ready,
        total_entries=len(entries),
        inserted_count=inserted_count,
        skipped_count=skipped_count,
        active_rows_before=active_rows_before,
        active_rows_after=active_rows_after,
        category_counts=dict(sorted(category_counts.items())),
        validation_errors=tuple(validation_errors),
    )


def _dry_run_report(
    *,
    database_path: Path,
    fixture_path: Path,
    entries: list[BakeryFaqEntry],
    validation_errors: list[str],
) -> BakeryFaqSeedReport:
    """只读盘点：统计已存在条目与启用条目数，不写库。"""
    if not database_path.exists():
        return _build_report(
            database_path=database_path,
            fixture_path=fixture_path,
            applied=False,
            schema_ready=False,
            entries=entries,
            inserted_count=0,
            skipped_count=0,
            active_rows_before=0,
            active_rows_after=0,
            validation_errors=validation_errors,
        )
    try:
        with closing(
            sqlite3.connect(
                f"file:{pathname2url(str(database_path))}?mode=ro", uri=True
            )
        ) as conn:
            existing_refs = get_existing_refs(conn)
            active_rows = count_active_rows(conn)
    except sqlite3.DatabaseError:
        return _build_report(
            database_path=database_path,
            fixture_path=fixture_path,
            applied=False,
            schema_ready=False,
            entries=entries,
            inserted_count=0,
            skipped_count=0,
            active_rows_before=0,
            active_rows_after=0,
            validation_errors=validation_errors,
        )
    skipped_count = sum(1 for entry in entries if entry.source_ref in existing_refs)
    return _build_report(
        database_path=database_path,
        fixture_path=fixture_path,
        applied=False,
        schema_ready=True,
        entries=entries,
        inserted_count=0,
        skipped_count=skipped_count,
        active_rows_before=active_rows,
        active_rows_after=active_rows,
        validation_errors=validation_errors,
    )


async def seed_bakery_faq(
    *,
    db_path: str,
    fixture_path: str,
    should_apply: bool,
) -> BakeryFaqSeedReport:
    """校验夹具并按需写入知识库，返回导入报告。"""
    resolved_db_path = resolve_project_path(db_path)
    resolved_fixture_path = resolve_project_path(fixture_path)
    entries, validation_errors = load_fixture_entries(resolved_fixture_path)
    if validation_errors:
        return _build_report(
            database_path=resolved_db_path,
            fixture_path=resolved_fixture_path,
            applied=should_apply,
            schema_ready=False,
            entries=entries,
            inserted_count=0,
            skipped_count=0,
            active_rows_before=0,
            active_rows_after=0,
            validation_errors=validation_errors,
        )

    if not should_apply:
        return _dry_run_report(
            database_path=resolved_db_path,
            fixture_path=resolved_fixture_path,
            entries=entries,
            validation_errors=validation_errors,
        )

    if not await _init_target_database(resolved_db_path):
        return _build_report(
            database_path=resolved_db_path,
            fixture_path=resolved_fixture_path,
            applied=should_apply,
            schema_ready=False,
            entries=entries,
            inserted_count=0,
            skipped_count=0,
            active_rows_before=0,
            active_rows_after=0,
            validation_errors=validation_errors,
        )

    try:
        with closing(sqlite3.connect(resolved_db_path)) as conn, conn:
            active_rows_before = count_active_rows(conn)
            inserted_count, skipped_count = _apply_entries(conn, entries)
            active_rows_after = count_active_rows(conn)
    except sqlite3.DatabaseError:
        return _build_report(
            database_path=resolved_db_path,
            fixture_path=resolved_fixture_path,
            applied=should_apply,
            schema_ready=False,
            entries=entries,
            inserted_count=0,
            skipped_count=0,
            active_rows_before=0,
            active_rows_after=0,
            validation_errors=validation_errors,
        )

    return _build_report(
        database_path=resolved_db_path,
        fixture_path=resolved_fixture_path,
        applied=True,
        schema_ready=True,
        entries=entries,
        inserted_count=inserted_count,
        skipped_count=skipped_count,
        active_rows_before=active_rows_before,
        active_rows_after=active_rows_after,
        validation_errors=validation_errors,
    )


async def _init_target_database(database_path: Path) -> bool:
    """初始化并迁移目标库，返回库是否可用。"""
    try:
        conn = await init_db(str(database_path))
    except (sqlite3.DatabaseError, OSError):
        return False
    await close_db(conn)
    return True


def _apply_entries(
    conn: sqlite3.Connection, entries: list[BakeryFaqEntry]
) -> tuple[int, int]:
    """写入缺失条目，返回（新增数，跳过数）；由调用方事务保证原子性。"""
    existing_refs = get_existing_refs(conn)
    entries_to_insert = [
        entry for entry in entries if entry.source_ref not in existing_refs
    ]
    for entry in entries_to_insert:
        insert_entry(conn, entry)
    return len(entries_to_insert), len(entries) - len(entries_to_insert)


def print_report(report: BakeryFaqSeedReport) -> None:
    """输出人工可读报告。"""
    mode = "apply" if report.applied else "dry-run"
    print("Bakery FAQ seed")
    print(f"mode={mode}")
    print(f"db_path={report.database_path}")
    print(f"fixture_path={report.fixture_path}")
    print(f"schema_ready={report.schema_ready}")
    print(f"total_entries={report.total_entries}")
    print(f"inserted_count={report.inserted_count}")
    print(f"skipped_count={report.skipped_count}")
    print(f"active_rows_before={report.active_rows_before}")
    print(f"active_rows_after={report.active_rows_after}")
    print(
        "category_counts="
        + json.dumps(report.category_counts, ensure_ascii=False, sort_keys=True)
    )
    for error in report.validation_errors:
        print(f"validation_error={error}")
    if report.validation_errors:
        print("action=fix the fixture file, then rerun the seed")
    elif not report.schema_ready:
        print(
            "action=run the seed with --apply to initialize the target database, "
            "or migrate the database first"
        )
    elif report.all_entries_present:
        print(
            "action=bakery FAQ entries already exist; rebuild embeddings if cache is missing"
        )
    elif not report.applied:
        print("action=review dry-run output, then rerun with --apply")
    else:
        print(
            "action=run scripts/rebuild_embeddings.py dry-run before applying embedding rebuild"
        )


def build_json_report(report: BakeryFaqSeedReport) -> dict[str, object]:
    """构造机器可读报告。"""
    generated_at = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    return {
        "status": report.status,
        "metadata": {
            "generated_at": generated_at,
            "project_root": str(ROOT_DIR),
            "database_path": str(report.database_path),
            "fixture_path": str(report.fixture_path),
            "seed_source": FAQ_SEED_SOURCE,
        },
        "report": report.to_dict(),
    }


def expand_output_path(output_path_value: str) -> Path:
    """展开输出路径中的 {timestamp} 占位符。"""
    timestamp = datetime.now().strftime(OUTPUT_TIMESTAMP_FORMAT)
    return Path(output_path_value.replace(OUTPUT_TIMESTAMP_PLACEHOLDER, timestamp))


def ensure_output_path_available(output_path_value: str) -> Path:
    """拒绝覆盖已存在的报告文件。"""
    output_path = expand_output_path(output_path_value)
    if output_path.exists():
        raise FileExistsError(f"报告文件已存在，拒绝覆盖: {output_path}")
    return output_path


def write_json_report(output_path: Path, json_bytes: bytes) -> None:
    """写入报告文件。"""
    if output_path.exists():
        raise FileExistsError(f"报告文件已存在，拒绝覆盖: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(UTF8_BOM + json_bytes)


async def async_main(argv: list[str] | None = None) -> int:
    """脚本主流程。"""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.output and not args.json:
        print("--output 必须配合 --json 使用。", file=sys.stderr)
        return EXIT_USAGE
    output_path: Path | None = None
    if args.output:
        try:
            output_path = ensure_output_path_available(args.output)
        except FileExistsError as exc:
            print(str(exc), file=sys.stderr)
            return EXIT_USAGE

    report = await seed_bakery_faq(
        db_path=args.db_path,
        fixture_path=args.fixture,
        should_apply=args.apply,
    )
    if args.json:
        json_bytes = (
            json.dumps(build_json_report(report), ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        if output_path is None:
            sys.stdout.buffer.write(json_bytes)
        else:
            try:
                write_json_report(output_path, json_bytes)
            except FileExistsError as exc:
                print(str(exc), file=sys.stderr)
                return EXIT_USAGE
    else:
        print_report(report)
    if report.validation_errors:
        return EXIT_REFUSED
    if not report.schema_ready:
        return EXIT_REFUSED
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """同步入口。"""
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
