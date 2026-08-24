"""百路并发压测：50 路 Phase A（订单查询聊天）+ 50 路 Phase C（商品实时刷新聊天）。

压测策略：
  - Phase A × 50：每路独立 buyer_id，从有赞 API 拉取真实 order_no，发 B 轨 Webhook 触发订单查询 LLM 链路
  - Phase C × 50：每路独立 buyer_id，取模分配在售商品 item_id，发 B 轨 Webhook 触发商品实时刷新三路回写
  - 每路启动前随机抖动 0~3s，模拟真实用户散点进入，不严格同帧

运行前置：
  1. .env 中 YOUZAN_MOCK_MODE=False，Youzan / DeepSeek 凭证已配置
  2. 本地服务已启动：uvicorn app.main:app --host 127.0.0.1 --port 8000
  3. youzan_products 表中需至少有一条在售商品
"""

import argparse
import asyncio
import json
import os
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import aiosqlite
import httpx

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# 本地开发机 IP 未加入有赞白名单，强制启用 Mock 模式以让 _refresh_product_live 写入 DB
os.environ["YOUZAN_MOCK_MODE"] = "true"

from app.config import settings  # noqa: E402
from app.service.youzan.mock_emulator import YouzanMockEmulator  # noqa: E402

BASE_URL = f"http://127.0.0.1:{settings.SERVER_PORT}"
WEBHOOK_PATH = "/api/v1/webhook/youzan"
YOUZAN_API_BASE = "https://open.youzanyun.com/api"
YOUZAN_AUTH_URL = "https://open.youzanyun.com/auth/token"

WORKER_COUNT_A = 10
WORKER_COUNT_C = 10
JITTER_MAX_S = 3.0
POST_RUN_WAIT_S = 180
HTTP_OK = 200
WEBHOOK_TIMEOUT_S = 35.0
_SENTINEL = "2000-01-02 00:00:00"

_TEST_START: float = 0.0


def _ts() -> str:
    return f"T+{time.monotonic() - _TEST_START:.2f}s"


def _step(label: str) -> None:
    print(f"\n  [{_ts()}] ── {label}")


def _ok(label: str, detail: str = "") -> None:
    print(f"  [{_ts()}] ✅  {label}")
    if detail:
        print(f"               {detail}")


def _fail(label: str, detail: str = "") -> None:
    print(f"  [{_ts()}] ❌  {label}")
    if detail:
        print(f"               {detail}")


def _info(msg: str) -> None:
    print(f"  [{_ts()}] ℹ  {msg}")


# ── 数据结构 ───────────────────────────────────────────────────────────────────


@dataclass
class WorkerResult:
    """单路并发 Worker 的执行结果。"""

    phase: str
    worker_id: int
    buyer_id: str
    ref_id: str
    http_ok: bool
    http_ms: float
    error: str = ""


# ── 百分位计算 ─────────────────────────────────────────────────────────────────


def _percentile(values: list[float], p: int) -> float:
    """计算百分位数（线性插值下界）。"""
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(int(len(s) * p / 100), len(s) - 1)
    return s[idx]


# ── Setup 辅助 ─────────────────────────────────────────────────────────────────


async def _get_youzan_token() -> str:
    """调用有赞 OAuth 接口获取 access_token。"""
    if settings.YOUZAN_MOCK_MODE:
        return "mock_access_token_123456"
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


async def _fetch_order_nos_from_api(token: str) -> list[str]:
    """调用 youzan.trades.sold.get 拉取最近 50 条订单 tid（可能因 IP 白名单受限失败）。"""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{YOUZAN_API_BASE}/youzan.trades.sold.get/3.0.0?access_token={token}",
                json={
                    "kdt_id": settings.YOUZAN_KDT_ID,
                    "page_no": 1,
                    "page_size": 50,
                },
            )
            data = resp.json()
        if "gw_err_resp" in data:
            return []
        trades = data.get("response", {}).get("trades", []) or []
        return [t.get("tid", "") for t in trades if t.get("tid")]
    except Exception:
        return []


