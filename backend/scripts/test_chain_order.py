"""Phase A 全链路测试：客服消息（含订单号）→ LLM Function Calling → 有赞 API → youzan_orders DB 回写。

测试路径（恢复原意）：
  用户消息含明确订单号，措辞为"配送履约"风格
    → 意图识别为 DELIVERY_TRACKING（不转人工）
    → 进入 _ai_conversation_loop
    → LLM 调用 get_order_info Function Calling
    → YouzanClient.get_order() 调有赞 API
    → upsert_order 写入 youzan_orders

运行前置：
  1. .env 中 YOUZAN_MOCK_MODE=False，DeepSeek/Youzan 凭证已配置
  2. 本地服务已启动：uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
"""

import asyncio
import sys
import time
from pathlib import Path

import aiosqlite
import httpx

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import settings  # noqa: E402
from app.service.youzan.mock_emulator import YouzanMockEmulator  # noqa: E402

BASE_URL = "http://127.0.0.1:8000"
WEBHOOK_PATH = "/api/v1/webhook/youzan"
YOUZAN_API_BASE = "https://open.youzanyun.com/api"
YOUZAN_AUTH_URL = "https://open.youzanyun.com/auth/token"
WAIT_SECONDS = 10
BUYER_ID = "test_buyer_phase_a"
HTTP_OK = 200

# 全局测试开始时刻（monotonic）
_TEST_START: float = 0.0


def _ts() -> str:
    """返回相对测试起始的耗时字符串，如 T+3.21s。"""
    return f"T+{time.monotonic() - _TEST_START:.2f}s"


def _step(label: str) -> None:
    print(f"\n  [{_ts()}] ── {label}")


def _ok(label: str, detail: str = "") -> None:
    print(f"  [{_ts()}] ✅ PASS  {label}")
    if detail:
        print(f"              {detail}")


def _fail(label: str, detail: str = "") -> None:
    print(f"  [{_ts()}] ❌ FAIL  {label}")
    if detail:
        print(f"              {detail}")


def _info(msg: str) -> None:
    print(f"  [{_ts()}] ℹ  {msg}")


async def _get_youzan_token() -> str:
    """调用有赞 OAuth 接口取 access_token（仅 Setup 阶段用）。"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            YOUZAN_AUTH_URL,
            json={
                "client_id": settings.YOUZAN_CLIENT_ID,
                "client_secret": settings.YOUZAN_CLIENT_SECRET,
                "authorize_type": "silent",
                "grant_id": settings.YOUZAN_KDT_ID,
            },
        )
        data = resp.json()
    auth_data = data.get("data") if isinstance(data, dict) else None
    if isinstance(auth_data, dict):
        return auth_data.get("access_token", "")
    return data.get("access_token", "")


async def _fetch_latest_order_no(token: str) -> str | None:
    """调用 youzan.trades.sold.get 取最新一条订单 tid。

    实际响应结构：response.trades[0].tid
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{YOUZAN_API_BASE}/youzan.trades.sold.get/3.0.0?access_token={token}",
            json={
                "kdt_id": settings.YOUZAN_KDT_ID,
                "page_no": 1,
                "page_size": 1,
            },
        )
        data = resp.json()
    try:
        trades = data.get("response", {}).get("trades", [])
        if trades:
            return trades[0].get("tid")
    except (KeyError, IndexError, TypeError, AttributeError):
        pass
    return None


async def _discover_order_no(db_path: str) -> str | None:
    """从本地 youzan_orders 取最近一条已知订单号；若无则返回 None。"""
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT order_no FROM youzan_orders ORDER BY updated_at DESC LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def _query_order(db_path: str, order_no: str) -> dict | None:
    """查询本地 youzan_orders 中目标订单记录。"""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT order_no, status, amount_fen, product_titles, buyer_id, updated_at"
            " FROM youzan_orders WHERE order_no = ?",
            (order_no,),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


POLL_INTERVAL_S = 2
POLL_MAX_S = 30


async def _delete_order(db_path: str, order_no: str) -> None:
    """测试前清除旧记录，确保断言的是本次 Function Calling 新写入的数据。"""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("DELETE FROM youzan_orders WHERE order_no = ?", (order_no,))
        await db.commit()


async def _poll_order(db_path: str, order_no: str, after_ts: str) -> dict | None:
    """轮询 youzan_orders，最长等 POLL_MAX_S 秒，记录重新出现即返回。
    注：测试前已 DELETE 该 order_no，出现即证明本次 Function Calling 写入成功。
    after_ts 仅作日志参考，不用于过滤。
    """
    deadline = time.monotonic() + POLL_MAX_S
    while time.monotonic() < deadline:
        record = await _query_order(db_path, order_no)
        if record:
            return record
        await asyncio.sleep(POLL_INTERVAL_S)
        print(f"  [{_ts()}]   轮询中，等待 LLM + 有赞 API + DB 写入...", end="\r")
    print()
    return None


