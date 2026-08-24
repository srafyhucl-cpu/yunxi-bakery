"""Phase C 百并发压测：检测 SQLite WAL 死锁、P99 响应时间与错误率。

运行命令：
  locust -f locustfile.py --host http://127.0.0.1:8000 \\
         --users 100 --spawn-rate 10 --run-time 60s --headless \\
         --csv=reports/load_test

前置：pip install locust
"""

import json
import random
import sys
import time
import urllib.parse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

from locust import HttpUser, between, task  # noqa: E402

from app.config import settings  # noqa: E402
from app.service.youzan.mock_emulator import YouzanMockEmulator  # noqa: E402

# 测试商品 alias 样本（从 RAG 知识库随机取，避免每次 DB 查询）
_PRODUCT_QUERIES = [
    "年轮蛋糕多少钱",
    "提拉米苏怎么预订",
    "草莓蛋糕有吗",
    "坨坨和卷卷",
    "运费怎么算",
    "可以定制吗",
]

# 已知测试用 item_id 列表（从本地 DB 预加载，若空则使用 fallback）
_TEST_ITEM_IDS: list[int] = []


def _load_item_ids() -> list[int]:
    """启动时同步从本地 DB 取 item_id 样本（最多 20 个）。"""
    try:
        import sqlite3

        db_path = str(ROOT_DIR / settings.DB_PATH)
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT item_id FROM youzan_products WHERE is_active = 1 LIMIT 20"
            ).fetchall()
            return [row[0] for row in rows]
    except Exception:
        return [2745044534]


_TEST_ITEM_IDS = _load_item_ids()
_FALLBACK_ITEM_ID = 2745044534


def _make_chat_webhook(query: str) -> tuple[bytes, str]:
    """生成买家咨询 Webhook（B 轨，无 event_type）。"""
    msg_id = f"locust_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"
    raw_body, signature = YouzanMockEmulator.generate_webhook_message(
        buyer_id=f"buyer_{random.randint(10000, 99999)}",
        content_text=query,
        msg_id=msg_id,
        client_id=settings.YOUZAN_CLIENT_ID,
        client_secret=settings.YOUZAN_CLIENT_SECRET,
    )
    return raw_body, signature


def _make_item_webhook(item_id: int) -> tuple[bytes, str]:
    """生成商品系统事件 Webhook（A 轨，item_ItemUpdate）。"""
    msg_obj = {"item_id": item_id}
    msg_encoded = urllib.parse.quote(json.dumps(msg_obj, ensure_ascii=False))
    payload = {
        "id": str(int(time.time() * 1000)),
        "type": "item_ItemUpdate",
        "kdt_id": settings.YOUZAN_KDT_ID,
        "msg": msg_encoded,
        "client_id": settings.YOUZAN_CLIENT_ID,
        "timestamp": int(time.time()),
        "version": "1.0",
    }
    raw_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    signature = YouzanMockEmulator.calculate_signature(
        settings.YOUZAN_CLIENT_ID, settings.YOUZAN_CLIENT_SECRET, raw_body
    )
    return raw_body, signature


class YouzanWebhookUser(HttpUser):
    """模拟有赞 Webhook 高并发推送用户。"""

    wait_time = between(0.1, 0.5)

    @task(7)
    def send_chat_message(self) -> None:
        """模拟买家发送咨询消息（70% 权重）。"""
        query = random.choice(_PRODUCT_QUERIES)
        raw_body, signature = _make_chat_webhook(query)
        with self.client.post(
            "/api/v1/webhook/youzan",
            data=raw_body,
            headers={"Content-Type": "application/json", "event-sign": signature},
            catch_response=True,
            name="/api/v1/webhook/youzan [chat]",
        ) as response:
            if response.status_code != 200:
                response.failure(f"非 200: {response.status_code}")

    @task(3)
    def send_item_webhook(self) -> None:
        """模拟商品上下架事件推送（30% 权重）。"""
        item_id = random.choice(_TEST_ITEM_IDS) if _TEST_ITEM_IDS else _FALLBACK_ITEM_ID
        raw_body, signature = _make_item_webhook(item_id)
        with self.client.post(
            "/api/v1/webhook/youzan",
            data=raw_body,
            headers={"Content-Type": "application/json", "event-sign": signature},
            catch_response=True,
            name="/api/v1/webhook/youzan [item]",
        ) as response:
            if response.status_code != 200:
                response.failure(f"非 200: {response.status_code}")