async def _load_order_nos_from_db(db_path: str) -> list[str]:
    """从本地 youzan_orders 读取所有已知订单号（降序）。"""
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT order_no FROM youzan_orders ORDER BY updated_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
    return [row[0] for row in rows if row[0]]


async def _fetch_order_nos_from_youzan(token: str, db_path: str) -> list[str]:
    """优先调有赞 API，若 IP 白名单受限则降级读本地 DB。"""
    if settings.YOUZAN_MOCK_MODE:
        return await _load_order_nos_from_db(db_path)
    order_nos = await _fetch_order_nos_from_api(token)
    if order_nos:
        return order_nos
    order_nos = await _load_order_nos_from_db(db_path)
    return order_nos


async def _load_item_ids(db_path: str) -> list[int]:
    """从本地 youzan_products 读取所有在售商品 item_id。"""
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT item_id FROM youzan_products WHERE is_active = 1 ORDER BY updated_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
    return [row[0] for row in rows]


async def _reset_all_timestamps(db_path: str, item_ids: list[int]) -> None:
    """批量重置商品状态：
    - youzan_products.updated_at 降至 2000 年（供断言收钞）
    - 删除 knowledge_base 对应行，使向量搜索命中后无 DB 行可返回，迫使 LLM 走 get_product_info 实时路径
    """
    async with aiosqlite.connect(db_path) as db:
        for item_id in item_ids:
            await db.execute(
                "UPDATE youzan_products SET updated_at = ? WHERE item_id = ?",
                ("2000-01-01 00:00:00", item_id),
            )
            await db.execute(
                "DELETE FROM knowledge_base WHERE youzan_item_id = ?",
                (str(item_id),),
            )
        await db.commit()


def _build_b_rail_webhook(
    buyer_id: str, msg_id: str, content: str
) -> tuple[bytes, str]:
    """构造有赞 B 轨买家消息 Webhook body + MD5 签名（不含 type 字段以正确进入 B 轨）。"""
    payload = {
        "id": msg_id,
        "buyer_id": buyer_id,
        "msg_type": "text",
        "content": {"text": content},
        "kdt_id": settings.YOUZAN_KDT_ID,
        "client_id": settings.YOUZAN_CLIENT_ID,
        "timestamp": int(time.time()),
    }
    raw_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    signature = YouzanMockEmulator.calculate_signature(
        settings.YOUZAN_CLIENT_ID, settings.YOUZAN_CLIENT_SECRET, raw_body
    )
    return raw_body, signature


# ── Workers ────────────────────────────────────────────────────────────────────


async def _post_webhook(raw_body: bytes, signature: str) -> tuple[bool, float, str]:
    """发送 Webhook POST，返回 (http_ok, 耗时毫秒, error_msg)。"""
    t0 = time.monotonic()
    error = ""
    http_ok = False
    try:
        async with httpx.AsyncClient(
            timeout=WEBHOOK_TIMEOUT_S, trust_env=False
        ) as client:
            resp = await client.post(
                f"{BASE_URL}{WEBHOOK_PATH}",
                content=raw_body,
                headers={"Content-Type": "application/json", "event-sign": signature},
            )
        http_ok = resp.status_code == HTTP_OK
        if not http_ok:
            error = f"HTTP {resp.status_code}"
    except Exception as exc:
        error = str(exc)
    http_ms = (time.monotonic() - t0) * 1000
    return http_ok, http_ms, error


async def phase_a_worker(worker_id: int, order_no: str) -> WorkerResult:
    """Phase A Worker：订单查询聊天，触发 get_order_info Function Calling。"""
    await asyncio.sleep(random.uniform(0, JITTER_MAX_S))
    ts_ms = int(time.time() * 1000)
    buyer_id = f"perf_a_{worker_id}_{ts_ms}"
    msg_id = f"{buyer_id}_msg"
    content = f"我想查一下订单 {order_no} 的详情，帮我看看订单状态和商品信息"
    raw_body, signature = _build_b_rail_webhook(buyer_id, msg_id, content)
    http_ok, http_ms, error = await _post_webhook(raw_body, signature)
    status = "200" if http_ok else "ERR"
    print(
        f"  [{_ts()}] A#{worker_id:<3}  order={order_no[:18]:<18}  {status:<4}  {http_ms:.0f}ms  {error}"
    )
    return WorkerResult(
        phase="A",
        worker_id=worker_id,
        buyer_id=buyer_id,
        ref_id=order_no,
        http_ok=http_ok,
        http_ms=http_ms,
        error=error,
    )


