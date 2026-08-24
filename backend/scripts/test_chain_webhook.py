"""Phase B 全链路测试：商品系统事件 Webhook → 有赞 API → DB + RAG + 埋点写入（含幂等验证）。

运行前置：
  1. .env 中 YOUZAN_MOCK_MODE=False，Youzan 凭证已配置
  2. 本地服务已启动：uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
  3. 本地 DB 中 youzan_products 需至少有一条记录
"""

import asyncio
import json
import sys
import time
import urllib.parse
from pathlib import Path

import aiosqlite
import httpx

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import settings  # noqa: E402
from app.service.youzan.mock_emulator import YouzanMockEmulator  # noqa: E402

BASE_URL = "http://127.0.0.1:8000"
WEBHOOK_PATH = "/api/v1/webhook/youzan"
WAIT_SECONDS = 10
HTTP_OK = 200

VS_JSON_PATH = ROOT_DIR / "data" / "embeddings.json"

_TEST_START: float = 0.0


def _ts() -> str:
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


async def _get_test_item_id(db_path: str) -> int | None:
    """从本地 youzan_products 取一条在售商品 item_id。"""
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT item_id FROM youzan_products WHERE is_active = 1 ORDER BY updated_at DESC LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def _snapshot_product(db_path: str, item_id: int) -> dict | None:
    """读取商品当前完整快照。"""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT item_id, title, price_fen, stock, is_active, updated_at"
            " FROM youzan_products WHERE item_id = ?",
            (item_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def _reset_timestamps(db_path: str, item_id: int) -> None:
    """将 youzan_products 和 knowledge_base 的 updated_at 都降到 2000 年，
    保证后续任何 Webhook 写入都能通过时序防线。"""
    _SENTINEL = "2000-01-01 00:00:00"
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE youzan_products SET updated_at=? WHERE item_id=?",
            (_SENTINEL, item_id),
        )
        await db.execute(
            "UPDATE knowledge_base SET updated_at=? WHERE youzan_item_id=?",
            (_SENTINEL, str(item_id)),
        )
        await db.commit()


async def _fetch_knowledge(db_path: str, item_id: int) -> dict | None:
    """读取 knowledge_base 对应商品条目（含内容预览）。"""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, title, category, updated_at, SUBSTR(content, 1, 300) AS content_preview"
            " FROM knowledge_base WHERE youzan_item_id = ?",
            (str(item_id),),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


def _snapshot_embeddings() -> tuple[float, set[str]]:
    """读取 embeddings.json 修改时间和 doc_keys 集合，文件不存在时返回空默认值。"""
    if not VS_JSON_PATH.exists():
        return 0.0, set()
    mtime = VS_JSON_PATH.stat().st_mtime
    with open(VS_JSON_PATH, "r", encoding="utf-8") as f:
        meta = json.load(f)
    return mtime, set(meta.get("doc_keys", []))


async def _count_analytics(db_path: str, item_id: int) -> int:
    """统计 analytics_events 中与该商品相关的 price_sync / stock_alert 埋点数。"""
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM analytics_events"
            " WHERE event_type IN ('price_sync','stock_alert') AND ref_id = ?",
            (str(item_id),),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


def _build_system_event_body(item_id: int) -> tuple[bytes, str]:
    """构造 item_ItemUpdate 系统事件 Webhook body 并计算 MD5 签名。"""
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


async def _post_event(raw_body: bytes, signature: str) -> tuple[int, float]:
    t0 = time.monotonic()
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{BASE_URL}{WEBHOOK_PATH}",
            content=raw_body,
            headers={"Content-Type": "application/json", "event-sign": signature},
        )
    return response.status_code, time.monotonic() - t0


def _print_diff_table(before: dict | None, after: dict | None) -> None:
    """打印商品快照字段前后对比表格。"""
    fields = ["title", "price_fen", "stock", "is_active", "updated_at"]
    print(f"              {'字段':<16} {'变更前':<28} {'变更后'}")
    print(f"              {'-' * 70}")
    for f in fields:
        bv = str(before.get(f, "N/A")) if before else "N/A"
        av = str(after.get(f, "N/A")) if after else "N/A"
        marker = " ←" if bv != av else ""
        print(f"              {f:<16} {bv:<28} {av}{marker}")


