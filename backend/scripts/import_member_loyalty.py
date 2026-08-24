"""会员积分/优惠券/会员卡全量导入脚本。

按 customer_master 主手机号调用有赞会员账务域 API 拉取积分/优惠券/会员卡，
幂等写入 member_balance / coupon_inventory；points_ledger 由 Webhook 增量维护。

用法（先干跑再全量）：
    python scripts/import_member_loyalty.py --db-path data/bot.db --limit 5
    python scripts/import_member_loyalty.py --db-path data/bot.db --limit 5 --apply
    python scripts/import_member_loyalty.py --db-path data/bot.db --apply --json --output reports/member-loyalty-import-{timestamp}.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import settings  # noqa: E402
from app.database import close_db, init_db  # noqa: E402
from app.repository.customer_master_repo import CustomerMasterRepo  # noqa: E402
from app.service.member_loyalty import MemberLoyaltyImportService  # noqa: E402
from app.service.youzan.client import YouzanClient  # noqa: E402
from scripts.preflight_production import (  # noqa: E402
    is_readable_sqlite_database,
    resolve_project_path,
)

OUTPUT_TIMESTAMP_PLACEHOLDER = "{timestamp}"
OUTPUT_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"
MASKED_PHONE_TAIL = 4


@dataclass(frozen=True)
class LoyaltyImportReport:
    """会员账务导入脚本的执行报告。"""

    database_path: str
    tenant_id: str
    applied: bool
    limit: int
    total_customers: int
    queried: int
    points_customers: int
    cards_found: int
    coupons_found: int
    failed: int
    samples: list[dict[str, object]]

    def to_dict(self) -> dict[str, object]:
        return {
            "database_path": self.database_path,
            "tenant_id": self.tenant_id,
            "mode": "apply" if self.applied else "dry-run",
            "limit": self.limit,
            "total_customers": self.total_customers,
            "queried": self.queried,
            "points_customers": self.points_customers,
            "cards_found": self.cards_found,
            "coupons_found": self.coupons_found,
            "failed": self.failed,
            "samples": self.samples,
        }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import Youzan member loyalty accounting data"
    )
    parser.add_argument(
        "--db-path",
        default=settings.DB_PATH,
        help="目标 SQLite 数据库路径，默认读取 DB_PATH。",
    )
    parser.add_argument(
        "--tenant-id",
        default="yunxi",
        help="customer 主档租户 ID，默认 yunxi。",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="最多处理多少个客户；0 表示全部（默认 0）。",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际写入账务表；不加该参数时只查询不写入。",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出机器可读 JSON。",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="配合 --json 使用，将报告写入指定文件，支持 {timestamp}。",
    )
    return parser.parse_args(argv)


def expand_output_path(output_path_value: str) -> Path:
    timestamp = datetime.now().strftime(OUTPUT_TIMESTAMP_FORMAT)
    expanded_value = output_path_value.replace(OUTPUT_TIMESTAMP_PLACEHOLDER, timestamp)
    return Path(expanded_value)


def ensure_output_path_available(output_path_value: str) -> Path:
    output_path = expand_output_path(output_path_value)
    if output_path.exists():
        raise FileExistsError(f"报告文件已存在，拒绝覆盖: {output_path}")
    return output_path


def mask_phone(phone: str) -> str:
    """手机号脱敏：保留前 3 位与后 4 位。"""
    if len(phone) <= MASKED_PHONE_TAIL:
        return phone
    return f"{phone[:3]}****{phone[-MASKED_PHONE_TAIL:]}"


async def run_import(
    db_path_value: str,
    tenant_id: str,
    limit: int,
    should_apply: bool,
) -> LoyaltyImportReport:
    """执行会员账务全量导入，返回汇总报告。"""
    resolved_db_path = resolve_project_path(db_path_value)
    if not resolved_db_path.exists():
        raise FileNotFoundError(f"数据库不存在: {resolved_db_path}")
    if not is_readable_sqlite_database(resolved_db_path):
        raise ValueError(f"数据库不可读或不是 SQLite: {resolved_db_path}")

    conn = await init_db(str(resolved_db_path))
    try:
        customer_repo = CustomerMasterRepo(conn)
        masters = await customer_repo.list_masters_with_primary_phone(tenant_id)
        if limit > 0:
            masters = masters[:limit]

        client = YouzanClient()
        service = MemberLoyaltyImportService(conn, client, tenant_id=tenant_id)
        total_customers = len(masters)
        queried = 0
        points_customers = 0
        cards_found = 0
        coupons_found = 0
        failed = 0
        samples: list[dict[str, object]] = []
        for master in masters:
            queried += 1
            stats = await service.import_one(
                master.primary_phone,
                customer_id=master.id,
                should_apply=should_apply,
            )
            if stats["errors"]:
                failed += 1
            if stats["points_total"] > 0:
                points_customers += 1
            cards_found += stats["cards"]
            coupons_found += stats["coupons"]
            if len(samples) < 5:
                samples.append(
                    {
                        "phone": mask_phone(master.primary_phone),
                        "points_total": stats["points_total"],
                        "cards": stats["cards"],
                        "coupons": stats["coupons"],
                        "errors": stats["errors"],
                    }
                )
        await client.close()
        return LoyaltyImportReport(
            database_path=str(resolved_db_path),
            tenant_id=tenant_id,
            applied=should_apply,
            limit=limit,
            total_customers=total_customers,
            queried=queried,
            points_customers=points_customers,
            cards_found=cards_found,
            coupons_found=coupons_found,
            failed=failed,
            samples=samples,
        )
    finally:
        await close_db(conn)


def print_report(report: LoyaltyImportReport) -> None:
    mode = "apply" if report.applied else "dry-run"
    print("Youzan member loyalty import")
    print(f"mode={mode}")
    print(f"db_path={report.database_path}")
    print(f"tenant_id={report.tenant_id}")
    print(f"limit={report.limit}")
    print(f"total_customers={report.total_customers}")
    print(f"queried={report.queried}")
    print(f"points_customers={report.points_customers}")
    print(f"cards_found={report.cards_found}")
    print(f"coupons_found={report.coupons_found}")
    print(f"failed={report.failed}")
    if report.samples:
        print("samples=" + json.dumps(report.samples, ensure_ascii=False))
    if report.applied:
        print("action=loyalty data applied")
    else:
        print("action=review dry-run output, then rerun with --apply")


def build_json_report(report: LoyaltyImportReport) -> dict[str, object]:
    generated_at = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    return {
        "status": "ready",
        "metadata": {
            "generated_at": generated_at,
            "project_root": str(ROOT_DIR),
            "script": "import_member_loyalty",
        },
        "report": report.to_dict(),
    }


def write_json_report(output_path: Path, json_bytes: bytes) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(json_bytes)


async def async_main(argv: list[str] | None = None) -> int:
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

    try:
        report = await run_import(
            db_path_value=args.db_path,
            tenant_id=args.tenant_id,
            limit=args.limit,
            should_apply=args.apply,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.json:
        json_bytes = (
            json.dumps(build_json_report(report), ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        if output_path is None:
            sys.stdout.buffer.write(json_bytes)
        else:
            write_json_report(output_path, json_bytes)
    else:
        print_report(report)
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