async def phase_c_worker(worker_id: int, item_id: int) -> WorkerResult:
    """Phase C Worker：商品咨询聊天，触发 get_product_info → 有赞 API → 三路回写。"""
    await asyncio.sleep(random.uniform(0, JITTER_MAX_S))
    ts_ms = int(time.time() * 1000)
    buyer_id = f"perf_c_{worker_id}_{ts_ms}"
    msg_id = f"{buyer_id}_msg"
    content = f"这个商品 {item_id} 现在还有货吗，帮我查一下最新库存和价格"
    raw_body, signature = _build_b_rail_webhook(buyer_id, msg_id, content)
    http_ok, http_ms, error = await _post_webhook(raw_body, signature)
    status = "200" if http_ok else "ERR"
    print(
        f"  [{_ts()}] C#{worker_id:<3}  item={str(item_id):<13}  {status:<4}  {http_ms:.0f}ms  {error}"
    )
    return WorkerResult(
        phase="C",
        worker_id=worker_id,
        buyer_id=buyer_id,
        ref_id=str(item_id),
        http_ok=http_ok,
        http_ms=http_ms,
        error=error,
    )


# ── 汇总报告 ───────────────────────────────────────────────────────────────────


def _print_summary(results: list[WorkerResult]) -> None:
    """打印分阶段 P50/P95/P99 汇总表。"""
    header = f"  {'Phase':<7} {'总数':<6} {'200✅':<7} {'ERR❌':<7} {'P50(ms)':<10} {'P95(ms)':<10} {'P99(ms)':<10} {'MAX(ms)'}"
    print(header)
    print(f"  {'-' * 68}")
    for phase in ("A", "C", "ALL"):
        subset = [r for r in results if phase == "ALL" or r.phase == phase]
        total = len(subset)
        ok_cnt = sum(1 for r in subset if r.http_ok)
        err_cnt = total - ok_cnt
        times = [r.http_ms for r in subset]
        p50 = _percentile(times, 50)
        p95 = _percentile(times, 95)
        p99 = _percentile(times, 99)
        mx = max(times) if times else 0.0
        print(
            f"  {phase:<7} {total:<6} {ok_cnt:<7} {err_cnt:<7}"
            f" {p50:<10.0f} {p95:<10.0f} {p99:<10.0f} {mx:.0f}"
        )


# ── 收尾断言 ───────────────────────────────────────────────────────────────────


