"""
按照有赞推送真实格式模拟商品与交易事件，验证全链路无崩溃、无静默丢弃。

商品事件：
1. item_group_change_msg  - payload 顶层 data.item_id
2. ITEM_INFO              - 已废弃，跳过
3. youzan_item_skuStockOrSoldNumUpdated - item_id 在 payload 顶层
4. ITEM_STATE             - msg URL 编码，data 内层 JSON

交易事件：
5. trade_TradeCreate/TradeBuyerPay - tid 嵌套在 full_order_info.order_info
6. trade_TradeSuccess/TradeSellerShip/TradeClose - tid 在 msg 顶层
"""

import json
import pytest

from app.database import init_db
from app.repository.knowledge_repo import KnowledgeRepo
from app.repository.config_repo import ConfigRepo
from app.service.embedding_search import EmbeddingSearcher
from app.service.knowledge_retriever import KnowledgeRetriever
from app.service.youzan.event_handler import YouzanEventHandler


class _FakeClient:
    """有赞 API 仿真客户端，按 item_id 返回最小化合法商品结构。"""

    async def get_product(self, item_id, alias=""):
        return {
            "response": {
                "item": {
                    "title": f"仿真商品_{item_id}",
                    "alias": f"alias_{item_id}",
                    "price": 9900,
                    "quantity": 20,
                    "pic_url": "",
                    "desc": "",
                    "skus": [],
                    "item_props": [],
                }
            }
        }

    async def get_order(self, order_no: str, *a, **kw):
        """返回符合 event_trade.py / function_tool_order.py 解析结构的仿真订单。"""
        return {
            "gw_err_resp": None,
            "data": {
                "full_order_info": {
                    "order_info": {
                        "tid": order_no,
                        "status": "WAIT_SELLER_SEND_GOODS",
                        "status_str": "待发货",
                        "pay_time": "2026-05-23 12:00:00",
                        "consign_time": "",
                        "created": "2026-05-23 11:58:00",
                        "pay_type_str": "微信支付",
                        "express_type": 1,
                        "refund_state": 0,
                    },
                    "pay_info": {
                        "payment": "188.00",
                        "total_fee": "188.00",
                        "post_fee": "0.00",
                    },
                    "buyer_info": {"buyer_id": "test_buyer_001", "outer_user_id": ""},
                    "address_info": {
                        "delivery_province": "上海",
                        "delivery_city": "上海市",
                        "delivery_district": "浦东新区",
                        "delivery_start_time": "",
                    },
                    "orders": [
                        {
                            "oid": "mock_oid_001",
                            "item_id": 5836487486,
                            "alias": "mock5836487486",
                            "title": "草莓双层奶油蛋糕",
                            "num": 1,
                            "price": "188.00",
                            "payment": "188.00",
                            "sku_properties_name": "6寸",
                            "buyer_messages": "",
                        }
                    ],
                }
            },
        }


async def _make_handler(db):
    vs = EmbeddingSearcher()
    vs.build([])
    kr = KnowledgeRetriever(KnowledgeRepo(db), vs, config_repo=ConfigRepo(db))
    return YouzanEventHandler(
        db=db, knowledge_retriever=kr, youzan_client=_FakeClient()
    )


# ──────────────────────────────────────────────
# 事件 #1：item_group_change_msg
# payload 顶层 data.item_id，无 msg / type 字段
# event_type 来自 HTTP header（此处直接传参）
# ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_item_group_change_msg():
    payload = {
        "id": "0a4550c002d5d05246d1",
        "kdt_id": "10",
        "version": "1591250527",
        "data": {"item_id": "100010"},
    }
    db = await init_db(":memory:")
    handler = await _make_handler(db)
    await handler.handle_system_event(
        payload=payload,
        event_type="item_group_change_msg",
        updated_at_str="2026-05-23 13:00:00",
        msg_id="0a4550c002d5d05246d1",
    )
    rows = await db.execute_fetchall(
        "SELECT item_id FROM youzan_products WHERE item_id = 100010"
    )
    assert len(rows) == 1, "item_group_change_msg 应触发商品写入"
    await db.close()


