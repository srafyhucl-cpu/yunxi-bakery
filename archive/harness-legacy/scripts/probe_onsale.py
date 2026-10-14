"""探测有赞在售商品接口原始响应（一次性诊断脚本，用完即删）。"""

import asyncio
import json

import aiosqlite
import httpx

from app.config import settings
from app.repository.config_repo import ConfigRepo
from app.service.youzan.client import YouzanClient


async def main() -> None:
    async with aiosqlite.connect(settings.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        repo = ConfigRepo(db)
        client = YouzanClient(config_repo=repo)
        token = await client.get_token()
        async with httpx.AsyncClient(timeout=15.0, trust_env=False) as http:
            resp = await http.post(
                f"https://open.youzanyun.com/api/youzan.items.onsale.get/3.0.1"
                f"?access_token={token}",
                json={"kdt_id": settings.YOUZAN_KDT_ID, "page_no": 1, "page_size": 5},
            )
            raw = resp.json()
    print("顶层 keys:", list(raw.keys()))
    inner = raw.get("response") or raw.get("data") or {}
    if isinstance(inner, dict):
        print("response keys:", list(inner.keys()))
        items = inner.get("items") or inner.get("list") or []
        print("items 条数:", len(items))
        if items:
            print("第一条 keys:", list(items[0].keys()))
            print("第一条:", json.dumps(items[0], ensure_ascii=False, indent=2)[:500])
    else:
        print("完整响应:", json.dumps(raw, ensure_ascii=False, indent=2)[:1000])


if __name__ == "__main__":
    asyncio.run(main())
