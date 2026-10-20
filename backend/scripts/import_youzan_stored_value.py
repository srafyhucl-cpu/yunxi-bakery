"""有赞储值余额期初导入脚本（CSV 合成数据，支持 dry-run / apply / rollback）。

把有赞门店存量储值余额以「期初导入」语义一次性入账本地 member_balance /
balance_ledger：dry-run 只创建批次并校验，apply 全有或全无入账，rollback 撤销
干净批次。全程不接触真实有赞 API 与生产库；真实门店导出以后可直接复用本脚本。

用法（先干跑再入账）：
    python scripts/import_youzan_stored_value.py --source data/youzan_stored_value.csv
    python scripts/import_youzan_stored_value.py --source data/youzan_stored_value.csv --apply
    python scripts/import_youzan_stored_value.py --source data/youzan_stored_value.csv --apply --json --output reports/youzan-sv-{timestamp}.json
    python scripts/import_youzan_stored_value.py --db-path data/bot.db --batch-id ysv_... --apply
    python scripts/import_youzan_stored_value.py --db-path data/bot.db --rollback-batch ysv_... --json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import settings  # noqa: E402
from app.database import close_db, init_db  # noqa: E402
from app.service.stored_value.importing import (  # noqa: E402
    StoredValueImportError,
    StoredValueImportService,
)
from scripts.preflight_production import resolve_project_path  # noqa: E402

OUTPUT_TIMESTAMP_PLACEHOLDER = "{timestamp}"
OUTPUT_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"
EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_USAGE = 2
BATCH_STATUS_APPLIED = "applied"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import Youzan stored value balance from CSV into local ledger"
    )
    parser.add_argument("--source", default=None, help="有赞储值余额 CSV 路径。")
    parser.add_argument(
        "--db-path",
        default=settings.DB_PATH,
        help="目标 SQLite 数据库路径，默认读取 DB_PATH。",
    )
    parser.add_argument(
        "--tenant-id", default="yunxi", help="客户主档租户 ID，默认 yunxi。"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="只创建/校验批次并输出报告，不写账务（默认行为）。",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="校验通过后实际入账；任一行失败整批回滚。",
    )
    parser.add_argument(
        "--batch-id", default=None, help="复用/指定既有批次，配合 dry-run 或 apply。"
    )
    parser.add_argument("--rollback-batch", default=None, help="回滚指定已入账批次。")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON。")
    parser.add_argument(
        "--output",
        default=None,
        help="配合 --json 使用，将报告写入指定文件，支持 {timestamp}。",
    )
    return parser.parse_args(argv)


async def run_import(
    *,
    db_path: str,
    tenant_id: str,
    source: str | None,
    batch_id: str | None,
    should_apply: bool,
) -> dict:
    """创建/校验批次并按需入账，返回报告 dict。"""
    if not source and not batch_id:
        raise StoredValueImportError("需要 --source 或 --batch-id 指定导入批次")
    resolved_db_path = resolve_project_path(db_path)
    conn = await init_db(str(resolved_db_path))
    try:
        service = StoredValueImportService(conn, tenant_id=tenant_id)
        target_id = batch_id
        if source:
            target_id = (await service.create_batch_from_csv(source))["id"]
        report = await service.validate_batch(str(target_id))
        if should_apply:
            report = await service.apply_batch(str(target_id))
        return report
    finally:
        await close_db(conn)


async def run_rollback(*, db_path: str, tenant_id: str, batch_id: str) -> dict:
    """回滚指定批次，返回报告 dict。"""
    resolved_db_path = resolve_project_path(db_path)
    conn = await init_db(str(resolved_db_path))
    try:
        service = StoredValueImportService(conn, tenant_id=tenant_id)
        return await service.rollback_batch(batch_id)
    finally:
        await close_db(conn)


def expand_output_path(output_path_value: str) -> Path:
    timestamp = datetime.now().strftime(OUTPUT_TIMESTAMP_FORMAT)
    return Path(output_path_value.replace(OUTPUT_TIMESTAMP_PLACEHOLDER, timestamp))


def ensure_output_path_available(output_path_value: str) -> Path:
    output_path = expand_output_path(output_path_value)
    if output_path.exists():
        raise FileExistsError(f"报告文件已存在，拒绝覆盖: {output_path}")
    return output_path


def build_json_payload(report: dict, *, status: str) -> dict:
    generated_at = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    return {
        "status": status,
        "metadata": {
            "generated_at": generated_at,
            "project_root": str(ROOT_DIR),
            "script": "import_youzan_stored_value",
        },
        "report": report,
    }


def print_report(report: dict, *, mode: str) -> None:
    print("Youzan stored value initial import")
    print(f"mode={mode}")
    print(f"batch_id={report['batch_id']}")
    print(f"status={report['status']}")
    print(f"scope={report['scope']}")
    print(f"source_file={report['source_file']}")
    print(f"total_rows={report['total_rows']}")
    print(f"valid_rows={report['valid_rows']}")
    print(f"invalid_rows={report['invalid_rows']}")
    print(f"conflict_rows={report['conflict_rows']}")
    print(f"applied_rows={report['applied_rows']}")
    print(f"expected_principal_fen={report['expected_principal_fen']}")
    print(f"expected_bonus_fen={report['expected_bonus_fen']}")
    print(f"expected_total_fen={report['expected_total_fen']}")
    print(f"applied_principal_fen={report['applied_principal_fen']}")
    print(f"applied_bonus_fen={report['applied_bonus_fen']}")
    print(f"applied_total_fen={report['applied_total_fen']}")
    print(f"principal_variance_fen={report['principal_variance_fen']}")
    print(f"bonus_variance_fen={report['bonus_variance_fen']}")
    print(f"variance_fen={report['variance_fen']}")
    if report["invalid_details"]:
        print(
            "invalid_details="
            + json.dumps(report["invalid_details"], ensure_ascii=False)
        )
    if report["conflict_details"]:
        print(
            "conflict_details="
            + json.dumps(report["conflict_details"], ensure_ascii=False)
        )


def report_exit_code(report: dict, *, should_apply: bool) -> int:
    """成功 0；校验失败 / apply 拒绝非 0。"""
    if report["status"] == "rolled_back":
        return EXIT_OK
    if int(report["invalid_rows"]) > 0:
        return EXIT_REFUSED
    if should_apply and report["status"] != BATCH_STATUS_APPLIED:
        return EXIT_REFUSED
    return EXIT_OK


def emit(
    payload: dict, report: dict, *, mode: str, as_json: bool, output: Path | None
) -> None:
    if as_json:
        json_bytes = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        )
        if output is None:
            sys.stdout.buffer.write(json_bytes)
        else:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(json_bytes)
        return
    print_report(report, mode=mode)


async def async_main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.output and not args.json:
        print("--output 必须配合 --json 使用。", file=sys.stderr)
        return EXIT_USAGE
    output_path = None
    if args.output:
        try:
            output_path = ensure_output_path_available(args.output)
        except FileExistsError as exc:
            print(str(exc), file=sys.stderr)
            return EXIT_USAGE

    rollback = args.rollback_batch
    if rollback and (args.source or args.apply):
        print("--rollback-batch 不能与 --source/--apply 同时使用。", file=sys.stderr)
        return EXIT_USAGE

    try:
        if rollback:
            report = await run_rollback(
                db_path=args.db_path, tenant_id=args.tenant_id, batch_id=rollback
            )
            mode = "rollback"
            exit_code = EXIT_OK
        else:
            report = await run_import(
                db_path=args.db_path,
                tenant_id=args.tenant_id,
                source=args.source,
                batch_id=args.batch_id,
                should_apply=args.apply,
            )
            mode = "apply" if args.apply else "dry-run"
            exit_code = report_exit_code(report, should_apply=args.apply)
    except StoredValueImportError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_REFUSED
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE

    payload_status = "ready" if exit_code == EXIT_OK else "failed"
    emit(
        build_json_payload(report, status=payload_status),
        report,
        mode=mode,
        as_json=args.json,
        output=output_path,
    )
    return exit_code


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