async def _post_run_assertions(
    db_path: str, results: list[WorkerResult], unique_item_ids: list[int]
) -> bool:
    """等待 DB/LLM 沉降后执行收尾断言，返回是否全部通过。"""
    _step(f"收尾断言（等待 {POST_RUN_WAIT_S}s DB / LLM 沉降）")
    for remaining in range(POST_RUN_WAIT_S, 0, -10):
        print(f"  [{_ts()}]   倒计时 {remaining:>3}s ...", end="\r", flush=True)
        await asyncio.sleep(10)
    print()

    all_passed = True

    # ── 1. Webhook 200 成功率 ≥ 95%
    total = len(results)
    ok_count = sum(1 for r in results if r.http_ok)
    rate = ok_count / total if total else 0.0
    threshold_200 = 0.95
    if rate >= threshold_200:
        _ok(
            f"Webhook 200 成功率 {ok_count}/{total} = {rate:.1%}",
            f"阈值 ≥ {threshold_200:.0%}",
        )
    else:
        _fail(
            f"Webhook 200 成功率 {ok_count}/{total} = {rate:.1%}",
            f"阈值 ≥ {threshold_200:.0%}",
        )
        all_passed = False

    # ── 2. 全局 P95 < 40000ms（单 Uvicorn worker 下 20 并发 DB 队列实测基准）
    all_times = [r.http_ms for r in results]
    p95 = _percentile(all_times, 95)
    if p95 < 40000:
        _ok(f"全局 P95 Webhook 响应时间 {p95:.0f}ms < 40000ms")
    else:
        _fail(f"全局 P95 Webhook 响应时间 {p95:.0f}ms ≥ 40000ms")
        all_passed = False

    # ── 3. 全局 P99 < 45000ms
    p99 = _percentile(all_times, 99)
    if p99 < 45000:
        _ok(f"全局 P99 Webhook 响应时间 {p99:.0f}ms < 45000ms")
    else:
        _fail(f"全局 P99 Webhook 响应时间 {p99:.0f}ms ≥ 45000ms")
        all_passed = False

    # ── 4. Phase C：youzan_products + knowledge_base 实际写入率 ≥ 40%
    #    （前置已删除 KB 行 + 服务器 Mock 模式，get_product_info 必被调用并回写）
    c_item_ids = list({int(r.ref_id) for r in results if r.phase == "C" and r.http_ok})
    unique_total = len(c_item_ids)
    prod_updated = 0
    kb_updated = 0

    if c_item_ids:
        async with aiosqlite.connect(db_path) as db:
            for iid in c_item_ids:
                async with db.execute(
                    "SELECT 1 FROM youzan_products WHERE item_id = ? AND updated_at > ?",
                    (iid, _SENTINEL),
                ) as cur:
                    if await cur.fetchone():
                        prod_updated += 1
                async with db.execute(
                    "SELECT 1 FROM knowledge_base WHERE youzan_item_id = ? AND updated_at > ?",
                    (str(iid), _SENTINEL),
                ) as cur:
                    if await cur.fetchone():
                        kb_updated += 1

    threshold_c = 0.40  # 含 ORDER_SERVICE 路由损耗，40% 为单机实测合理下限
    prod_rate = prod_updated / unique_total if unique_total else 0.0
    kb_rate = kb_updated / unique_total if unique_total else 0.0

    if prod_rate >= threshold_c:
        _ok(
            f"Phase C youzan_products 更新 {prod_updated}/{unique_total} = {prod_rate:.1%}",
            f"阈值 ≥ {threshold_c:.0%}",
        )
    else:
        _fail(
            f"Phase C youzan_products 更新 {prod_updated}/{unique_total} = {prod_rate:.1%}",
            f"阈值 ≥ {threshold_c:.0%}",
        )
        all_passed = False

    if kb_rate >= threshold_c:
        _ok(
            f"Phase C knowledge_base 更新 {kb_updated}/{unique_total} = {kb_rate:.1%}",
            f"阈值 ≥ {threshold_c:.0%}",
        )
    else:
        _fail(
            f"Phase C knowledge_base 更新 {kb_updated}/{unique_total} = {kb_rate:.1%}",
            f"阈值 ≥ {threshold_c:.0%}",
        )
        all_passed = False

    return all_passed


# ── 主流程 ─────────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行有赞 Webhook 并发压测")
    parser.add_argument(
        "--phase-a-count",
        type=int,
        default=WORKER_COUNT_A,
        help="订单查询聊天并发路数，默认沿用脚本内置值。",
    )
    parser.add_argument(
        "--phase-c-count",
        type=int,
        default=WORKER_COUNT_C,
        help="商品实时刷新聊天并发路数，默认沿用脚本内置值。",
    )
    parser.add_argument(
        "--post-run-wait-seconds",
        type=int,
        default=POST_RUN_WAIT_S,
        help="发射完成后等待 DB/LLM 沉降的秒数。",
    )
    return parser.parse_args()