# ──────────────────────────────────────────────
# 事件 #2：ITEM_INFO（商品新增/编辑）
# 场景A：msg 截断 JSON 降级为空字典，fallback 用 payload.id 写库
# 场景B：同理，顶层 id 就是商品 ID（官方文档 MSG/277 确认）
# ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_item_info_truncated_json_fallback_writes_db():
    """msg 截断时降级空字典，ITEM_INFO fallback 用 payload.id 做商品 ID 仍能写库。"""
    payload = {
        "msg": '{"mode":1,"kdt_id":55,"test":false,"sign":"3831b4ed685733d44',  # 截断
        "kdt_name": "有你有赞",
        "type": "ITEM_INFO",
        "version": "1616123995645",
        "kdt_id": "63077",
        "id": "400444679",
        "app_id": "299232221a",
        "status": "ITEM_CREATE",
    }
    db = await init_db(":memory:")
    handler = await _make_handler(db)
    await handler.handle_system_event(
        payload=payload,
        event_type="ITEM_INFO",
        updated_at_str="2026-05-23 13:00:00",
        msg_id="test-truncated",
    )
    rows = await db.execute_fetchall(
        "SELECT item_id FROM youzan_products WHERE item_id = 400444679"
    )
    assert len(rows) == 1, "ITEM_INFO msg 截断时应 fallback 用 payload.id 写库"
    await db.close()


@pytest.mark.asyncio
async def test_item_info_id_is_item_id_writes_db():
    """ITEM_INFO 真实推送：顶层 id 字段就是商品 ID（官方文档 MSG/277 确认），msg 只含元数据。"""
    payload = {
        "msg": '{"mode":1,"kdt_id":55,"test":false,"sign":"3831b4ed685733d44',  # 截断的元数据
        "kdt_name": "有你有赞",
        "type": "ITEM_INFO",
        "version": "1616123995645",
        "kdt_id": "63077",
        "id": "400444679",  # 真实商品 ID
        "msg_id": "已废弃",
        "app_id": "299232221a",
        "status": "ITEM_CREATE",
    }
    db = await init_db(":memory:")
    handler = await _make_handler(db)
    await handler.handle_system_event(
        payload=payload,
        event_type="ITEM_INFO",
        updated_at_str="2026-05-23 13:00:00",
        msg_id="400444679",
    )
    rows = await db.execute_fetchall(
        "SELECT item_id FROM youzan_products WHERE item_id = 400444679"
    )
    assert len(rows) == 1, "ITEM_INFO 顶层 id 应作为 item_id 写入 DB"
    await db.close()


# ──────────────────────────────────────────────
# 事件 #3：youzan_item_skuStockOrSoldNumUpdated
# item_id 直接在 payload 顶层，无 msg 字段
# event_type 来自 HTTP header
# ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_sku_stock_update():
    payload = {
        "kdt_id": "1896311",
        "event_type": "INSERT",
        "item_id": "1234",
        "channel": "1",
        "sku_id": "4567",
    }
    db = await init_db(":memory:")
    handler = await _make_handler(db)
    await handler.handle_system_event(
        payload=payload,
        event_type="youzan_item_skuStockOrSoldNumUpdated",
        updated_at_str="2026-05-23 13:00:00",
        msg_id="yz7-test-sku-update",
    )
    rows = await db.execute_fetchall(
        "SELECT item_id FROM youzan_products WHERE item_id = 1234"
    )
    assert len(rows) == 1, "youzan_item_skuStockOrSoldNumUpdated 应触发商品写入"
    await db.close()


# ──────────────────────────────────────────────
# 事件 #4：ITEM_STATE（标准格式）
# type 在 payload，msg 为 URL 编码 JSON
# ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_item_state_standard():
    import urllib.parse

    msg_content = json.dumps(
        {
            "kdt_id": "1896311",
            "event_type": "INSERT",
            "item_id": "1234",
            "channel": "1",
            "sku_id": "4567",
        }
    )
    payload = {
        "kdt_id": "1896311",
        "event_type": "INSERT",
        "type": "ITEM_STATE",
        "msg": urllib.parse.quote(msg_content),
        "id": "400444678",
    }
    db = await init_db(":memory:")
    handler = await _make_handler(db)
    await handler.handle_system_event(
        payload=payload,
        event_type="ITEM_STATE",
        updated_at_str="2026-05-23 13:00:00",
        msg_id="400444678",
    )
    rows = await db.execute_fetchall(
        "SELECT item_id FROM youzan_products WHERE item_id = 1234"
    )
    assert len(rows) == 1, "ITEM_STATE 应触发商品写入"
    await db.close()


