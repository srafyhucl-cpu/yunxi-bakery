"""执行数据库隐私保留期清理，不处理备份文件。"""

import argparse
import asyncio
import json
import sys
from datetime import datetime

from app.database import db_session_scope
from app.repository.privacy_repo import PrivacyRepo
from app.service.privacy_lifecycle import PrivacyLifecycleService


async def run(db_path: str, now: datetime | None = None) -> dict[str, int]:
    async with db_session_scope(db_path) as db:
        service = PrivacyLifecycleService(PrivacyRepo(db))
        return await service.purge_expired(now=now)


def main() -> None:
    parser = argparse.ArgumentParser(description="按隐私保留策略清理数据库记录")
    parser.add_argument("--db", default="data/bot.db", help="SQLite 数据库路径")
    parser.add_argument(
        "--now", default="", help="测试用当前时间，格式 YYYY-MM-DD HH:MM:SS"
    )
    args = parser.parse_args()
    current = datetime.strptime(args.now, "%Y-%m-%d %H:%M:%S") if args.now else None
    result = asyncio.run(run(args.db, current))
    sys.stdout.write(
        json.dumps({"status": "ok", "deleted": result}, ensure_ascii=False) + "\n"
    )


if __name__ == "__main__":
    main()