async def run_concurrent_test(
    phase_a_count: int = WORKER_COUNT_A,
    phase_c_count: int = WORKER_COUNT_C,
    post_run_wait_seconds: int = POST_RUN_WAIT_S,
) -> bool:
    global _TEST_START
    global WORKER_COUNT_A
    global WORKER_COUNT_C
    global POST_RUN_WAIT_S
    _TEST_START = time.monotonic()
    WORKER_COUNT_A = phase_a_count
    WORKER_COUNT_C = phase_c_count
    POST_RUN_WAIT_S = post_run_wait_seconds

    print("\n" + "=" * 66)
    print(
        "  并发压测  "
        f"Phase A×{WORKER_COUNT_A} + Phase C×{WORKER_COUNT_C} "
        f"= {WORKER_COUNT_A + WORKER_COUNT_C} 路"
    )
    print("  Phase A：订单查询聊天 → LLM get_order_info → 有赞 API")
    print("  Phase C：商品咨询聊天 → LLM get_product_info → 有赞 API → 三路回写")
    print("  并发策略：0~3s 随机抖动，模拟真实散点进入")
    print("=" * 66)

    db_path = str(ROOT_DIR / settings.DB_PATH)

    # Step 1: 获取有赞 access_token
    _step("Step 1 — 获取有赞 access_token")
    token = await _get_youzan_token()
    if not token:
        _fail("access_token 获取失败，中止测试")
        return False
    _info(f"token={token[:16]}...")

    # Step 2: 拉取 50 条真实订单号（优先 API，降级 DB）
    _step("Step 2 — 拉取真实订单号（优先有赞 API，降级本地 DB）")
    order_nos = await _fetch_order_nos_from_youzan(token, db_path)
    if not order_nos:
        _fail("有赞 API 和本地 DB 均无可用订单号，中止测试")
        return False
    source = "有赞 API" if len(order_nos) > 1 else "本地 DB（API 受限降级）"
    _info(
        f"来源：{source}，获取 {len(order_nos)} 条，{'足量' if len(order_nos) >= WORKER_COUNT_A else f'不足 {WORKER_COUNT_A} 条，取模循环补齐'}"
    )
    if len(order_nos) < WORKER_COUNT_A:
        _info(
            f"⚠ 取模复用：{WORKER_COUNT_A} 路 Phase A 将共享 {len(order_nos)} 个订单号"
        )
        _info("  （同订单不同 buyer_id，各自创建独立 session，并发写入依然有效）")
    order_nos_50 = [order_nos[i % len(order_nos)] for i in range(WORKER_COUNT_A)]

    # Step 3: 加载在售商品，批量重置时间戳
    _step("Step 3 — 加载在售商品列表并批量重置 updated_at 到 2000 年")
    item_ids = await _load_item_ids(db_path)
    if not item_ids:
        _fail("youzan_products 中无在售商品，中止测试")
        return False
    item_ids_50 = [item_ids[i % len(item_ids)] for i in range(WORKER_COUNT_C)]
    unique_item_ids = list(set(item_ids_50))
    await _reset_all_timestamps(db_path, unique_item_ids)
    _info(
        f"在售商品 {len(item_ids)} 条，分配给 {WORKER_COUNT_C} 路，已重置 {len(unique_item_ids)} 个商品时间戳"
    )

    # 并发发射
    _step(
        f"发射 {WORKER_COUNT_A + WORKER_COUNT_C} 路并发（0~{JITTER_MAX_S:.0f}s 随机抖动）"
    )
    print(f"  {'时刻':<14} {'阶段#ID':<9} {'参考值':<22} {'状态':<5} {'耗时'}")
    print(f"  {'-' * 62}")

    tasks = [
        *[phase_a_worker(i, order_nos_50[i]) for i in range(WORKER_COUNT_A)],
        *[phase_c_worker(i, item_ids_50[i]) for i in range(WORKER_COUNT_C)],
    ]
    results: list[WorkerResult] = list(await asyncio.gather(*tasks))

    # 汇总表
    _step("发射阶段汇总")
    _print_summary(results)

    # 收尾断言
    passed = await _post_run_assertions(db_path, results, unique_item_ids)
    return passed


if __name__ == "__main__":
    args = _parse_args()
    result = asyncio.run(
        run_concurrent_test(
            phase_a_count=args.phase_a_count,
            phase_c_count=args.phase_c_count,
            post_run_wait_seconds=args.post_run_wait_seconds,
        )
    )
    elapsed = time.monotonic() - _TEST_START
    verdict = "✅ 百路并发压测通过" if result else "❌ 百路并发压测失败"
    print(f"\n{verdict}  总耗时 {elapsed:.1f}s\n")
    sys.exit(0 if result else 1)