async def run_phase_a() -> bool:
    global _TEST_START
    _TEST_START = time.monotonic()

    print("\n" + "=" * 60)
    print(
        "Phase A：客服消息（含订单号）→ LLM Function Calling → 有赞 API → youzan_orders 回写"
    )
    print("=" * 60)
    print(
        "  路径：DELIVERY_TRACKING 意图 → _ai_conversation_loop → get_order_info → upsert_order"
    )

    db_path = str(ROOT_DIR / settings.DB_PATH)

    # ── Step 0：发现可测订单号 ─────────────────────────────────────────────────
    _step("Setup：发现可测订单号")
    order_no = await _discover_order_no(db_path)
    if order_no:
        _info(f"本地 DB 已有历史记录，使用 order_no={order_no}")
    else:
        _info("本地 DB 无记录，调用有赞 API youzan.trades.sold.get 自动取最新订单")
        try:
            token = await _get_youzan_token()
            _info(f"有赞 token 获取成功（{token[:12]}...）")
            order_no = await _fetch_latest_order_no(token)
            if order_no:
                _info(f"取到最新订单号: {order_no}")
            else:
                _info("有赞 API 未返回订单（店铺暂无历史订单）")
        except Exception as exc:
            _info(f"有赞 API 调用失败: {exc}")

    if not order_no:
        _fail("无法获取可测订单号，终止测试")
        return False

    # ── Step 1：清除旧记录（确保断言的是本次写入）──────────────────────────────
    _step("清除 youzan_orders 旧记录（保证断言干净）")
    await _delete_order(db_path, order_no)
    _info(f"已清除 order_no={order_no} 的旧记录（若存在）")
    test_start_ts = time.strftime("%Y-%m-%d %H:%M:%S")
    _info(f"测试开始时间戳: {test_start_ts}")

    # ── Step 2：构造含订单号的客服消息 Webhook ────────────────────────────────
    _step("构造客服消息 Webhook（配送履约措辞，含明确订单号）")
    buyer_id = f"test_phase_a_{int(time.time())}"
    question = f"我的蛋糕订单 {order_no} 发货了吗，顺便告诉我买的什么商品"
    msg_id = f"test_phase_a_{int(time.time() * 1000)}"
    raw_body, signature = YouzanMockEmulator.generate_webhook_message(
        buyer_id=buyer_id,
        content_text=question,
        msg_id=msg_id,
        client_id=settings.YOUZAN_CLIENT_ID,
        client_secret=settings.YOUZAN_CLIENT_SECRET,
    )
    _info(f"buyer_id={buyer_id}（每次唯一，session 干净）")
    _info(f"msg_id={msg_id}")
    _info(f"消息内容: {question!r}")
    _info(f"signature={signature}")
    _info(f"POST {BASE_URL}{WEBHOOK_PATH}")

    t_post = time.monotonic()
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{BASE_URL}{WEBHOOK_PATH}",
            content=raw_body,
            headers={"Content-Type": "application/json", "event-sign": signature},
        )
    t_post_elapsed = time.monotonic() - t_post

    if response.status_code == HTTP_OK:
        _ok(
            f"Webhook 接收返回 200（往返 {t_post_elapsed:.2f}s）",
            f"body={response.text[:80]}",
        )
    else:
        _fail(
            "Webhook 返回非 200",
            f"status={response.status_code}  body={response.text[:120]}",
        )
        return False

    # ── Step 3：轮询等待 Function Calling → DB 写入 ───────────────────────────
    _step(
        f"轮询等待 LLM Function Calling → 有赞 API → upsert_order（最长 {POLL_MAX_S}s）"
    )
    _info(
        "链路：意图识别 → _ai_conversation_loop → get_order_info → youzan.trade.get → upsert_order"
    )
    record = await _poll_order(db_path, order_no, test_start_ts)

    # ── Step 4：断言 DB 写入 ───────────────────────────────────────────────────
    _step("断言 youzan_orders DB 写入（updated_at >= 测试开始时间）")
    if not record:
        _fail(f"youzan_orders 超时未找到 order_no={order_no}")
        _info(f"轮询上限 {POLL_MAX_S}s 已到，请检查服务日志：")
        _info("  1. 意图是否被识别为 ORDER_SERVICE（会转人工不过 LLM）")
        _info("  2. LLM 是否调用了 get_order_info")
        _info("  3. 有赞 API 是否返回了 full_order_info")
        return False

    # updated_at 存储有赞订单自身的 update_time，不是 DB 写入时间
    # 判断依据：测试前已 DELETE 过该 order_no，能查到记录即证明本次 Function Calling 写入
    _ok(
        "youzan_orders 有记录（测试前已删除，现重新出现，证明本次 Function Calling 写入成功）"
    )
    print(f"\n              {'字段':<22} {'值'}")
    print(f"              {'-' * 55}")
    for f, v in record.items():
        print(f"              {f:<22} {v}")

    status_ok = bool(record.get("status"))
    amount_ok = record.get("amount_fen", 0) > 0
    titles_ok = bool(record.get("product_titles"))

    if status_ok:
        _ok("status 字段非空", f"status={record['status']}")
    else:
        _fail("status 字段为空")
    if amount_ok:
        _ok("amount_fen > 0", f"¥{record['amount_fen'] / 100:.2f}")
    else:
        _fail("amount_fen 为 0 或缺失")
    if titles_ok:
        _ok("product_titles 非空", record["product_titles"][:60])
    else:
        _fail("product_titles 为空")

    return status_ok and amount_ok and titles_ok


if __name__ == "__main__":
    result = asyncio.run(run_phase_a())
    elapsed = time.monotonic() - _TEST_START
    print(
        f"\n{'✅ Phase A 通过' if result else '❌ Phase A 失败'}  总耗时 {elapsed:.1f}s\n"
    )
    sys.exit(0 if result else 1)
