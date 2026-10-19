"""店员账号管理 CLI。

用法示例：
    python scripts/manage_staff.py create --name 小王 --phone 13800000000 --role cashier
    python scripts/manage_staff.py list
    python scripts/manage_staff.py disable --phone 13800000000
    python scripts/manage_staff.py reset-pin --phone 13800000000
"""

import argparse
import asyncio
import getpass
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import settings  # noqa: E402
from app.database import close_db, init_db  # noqa: E402
from app.repository.staff_repo import StaffAuditRepo, StaffRepo  # noqa: E402
from app.service.staff_auth import StaffAuthService  # noqa: E402


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage bakery staff accounts")
    parser.add_argument(
        "--db-path",
        default=settings.DB_PATH,
        help="目标 SQLite 数据库路径，默认读取 DB_PATH。",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="创建店员账号")
    create_parser.add_argument("--name", required=True, help="店员姓名")
    create_parser.add_argument("--phone", required=True, help="11 位手机号")
    create_parser.add_argument(
        "--role",
        required=True,
        choices=("cashier", "manager"),
        help="店员角色",
    )
    create_parser.add_argument("--pin", default=None, help="4-8 位数字 PIN")

    subparsers.add_parser("list", help="列出启用中的店员账号")

    disable_parser = subparsers.add_parser("disable", help="停用店员账号")
    disable_parser.add_argument("--phone", required=True, help="11 位手机号")

    reset_parser = subparsers.add_parser("reset-pin", help="重置店员 PIN")
    reset_parser.add_argument("--phone", required=True, help="11 位手机号")
    reset_parser.add_argument("--pin", default=None, help="4-8 位数字 PIN")
    return parser.parse_args(argv)


def _read_pin(pin: str | None) -> str:
    """未显式传入 PIN 时交互输入两次确认，绝不回显。"""
    if pin:
        return pin
    first = getpass.getpass("请输入 PIN（4-8 位数字）: ")
    second = getpass.getpass("请再次输入 PIN: ")
    if first != second:
        raise ValueError("两次输入的 PIN 不一致")
    return first


def _print_staff_rows(rows: list) -> None:
    if not rows:
        print("暂无启用中的店员账号")
        return
    for staff in rows:
        status = "启用" if staff.is_active else "停用"
        print(
            f"{staff.id}\t{staff.name}\t{staff.phone}\t"
            f"{staff.role}\t{status}\t{staff.last_login_at or '-'}"
        )


async def _run(args: argparse.Namespace) -> int:
    conn = await init_db(args.db_path)
    try:
        service = StaffAuthService(
            staff_repo=StaffRepo(conn),
            audit_repo=StaffAuditRepo(conn),
        )
        if args.command == "create":
            account = await service.create_staff(
                name=args.name,
                phone=args.phone,
                role=args.role,
                pin=_read_pin(args.pin),
            )
            await conn.commit()
            print(f"店员创建成功: {account.id}")
            return 0
        if args.command == "list":
            _print_staff_rows(await service.list_staff(active_only=True))
            return 0
        if args.command == "disable":
            account = await service.disable_staff(args.phone)
            await conn.commit()
            print(f"店员已停用: {account.id}")
            return 0
        if args.command == "reset-pin":
            account = await service.reset_pin(args.phone, _read_pin(args.pin))
            await conn.commit()
            print(f"PIN 已重置: {account.id}")
            return 0
        print(f"未知命令: {args.command}", file=sys.stderr)
        return 2
    finally:
        await close_db(conn)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (EOFError, KeyboardInterrupt):
        print("已取消", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
