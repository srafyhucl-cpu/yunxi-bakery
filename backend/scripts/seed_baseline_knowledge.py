"""为生产环境导入最低可服务的基础客服知识。"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import settings  # noqa: E402
from app.models.knowledge import (  # noqa: E402
    KnowledgeCategory,
    KnowledgeContentType,
    VectorSyncStatus,
)
from scripts.preflight_production import (  # noqa: E402
    OUTPUT_TIMESTAMP_FORMAT,
    OUTPUT_TIMESTAMP_PLACEHOLDER,
    UTF8_BOM,
    resolve_project_path,
)

BASELINE_SOURCE = "baseline_knowledge_seed"
BASELINE_ORIGIN = "ops_baseline_seed"
BASELINE_ACTOR = "production_preflight"
MIGRATION_REQUIRED_ACTION = (
    "run scripts/preflight_production.py or scripts/apply_migrations.py dry-run first; "
    "confirm target database path, then rerun migrations with --apply"
)

KNOWLEDGE_REQUIRED_COLUMNS = {
    "category",
    "content_type",
    "title",
    "content",
    "keywords",
    "priority",
    "is_active",
    "last_sync_source",
    "last_sync_ref",
    "content_origin",
    "created_by",
    "updated_by",
    "vector_sync_status",
}


@dataclass(frozen=True)
class BaselineKnowledgeEntry:
    sync_ref: str
    category: str
    content_type: str
    title: str
    content: str
    keywords: str
    priority: int


@dataclass(frozen=True)
class BaselineSeedReport:
    database_path: Path
    applied: bool
    schema_ready: bool
    active_rows_before: int
    active_rows_after: int
    inserted_count: int
    skipped_count: int
    total_entries: int

    @property
    def all_entries_present(self) -> bool:
        return self.schema_ready and self.skipped_count == self.total_entries

    @property
    def status(self) -> str:
        if not self.schema_ready:
            return "failed"
        if self.all_entries_present:
            return "ready"
        if self.applied and self.active_rows_after > 0:
            return "ready"
        return "failed"

    def to_dict(self) -> dict[str, object]:
        return {
            "database_path": str(self.database_path),
            "applied": self.applied,
            "schema_ready": self.schema_ready,
            "active_rows_before": self.active_rows_before,
            "active_rows_after": self.active_rows_after,
            "inserted_count": self.inserted_count,
            "skipped_count": self.skipped_count,
            "total_entries": self.total_entries,
            "all_entries_present": self.all_entries_present,
        }


BASELINE_ENTRIES: tuple[BaselineKnowledgeEntry, ...] = (
    BaselineKnowledgeEntry(
        sync_ref="ordering_intake",
        category=KnowledgeCategory.FAQ.value,
        content_type=KnowledgeContentType.SCRIPT.value,
        title="下单咨询信息收集",
        content=(
            "顾客咨询下单时，先确认蛋糕用途、人数或尺寸、口味偏好、预算、取货或配送时间、"
            "收货区域、联系人与电话。没有检索到明确商品或库存时，不承诺价格、库存和交付时间，"
            "应说明会为顾客确认可做方案，并在信息完整后转人工或提醒人工跟进。"
        ),
        keywords="下单,预订,尺寸,口味,预算,配送,取货,联系方式",
        priority=90,
    ),
    BaselineKnowledgeEntry(
        sync_ref="product_price_stock_guardrail",
        category=KnowledgeCategory.POLICY.value,
        content_type=KnowledgeContentType.RULE.value,
        title="价格库存口径",
        content=(
            "商品价格、库存、活动优惠和可售规格以有赞商品数据或人工确认为准。AI 未检索到明确商品数据时，"
            "只能介绍咨询流程和需要收集的信息，不能凭经验报价，不能承诺库存，不能替顾客确认订单。"
        ),
        keywords="价格,库存,优惠,规格,有赞,报价,承诺",
        priority=100,
    ),
    BaselineKnowledgeEntry(
        sync_ref="custom_cake_consulting",
        category=KnowledgeCategory.FAQ.value,
        content_type=KnowledgeContentType.SCRIPT.value,
        title="定制蛋糕咨询",
        content=(
            "顾客咨询定制蛋糕时，应收集参考图片、主题风格、尺寸或用餐人数、口味、文字内容、预算、"
            "交付日期和配送区域。涉及造型复杂度、版权图案、急单、特殊食材和最终报价时，必须提示需要人工确认。"
        ),
        keywords="定制蛋糕,参考图,造型,主题,文字,急单,报价",
        priority=88,
    ),
    BaselineKnowledgeEntry(
        sync_ref="delivery_pickup_policy_guardrail",
        category=KnowledgeCategory.POLICY.value,
        content_type=KnowledgeContentType.RULE.value,
        title="配送取货口径",
        content=(
            "配送范围、配送费、可配送时段、取货时间和急单安排以门店实际排期为准。AI 可以先记录顾客期望时间、"
            "地址区域和联系方式，但不得承诺一定准时送达；时间敏感或超出常规范围的需求应转人工确认。"
        ),
        keywords="配送,取货,配送费,时段,急单,地址,排期",
        priority=86,
    ),
    BaselineKnowledgeEntry(
        sync_ref="after_sales_intake",
        category=KnowledgeCategory.AFTER_SALES.value,
        content_type=KnowledgeContentType.SCRIPT.value,
        title="售后问题收集",
        content=(
            "顾客反馈售后问题时，先表达歉意并安抚情绪，再收集订单号、购买渠道、问题描述、照片或视频、"
            "收货时间和联系方式。不要直接承诺退款、补发或赔付，需说明会记录并交由人工客服核实处理。"
        ),
        keywords="售后,退款,补发,赔付,投诉,照片,订单号",
        priority=92,
    ),
    BaselineKnowledgeEntry(
        sync_ref="human_transfer_triggers",
        category=KnowledgeCategory.POLICY.value,
        content_type=KnowledgeContentType.RULE.value,
        title="必须转人工场景",
        content=(
            "出现价格库存无法确认、订单支付或退款、投诉升级、食品安全或过敏风险、急单排期、定制可行性、"
            "顾客要求人工、AI 连续无法回答或外部接口异常时，应立即转人工并附上已收集的信息摘要。"
        ),
        keywords="转人工,投诉,退款,过敏,急单,接口异常,无法回答",
        priority=98,
    ),
    BaselineKnowledgeEntry(
        sync_ref="store_info_guardrail",
        category=KnowledgeCategory.STORE_INFO.value,
        content_type=KnowledgeContentType.RULE.value,
        title="门店信息口径",
        content=(
            "顾客询问门店地址、营业时间、联系电话、停车和自提位置时，优先使用后台已维护的门店知识。"
            "如果当前知识库没有明确记录，不得编造地址或电话，应请顾客稍等并转人工确认。"
        ),
        keywords="门店,地址,营业时间,电话,自提,停车",
        priority=84,
    ),
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed Platform baseline knowledge")
    parser.add_argument(
        "--db-path",
        default=settings.DB_PATH,
        help="目标 SQLite 数据库路径，默认读取 DB_PATH。",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际写入基础知识；不加该参数时只做 dry-run。",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出机器可读 JSON，便于基础知识导入前后留档或部署脚本解析。",
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


def get_knowledge_columns(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("PRAGMA table_info(knowledge_base)").fetchall()
    return {str(row[1]) for row in rows}


def is_knowledge_schema_ready(conn: sqlite3.Connection) -> bool:
    columns = get_knowledge_columns(conn)
    return KNOWLEDGE_REQUIRED_COLUMNS.issubset(columns)


def count_active_rows(conn: sqlite3.Connection) -> int:
    cursor = conn.execute(
        "SELECT COUNT(id) FROM knowledge_base WHERE is_active = ?",
        (1,),
    )
    return int(cursor.fetchone()[0])


def get_existing_refs(conn: sqlite3.Connection) -> set[str]:
    cursor = conn.execute(
        "SELECT last_sync_ref FROM knowledge_base WHERE last_sync_source = ?",
        (BASELINE_SOURCE,),
    )
    return {str(row[0]) for row in cursor.fetchall()}


def insert_entry(conn: sqlite3.Connection, entry: BaselineKnowledgeEntry) -> None:
    conn.execute(
        "INSERT INTO knowledge_base ("
        "category, content_type, title, content, keywords, priority, is_active, "
        "last_sync_source, last_sync_ref, content_origin, created_by, updated_by, "
        "vector_sync_status"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            entry.category,
            entry.content_type,
            entry.title,
            entry.content,
            entry.keywords,
            entry.priority,
            1,
            BASELINE_SOURCE,
            entry.sync_ref,
            BASELINE_ORIGIN,
            BASELINE_ACTOR,
            BASELINE_ACTOR,
            VectorSyncStatus.PENDING.value,
        ),
    )


def seed_baseline_knowledge(
    db_path_value: str, *, should_apply: bool
) -> BaselineSeedReport:
    database_path = resolve_project_path(db_path_value)
    if not database_path.exists():
        return BaselineSeedReport(
            database_path=database_path,
            applied=should_apply,
            schema_ready=False,
            active_rows_before=0,
            active_rows_after=0,
            inserted_count=0,
            skipped_count=0,
            total_entries=len(BASELINE_ENTRIES),
        )

    try:
        with closing(sqlite3.connect(database_path)) as conn, conn:
            schema_ready = is_knowledge_schema_ready(conn)
            if not schema_ready:
                return BaselineSeedReport(
                    database_path=database_path,
                    applied=should_apply,
                    schema_ready=False,
                    active_rows_before=0,
                    active_rows_after=0,
                    inserted_count=0,
                    skipped_count=0,
                    total_entries=len(BASELINE_ENTRIES),
                )

            active_rows_before = count_active_rows(conn)
            existing_refs = get_existing_refs(conn)
            entries_to_insert = [
                entry
                for entry in BASELINE_ENTRIES
                if entry.sync_ref not in existing_refs
            ]

            if should_apply:
                for entry in entries_to_insert:
                    insert_entry(conn, entry)
                conn.commit()

            active_rows_after = count_active_rows(conn)
            inserted_count = len(entries_to_insert) if should_apply else 0
            skipped_count = len(BASELINE_ENTRIES) - len(entries_to_insert)
            return BaselineSeedReport(
                database_path=database_path,
                applied=should_apply,
                schema_ready=True,
                active_rows_before=active_rows_before,
                active_rows_after=active_rows_after,
                inserted_count=inserted_count,
                skipped_count=skipped_count,
                total_entries=len(BASELINE_ENTRIES),
            )
    except sqlite3.DatabaseError:
        return BaselineSeedReport(
            database_path=database_path,
            applied=should_apply,
            schema_ready=False,
            active_rows_before=0,
            active_rows_after=0,
            inserted_count=0,
            skipped_count=0,
            total_entries=len(BASELINE_ENTRIES),
        )


def print_report(report: BaselineSeedReport) -> None:
    mode = "apply" if report.applied else "dry-run"
    print("Platform baseline knowledge seed")
    print(f"mode={mode}")
    print(f"db_path={report.database_path}")
    print(f"schema_ready={report.schema_ready}")
    print(f"active_rows_before={report.active_rows_before}")
    print(f"active_rows_after={report.active_rows_after}")
    print(f"total_entries={report.total_entries}")
    print(f"inserted_count={report.inserted_count}")
    print(f"skipped_count={report.skipped_count}")
    if not report.schema_ready:
        print(f"action={MIGRATION_REQUIRED_ACTION}")
    elif report.all_entries_present:
        print(
            "action=baseline knowledge already exists; rebuild embeddings if cache is missing"
        )
    elif not report.applied:
        print(
            "action=review dry-run output, confirm target database path, then rerun with --apply"
        )
    elif report.inserted_count:
        print(
            "action=run scripts/rebuild_embeddings.py dry-run before applying embedding rebuild"
        )
    else:
        print("action=baseline knowledge unchanged; inspect seed refs before retrying")


def build_json_report(report: BaselineSeedReport) -> dict[str, object]:
    generated_at = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    return {
        "status": report.status,
        "metadata": {
            "generated_at": generated_at,
            "project_root": str(ROOT_DIR),
            "database_path": str(report.database_path),
            "baseline_source": BASELINE_SOURCE,
        },
        "report": report.to_dict(),
    }


def expand_output_path(output_path_value: str) -> Path:
    timestamp = datetime.now().strftime(OUTPUT_TIMESTAMP_FORMAT)
    expanded_value = output_path_value.replace(OUTPUT_TIMESTAMP_PLACEHOLDER, timestamp)
    return Path(expanded_value)


def write_json_report(output_path: Path, json_bytes: bytes) -> None:
    if output_path.exists():
        raise FileExistsError(f"报告文件已存在，拒绝覆盖: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(UTF8_BOM + json_bytes)


def ensure_output_path_available(output_path_value: str) -> Path:
    output_path = expand_output_path(output_path_value)
    if output_path.exists():
        raise FileExistsError(f"报告文件已存在，拒绝覆盖: {output_path}")
    return output_path


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.output and not args.json:
        print("--output 必须配合 --json 使用。", file=sys.stderr)
        return 2
    if args.output:
        try:
            output_path = ensure_output_path_available(args.output)
        except FileExistsError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    else:
        output_path = None
    report = seed_baseline_knowledge(args.db_path, should_apply=args.apply)
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
                return 2
    else:
        print_report(report)
    if not report.schema_ready:
        return 1
    if report.all_entries_present:
        return 0
    return 0 if report.applied and report.active_rows_after > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