# ──────────────────────────────────────────────
# ──────────────────────────────────────────────
# 事件 #5：trade_TradeCreate（tid 嵌套在 full_order_info.order_info）
# ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_trade_create_nested_tid_writes_db():
    """trade_TradeCreate msg 为 dict，tid 嵌套在 full_order_info.order_info，应写入 orders 表。"""
    tid = "E20260523001"
    payload = {
        "type": "trade_TradeCreate",
        "msg": {
            "full_order_info": {
                "order_info": {
                    "tid": tid,
                    "status": "WAIT_BUYER_PAY",
                    "created": "2026-05-23 12:00:00",
                },
            }
        },
        "msg_id": "trade-create-001",
    }
    db = await init_db(":memory:")
    handler = await _make_handler(db)
    await handler.handle_system_event(
        payload=payload,
        event_type="trade_TradeCreate",
        updated_at_str="2026-05-23 12:00:00",
        msg_id="trade-create-001",
    )
    rows = await db.execute_fetchall(
        "SELECT order_no FROM youzan_orders WHERE order_no = ?", (tid,)
    )
    assert len(rows) == 1, "trade_TradeCreate 应写入 youzan_orders 表"
    await db.close()


# ──────────────────────────────────────────────
# 事件 #6：trade_TradeSuccess（tid 在 msg 顶层）
# ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_trade_success_top_level_tid_writes_db():
    """trade_TradeSuccess msg 为 dict，tid 在顶层，应写入 orders 表。"""
    tid = "E20260523002"
    payload = {
        "type": "trade_TradeSuccess",
        "msg": {"tid": tid, "update_time": "2026-05-23 14:00:00"},
        "msg_id": "trade-success-001",
    }
    db = await init_db(":memory:")
    handler = await _make_handler(db)
    await handler.handle_system_event(
        payload=payload,
        event_type="trade_TradeSuccess",
        updated_at_str="2026-05-23 14:00:00",
        msg_id="trade-success-001",
    )
    rows = await db.execute_fetchall(
        "SELECT order_no FROM youzan_orders WHERE order_no = ?", (tid,)
    )
    assert len(rows) == 1, "trade_TradeSuccess 应写入 youzan_orders 表"
    await db.close()


# 组合：4 条同批推送互不干扰
# ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_batch_push_all_four_events():
    import urllib.parse

    db = await init_db(":memory:")
    handler = await _make_handler(db)

    events = [
        (
            {
                "id": "0a4550c002d5d05246d1",
                "kdt_id": "10",
                "version": "1591250527",
                "data": {"item_id": "100010"},
            },
            "item_group_change_msg",
            "0a4550c002d5d05246d1",
        ),
        (
            {
                "msg": '{"mode":1,"sign":"3831b4ed685733d44',
                "type": "ITEM_INFO",
                "id": "400444679",
                "msg_id": "已废弃",
            },
            "ITEM_INFO",
            "已废弃",
        ),
        (
            {"kdt_id": "1896311", "item_id": "1234", "sku_id": "4567"},
            "youzan_item_skuStockOrSoldNumUpdated",
            "yz7-sku-001",
        ),
        (
            {
                "type": "ITEM_STATE",
                "msg": urllib.parse.quote(json.dumps({"item_id": "5678"})),
                "id": "400444678",
            },
            "ITEM_STATE",
            "400444678",
        ),
    ]

    for payload, event_type, msg_id in events:
        await handler.handle_system_event(
            payload=payload,
            event_type=event_type,
            updated_at_str="2026-05-23 13:00:00",
            msg_id=msg_id,
        )

    rows = await db.execute_fetchall(
        "SELECT item_id FROM youzan_products ORDER BY item_id"
    )
    item_ids = {r["item_id"] for r in rows}
    assert 100010 in item_ids, "item_group_change_msg 商品应写入"
    assert 1234 in item_ids, "SKU 更新商品应写入"
    assert 5678 in item_ids, "ITEM_STATE 商品应写入"
    await db.close()