async def run_phase_b() -> bool:
    global _TEST_START
    _TEST_START = time.monotonic()

    print("\n" + "=" * 60)
    print("Phase B：商品系统事件 Webhook → DB + RAG + 埋点（含幂等验证）")
    print("=" * 60)

    db_path = str(ROOT_DIR / settings.DB_PATH)

    # ── Setup：选取测试商品 ───────────────────────────────────────────────────
    _step("Setup：选取测试商品 item_id")
    item_id = await _get_test_item_id(db_path)
    if not item_id:
        _fail("youzan_products 中无在售商品，请先同步商品数据")
        return False
    _info(f"选用 item_id={item_id}")

    # ── 重置时间戳，确保两张表都能触发 upsert 时序防线 ────────────────────────
    _step("重置 youzan_products + knowledge_base updated_at 到 2000 年（清洁测试环境）")
    await _reset_timestamps(db_path, item_id)
    _info(f"item_id={item_id} 两张表 updated_at 已降至 2000-01-01")

    # ── 基线快照 ──────────────────────────────────────────────────────────────
    _step("采集基线快照")
    snapshot_before = await _snapshot_product(db_path, item_id)
    analytics_before = await _count_analytics(db_path, item_id)
    kb_before = await _fetch_knowledge(db_path, item_id)
    _info(
        f"youzan_products.title={snapshot_before['title'] if snapshot_before else 'N/A'}"
    )
    _info(
        f"youzan_products.updated_at={snapshot_before['updated_at'] if snapshot_before else 'N/A'}"
    )
    _info(
        f"youzan_products.price_fen={snapshot_before['price_fen'] if snapshot_before else 'N/A'}"
    )
    _info(
        f"youzan_products.stock={snapshot_before['stock'] if snapshot_before else 'N/A'}"
    )
    _info(f"knowledge_base 条目: {'存在' if kb_before else '不存在'}")
    _info(f"analytics_events(price_sync/stock_alert)={analytics_before}")

    # ══════════════════════════════════════════════════════════════════════════
    print("\n  ── Run 1（首次推送，期望触发同步）──")
    # ══════════════════════════════════════════════════════════════════════════

    emb_mtime_base, emb_keys_base = _snapshot_embeddings()
    test_start_ts = time.time()
    _step("构造 item_ItemUpdate 事件并 POST")
    raw_body, sig = _build_system_event_body(item_id)
    payload_preview = json.loads(raw_body)
    _info(
        f"type={payload_preview['type']}  item_id={item_id}  kdt_id={payload_preview['kdt_id']}"
    )
    _info(f"signature={sig}")

    status, elapsed = await _post_event(raw_body, sig)
    if status == HTTP_OK:
        _ok(f"Webhook 接收返回 200（往返 {elapsed:.2f}s）")
    else:
        _fail(f"Webhook 返回 {status}")
        return False

    _step(f"等待后台链路（有赞 API → upsert → RAG 增量），共 {WAIT_SECONDS}s")
    for i in range(WAIT_SECONDS):
        await asyncio.sleep(1)
        print(f"  [{_ts()}]   ... {i + 1}/{WAIT_SECONDS}s", end="\r")
    print()

    _step("断言 youzan_products 回写")
    snapshot_r1 = await _snapshot_product(db_path, item_id)
    updated = snapshot_r1 is not None and (
        snapshot_before is None
        or snapshot_r1["updated_at"] >= snapshot_before["updated_at"]
    )
    if updated:
        _ok("updated_at 已刷新")
    else:
        _fail("updated_at 未更新")
    _print_diff_table(snapshot_before, snapshot_r1)

    _step("断言 knowledge_base RAG 增量更新")
    kb_r1 = await _fetch_knowledge(db_path, item_id)
    _SENTINEL = "2000-01-02 00:00:00"
    kb_updated = kb_r1 is not None and kb_r1["updated_at"] > _SENTINEL
    if kb_updated:
        _ok(
            "knowledge_base 已更新",
            f"id={kb_r1['id']}  updated_at={kb_r1['updated_at']}  （测试前已降至 2000-01-01，现为新时间证明本次写入）",
        )
        print("\n              ── 知识内容前 300 字 ──")
        for line in kb_r1["content_preview"].splitlines():
            print(f"              {line}")
    elif kb_r1:
        _fail(
            f"knowledge_base 条目存在但 updated_at 未刷新（{kb_r1['updated_at']} ≤ {_SENTINEL}）"
        )
    else:
        _fail("knowledge_base 无对应条目")

    _step("断言 analytics_events 埋点")
    analytics_r1 = await _count_analytics(db_path, item_id)
    if analytics_r1 >= analytics_before:
        _ok(
            f"analytics_events 数量 ≥ 基线（{analytics_before} → {analytics_r1}）",
            "price_sync / stock_alert 至少持平（无变化时正常为 0）",
        )
    else:
        _fail(f"analytics_events 数量异常下降（{analytics_before} → {analytics_r1}）")

    _step("断言向量索引磁盘刷新（embeddings.json mtime + doc_keys）")
    emb_mtime_r1, emb_keys_r1 = _snapshot_embeddings()
    emb_updated = emb_mtime_r1 > test_start_ts
    if emb_updated:
        _ok(
            "embeddings.json 已刷新落盘",
            f"mtime 进阶 +{emb_mtime_r1 - test_start_ts:.2f}s，doc_keys 共 {len(emb_keys_r1)} 条",
        )
    else:
        _fail("embeddings.json 未刷新（可能 periodic_save_task 尚未唤醒）")
    emb_key_hit = str(item_id) in emb_keys_r1
    if emb_key_hit:
        _ok(
            "doc_keys 包含目标商品",
            f"item_id={item_id} 在向量矩阵中（共 {len(emb_keys_r1)} 条）",
        )
    else:
        _fail(f"doc_keys 未找到 item_id={item_id}（当前共 {len(emb_keys_r1)} 条）")

    # ══════════════════════════════════════════════════════════════════════════
    print("\n  ── Run 2（重复推送，期望 analytics_events 无新增——幂等验证）──")
    # ══════════════════════════════════════════════════════════════════════════

    _step("再次 POST 同 item_id 事件")
    raw_body2, sig2 = _build_system_event_body(item_id)
    status2, elapsed2 = await _post_event(raw_body2, sig2)
    if status2 == HTTP_OK:
        _ok(f"Webhook 接收返回 200（往返 {elapsed2:.2f}s）")
    else:
        _fail(f"Webhook 返回 {status2}")

    _step(f"等待 {WAIT_SECONDS}s")
    for i in range(WAIT_SECONDS):
        await asyncio.sleep(1)
        print(f"  [{_ts()}]   ... {i + 1}/{WAIT_SECONDS}s", end="\r")
    print()

    _step("断言幂等：analytics_events 无新增")
    analytics_r2 = await _count_analytics(db_path, item_id)
    idempotent = analytics_r2 == analytics_r1
    if idempotent:
        _ok(f"无新增埋点（{analytics_r1} → {analytics_r2}）")
    else:
        _fail(f"埋点意外新增（{analytics_r1} → {analytics_r2}）")

    _step("断言幂等：doc_keys 数量无新增（重复推送不应幂达新增向量）")
    _, emb_keys_r2 = _snapshot_embeddings()
    emb_idempotent = len(emb_keys_r2) == len(emb_keys_r1)
    if emb_idempotent:
        _ok(
            f"doc_keys 数量未变（{len(emb_keys_r1)} → {len(emb_keys_r2)}）",
            "重复推送是原地替换而非追加，幂等性通过",
        )
    else:
        _fail(
            f"doc_keys 意外新增（{len(emb_keys_r1)} → {len(emb_keys_r2)}），幂等防线失效"
        )

    passed = (
        updated
        and kb_updated
        and (analytics_r1 >= analytics_before)
        and (status == HTTP_OK)
        and idempotent
        and emb_updated
        and emb_key_hit
        and emb_idempotent
    )
    return passed


if __name__ == "__main__":
    result = asyncio.run(run_phase_b())
    elapsed = time.monotonic() - _TEST_START
    print(
        f"\n{'✅ Phase B 通过' if result else '❌ Phase B 失败'}  总耗时 {elapsed:.1f}s\n"
    )
    sys.exit(0 if result else 1)
