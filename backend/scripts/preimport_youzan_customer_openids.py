"""有赞客户小程序 openid 预导入脚本。

按 customer_master 中的主手机号调用有赞 youzan.users.info.query 获取微信小程序 openid，
幂等写入 customer_identity_links（identity_type=miniapp_openid）。

用法（先干跑再全量）：
    python scripts/preimport_youzan_customer_openids.py --db-path data/bot.db --limit 5
    python scripts/preimport_youzan_customer_openids.py --db-path data/bot.db --limit 5 --apply
    python scripts/preimport_youzan_customer_openids.py --db-path data/bot.db --apply --json --output reports/youzan-openid-preimport-{timestamp}.json
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
from app.service.customer import CustomerMasterService  # noqa: E402
from app.service.youzan.client import YouzanClient  # noqa: E402
from scripts.preflight_production import (  # noqa: E402
    is_readable_sqlite_database,
    resolve_project_path,
)

OUTPUT_TIMESTAMP_PLACEHOLDER = "{timestamp}"
OUTPUT_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"
WECHAT_TYPE_MINIAPP = 2
IDENTITY_TYPE_MINIAPP_OPENID = "miniapp_openid"
MASKED_PHONE_TAIL = 4
MASKED_OPENID_HEAD = 8


@dataclass(frozen=True)
class PreimportReport:
    """openid 预导入脚本的执行报告。"""

    database_path: str
    tenant_id: str
    applied: bool
    limit: int
    total_phones: int
    queried: int
    matched_openid: int
    already_linked: int
    created: int
    not_found: int
    failed: int
    skipped_linked: int
    samples: list[dict[str, str]]

    @property
    def hit_rate(self) -> float:
        if self.queried <= 0:
            return 0.0
        return round(self.matched_openid / self.queried, 4)

    def to_dict(self) -> dict[str, object]:
        return {
            "database_path": self.database_path,
            "tenant_id": self.tenant_id,
            "mode": "apply" if self.applied else "dry-run",
            "limit": self.limit,
            "total_phones": self.total_phones,
            "queried": self.queried,
            "matched_openid": self.matched_openid,
            "already_linked": self.already_linked,
            "created": self.created,
            "not_found": self.not_found,
            "failed": self.failed,
            "skipped_linked": self.skipped_linked,
            "hit_rate": self.hit_rate,
            "samples": self.samples,
        }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preimport Youzan customer openids")
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
        help="最多处理多少条主手机号；0 表示全部（默认 0）。",
    )
    parser.add_argument(
        "--skip-linked",
        action="store_true",
        help="跳过已挂 miniapp_openid 身份的客户，避免重复计费查询。",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际写入 customer_identity_links；不加该参数时只查询不写入。",
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


def mask_openid(openid: str) -> str:
    """openid 脱敏：仅保留前 8 位。"""
    if len(openid) <= MASKED_OPENID_HEAD:
        return openid
    return f"{openid[:MASKED_OPENID_HEAD]}***"


def extract_miniapp_openid(payload: dict) -> str:
    """从 youzan.users.info.query 响应中提取微信小程序 openid。"""
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return ""
    user_list = data.get("user_list") or []
    for item in user_list:
        if not isinstance(item, dict):
            continue
        wechat_info = item.get("wechat_info") or {}
        if int(wechat_info.get("wechat_type") or 0) != WECHAT_TYPE_MINIAPP:
            continue
        platform_info = item.get("platform_info") or {}
        openid = str(platform_info.get("weixin_open_id") or "").strip()
        if openid:
            return openid
    return ""


def _resolve_database_path_value(db_path_value: str) -> str:
    if db_path_value == ":memory:":
        return ":memory:"
    return str(resolve_project_path(db_path_value))


async def run_preimport(
    *,
    db_path_value: str,
    tenant_id: str,
    limit: int,
    should_apply: bool,
    skip_linked: bool,
) -> PreimportReport:
    """执行 openid 预导入：读取主档手机号、查询有赞、幂等写入身份链接。"""
    resolved_db_path = _resolve_database_path_value(db_path_value)
    if resolved_db_path != ":memory:" and not is_readable_sqlite_database(
        Path(resolved_db_path)
    ):
        raise ValueError(f"数据库不可读或不是有效 SQLite: {resolved_db_path}")

    conn = await init_db(resolved_db_path)
    try:
        repo = CustomerMasterRepo(conn)
        service = CustomerMasterService(repo)
        client = YouzanClient()

        masters = await repo.list_masters_with_primary_phone(tenant_id)
        total_phones = len(masters)
        if limit > 0:
            masters = masters[:limit]

        queried = 0
        matched_openid = 0
        already_linked = 0
        created = 0
        not_found = 0
        failed = 0
        skipped_linked = 0
        samples: list[dict[str, str]] = []

        for master in masters:
            phone = master.primary_phone.strip()
            if not phone:
                continue
            if skip_linked:
                links = await repo.list_identity_links(master.id)
                if any(
                    link.identity_type == IDENTITY_TYPE_MINIAPP_OPENID for link in links
                ):
                    skipped_linked += 1
                    continue

            queried += 1
            try:
                payload = await client.query_user_info(phone)
                openid = extract_miniapp_openid(payload)
            except Exception as exc:
                failed += 1
                print(f"query failed phone={mask_phone(phone)}: {exc}", file=sys.stderr)
                continue

            if not openid:
                not_found += 1
                continue

            matched_openid += 1
            existing = await repo.get_identity_by_value(
                tenant_id, IDENTITY_TYPE_MINIAPP_OPENID, openid
            )
            if existing is not None:
                already_linked += 1
                continue

            if should_apply:
                link_payload = service.build_miniapp_openid_identity(
                    customer_id=master.id,
                    tenant_id=tenant_id,
                    openid=openid,
                    source_system="youzan",
                )
                await service.attach_identity(link_payload)
                created += 1
            else:
                created += 1

            if len(samples) < 5:
                samples.append(
                    {
                        "phone": mask_phone(phone),
                        "openid": mask_openid(openid),
                    }
                )

        return PreimportReport(
            database_path=resolved_db_path,
            tenant_id=tenant_id,
            applied=should_apply,
            limit=limit,
            total_phones=total_phones,
            queried=queried,
            matched_openid=matched_openid,
            already_linked=already_linked,
            created=created,
            not_found=not_found,
            failed=failed,
            skipped_linked=skipped_linked,
            samples=samples,
        )
    finally:
        await close_db(conn)


def print_report(report: PreimportReport) -> None:
    mode = "apply" if report.applied else "dry-run"
    print("Youzan customer openid preimport")
    print(f"mode={mode}")
    print(f"db_path={report.database_path}")
    print(f"tenant_id={report.tenant_id}")
    print(f"limit={report.limit}")
    print(f"total_phones={report.total_phones}")
    print(f"queried={report.queried}")
    print(f"matched_openid={report.matched_openid}")
    print(f"already_linked={report.already_linked}")
    print(f"created={report.created}")
    print(f"not_found={report.not_found}")
    print(f"failed={report.failed}")
    print(f"skipped_linked={report.skipped_linked}")
    print(f"hit_rate={report.hit_rate}")
    if report.samples:
        print("samples=" + json.dumps(report.samples, ensure_ascii=False))
    if report.applied:
        print("action=openid links applied")
    else:
        print("action=review dry-run output, then rerun with --apply")


def build_json_report(report: PreimportReport) -> dict[str, object]:
    generated_at = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    return {
        "status": "ready",
        "metadata": {
            "generated_at": generated_at,
            "project_root": str(ROOT_DIR),
            "script": "preimport_youzan_customer_openids",
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
        report = await run_preimport(
            db_path_value=args.db_path,
            tenant_id=args.tenant_id,
            limit=args.limit,
            should_apply=args.apply,
            skip_linked=args.skip_linked,
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
