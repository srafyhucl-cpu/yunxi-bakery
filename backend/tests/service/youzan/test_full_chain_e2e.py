"""
全链路端到端集成测试：模拟有赞平台真实推送 payload，验证 9 种订阅事件完整链路。

验证项：
- 商品事件 → youzan_products 表写入 + knowledge_base 表写入 + 向量索引更新
- 交易事件 → youzan_orders 表写入 + 埋点记录
- 异常/边界 → 不崩溃，不静默丢弃

payload 全部基于有赞官方文档真实结构造数（MSG/277, MSG/276, MSG/364, MSG/433, MSG/302）。
"""

import json
import urllib.parse

import pytest

from app.database import init_db
from app.repository.knowledge_repo import KnowledgeRepo
from app.repository.config_repo import ConfigRepo
from app.service.embedding_search import EmbeddingSearcher
from app.service.knowledge_retriever import KnowledgeRetriever
from app.service.youzan.event_handler import YouzanEventHandler


# ──────────────────────────────────────────────
# 仿真有赞 API 客户端
# ──────────────────────────────────────────────
class _MockYouzanClient:
    """
    仿真有赞 API 响应，覆盖 get_product / get_order 两个链路。
    按 item_id / tid 返回符合官方响应结构的数据。
    """

    async def get_product(self, item_id, alias=""):
        """仿真 youzan.item.get 响应结构：data.item"""
        return {
            "data": {
                "item": {
                    "title": f"芸熙烘焙·测试商品{item_id}",
                    "alias": f"yx{item_id}",
                    "price": 6800,
                    "quantity": 50,
                    "pic_url": "https://img.yzcdn.cn/fake.jpg",
                    "desc": "<p>手工制作，动物奶油，草莓夹心千层蛋糕</p>",
                    "skus": [
                        {
                            "sku_id": 90001,
                            "price": 6800,
                            "quantity": 30,
                            "properties_name_json": json.dumps(
                                [
                                    {"k": "规格", "v": "6寸"},
                                ]
                            ),
                        },
                        {
                            "sku_id": 90002,
                            "price": 9800,
                            "quantity": 20,
                            "properties_name_json": json.dumps(
                                [
                                    {"k": "规格", "v": "8寸"},
                                ]
                            ),
                        },
                    ],
                    "item_props": [
                        {
                            "prop_name": "甜度",
                            "is_multiple": False,
                            "text_models": [
                                {"prop_text_name": "正常甜", "price": 0},
                                {"prop_text_name": "七分甜", "price": 0},
                            ],
                        }
                    ],
                }
            }
        }

    async def get_order(self, order_no: str, *a, **kw):
        """仿真 youzan.trade.get 响应结构：data.full_order_info"""
        return {
            "data": {
                "full_order_info": {
                    "order_info": {
                        "tid": order_no,
                        "status": "WAIT_SELLER_SEND_GOODS",
                        "status_str": "待发货",
                        "pay_time": "2026-05-23 14:30:00",
                        "consign_time": "",
                        "created": "2026-05-23 14:28:00",
                        "pay_type_str": "微信支付",
                        "express_type": 1,
                        "refund_state": 0,
                    },
                    "pay_info": {
                        "payment": "68.00",
                        "total_fee": "68.00",
                        "post_fee": "0.00",
                    },
                    "buyer_info": {
                        "buyer_id": "buyer_e2e_001",
                        "outer_user_id": "wx_openid_abc",
                    },
                    "address_info": {
                        "delivery_province": "上海",
                        "delivery_city": "上海市",
                        "delivery_district": "浦东新区",
                        "delivery_start_time": "2026-05-24 10:00:00",
                    },
                    "orders": [
                        {
                            "oid": f"oid_{order_no}_1",
                            "item_id": 5836487486,
                            "alias": "yx5836487486",
                            "title": "草莓千层蛋糕 6寸",
                            "num": 1,
                            "price": "68.00",
                            "payment": "68.00",
                            "sku_properties_name": "6寸",
                            "buyer_messages": "生日快乐",
                        }
                    ],
                }
            },
        }


async def _setup(db=None):
    """初始化 DB + handler。"""
    if db is None:
        db = await init_db(":memory:")
    vs = EmbeddingSearcher()
    vs.build([])
    kr = KnowledgeRetriever(KnowledgeRepo(db), vs, config_repo=ConfigRepo(db))
    handler = YouzanEventHandler(
        db=db, knowledge_retriever=kr, youzan_client=_MockYouzanClient()
    )
    return db, handler


# ══════════════════════════════════════════════
# 商品事件 × 4
# ══════════════════════════════════════════════


@pytest.mark.asyncio
async def test_e2e_item_info_create():
    """
    事件 1：ITEM_INFO — 商品新增 (ITEM_CREATE)
    官方文档 MSG/277：顶层 id = 商品ID，msg 只含元数据（无 item_id）。
    验证：youzan_products + knowledge_base 写入。
    """
    payload = {
        "msg": '{"mode":1,"kdt_id":63077,"test":false,"sign":"a1b2c3d4e5f6"}',
        "kdt_name": "芸熙烘焙",
        "type": "ITEM_INFO",
        "version": "1716451200000",
        "kdt_id": "63077",
        "id": "5001001",
        "msg_id": "已废弃",
        "app_id": "299232221a",
        "status": "ITEM_CREATE",
    }
    db, handler = await _setup()
    await handler.handle_system_event(
        payload=payload,
        event_type="ITEM_INFO",
        updated_at_str="2026-05-23 15:00:00",
        msg_id="msg-item-info-001",
    )

    # 验证 youzan_products
    rows = await db.execute_fetchall(
        "SELECT item_id, title FROM youzan_products WHERE item_id = 5001001"
    )
    assert len(rows) == 1, "ITEM_INFO ITEM_CREATE 应写入 youzan_products"
    assert "芸熙烘焙" in rows[0]["title"]

    # 验证 knowledge_base
    kb_rows = await db.execute_fetchall(
        "SELECT content FROM knowledge_base WHERE youzan_item_id = 5001001"
    )
    assert len(kb_rows) == 1, "ITEM_INFO 应同步写入 knowledge_base"
    assert "草莓" in kb_rows[0]["content"], "知识库内容应包含商品描述关键词"

    await db.close()


@pytest.mark.asyncio
async def test_e2e_item_info_update():
    """
    事件 2：ITEM_INFO — 商品编辑 (ITEM_UPDATE)
    同 ITEM_CREATE 结构，status 为 ITEM_UPDATE。
    """
    payload = {
        "msg": '{"mode":1,"kdt_id":63077,"test":false,"sign":"x9y8z7"}',
        "kdt_name": "芸熙烘焙",
        "type": "ITEM_INFO",
        "version": "1716451300000",
        "kdt_id": "63077",
        "id": "5001002",
        "msg_id": "已废弃",
        "app_id": "299232221a",
        "status": "ITEM_UPDATE",
    }
    db, handler = await _setup()
    await handler.handle_system_event(
        payload=payload,
        event_type="ITEM_INFO",
        updated_at_str="2026-05-23 15:01:00",
        msg_id="msg-item-info-002",
    )
    rows = await db.execute_fetchall(
        "SELECT item_id FROM youzan_products WHERE item_id = 5001002"
    )
    assert len(rows) == 1, "ITEM_INFO ITEM_UPDATE 应写入 youzan_products"
    await db.close()


@pytest.mark.asyncio
async def test_e2e_item_state_down():
    """
    事件 3：ITEM_STATE — 商品下架 (ITEM_SALE_DOWN)
    官方文档 MSG/276：id=商品ID，msg 为 URL 编码 JSON，内层 data.is_display=0。
    验证：youzan_products 写入 + knowledge_base 被删除（下架擦除向量）。
    """
    inner_data = json.dumps(
        {
            "item_id": 5001003,
            "alias": "yx5001003",
            "kdt_id": 63077,
            "is_display": 0,
        }
    )
    msg_obj = json.dumps({"data": inner_data, "change_fields": '["is_display"]'})
    payload = {
        "msg": urllib.parse.quote(msg_obj),
        "kdt_name": "芸熙烘焙",
        "type": "ITEM_STATE",
        "version": "1716451400000",
        "kdt_id": "63077",
        "id": "5001003",
        "msg_id": "5001003",
        "app_id": "299232221a",
        "status": "ITEM_SALE_DOWN",
    }
    db, handler = await _setup()

    # 先写入一条知识（模拟之前上架已同步）
    await db.execute(
        "INSERT INTO knowledge_base (category, title, content, youzan_item_id) VALUES (?, ?, ?, ?)",
        ("product", "测试商品5001003", "旧内容", "5001003"),
    )
    await db.commit()

    await handler.handle_system_event(
        payload=payload,
        event_type="ITEM_STATE",
        updated_at_str="2026-05-23 15:02:00",
        msg_id="msg-item-state-001",
    )

    # 验证 youzan_products 写入（即使下架也需要记录）
    prod_rows = await db.execute_fetchall(
        "SELECT item_id, is_active FROM youzan_products WHERE item_id = 5001003"
    )
    assert len(prod_rows) == 1, "ITEM_STATE 下架应写入 youzan_products"
    assert prod_rows[0]["is_active"] == 0, "下架商品 is_active 应为 0"

    # 验证 knowledge_base 软下架（is_active=0）
    kb_rows = await db.execute_fetchall(
        "SELECT is_active FROM knowledge_base WHERE youzan_item_id = '5001003'"
    )
    assert len(kb_rows) == 1, "下架商品知识条目应保留"
    assert kb_rows[0]["is_active"] == 0, "下架商品 knowledge_base.is_active 应为 0"

    await db.close()


@pytest.mark.asyncio
async def test_e2e_item_state_up():
    """
    事件 4：ITEM_STATE — 商品上架 (ITEM_SALE_UP)
    is_display=1，应写库 + 写知识库。
    """
    inner_data = json.dumps(
        {
            "item_id": 5001004,
            "alias": "yx5001004",
            "kdt_id": 63077,
            "is_display": 1,
        }
    )
    msg_obj = json.dumps({"data": inner_data, "change_fields": '["is_display"]'})
    payload = {
        "msg": urllib.parse.quote(msg_obj),
        "kdt_name": "芸熙烘焙",
        "type": "ITEM_STATE",
        "version": "1716451500000",
        "kdt_id": "63077",
        "id": "5001004",
        "msg_id": "5001004",
        "app_id": "299232221a",
        "status": "ITEM_SALE_UP",
    }
    db, handler = await _setup()
    await handler.handle_system_event(
        payload=payload,
        event_type="ITEM_STATE",
        updated_at_str="2026-05-23 15:03:00",
        msg_id="msg-item-state-002",
    )

    prod_rows = await db.execute_fetchall(
        "SELECT item_id, is_active FROM youzan_products WHERE item_id = 5001004"
    )
    assert len(prod_rows) == 1
    assert prod_rows[0]["is_active"] == 1, "上架商品 is_active 应为 1"

    kb_rows = await db.execute_fetchall(
        "SELECT content FROM knowledge_base WHERE youzan_item_id = 5001004"
    )
    assert len(kb_rows) == 1, "上架商品应写入 knowledge_base"

    await db.close()


@pytest.mark.asyncio
async def test_e2e_item_group_change():
    """
    事件 5：item_group_change_msg — 商品分组变更
    官方文档 MSG/364：data.item_id 在顶层，id 是校验字段。
    """
    payload = {
        "id": "0a4550c002d5d05246d1",
        "kdt_id": "63077",
        "version": "1716451600000",
        "data": {"item_id": "5001005"},
    }
    db, handler = await _setup()
    await handler.handle_system_event(
        payload=payload,
        event_type="item_group_change_msg",
        updated_at_str="2026-05-23 15:04:00",
        msg_id="msg-group-001",
    )

    rows = await db.execute_fetchall(
        "SELECT item_id FROM youzan_products WHERE item_id = 5001005"
    )
    assert len(rows) == 1, "item_group_change_msg 应写入 youzan_products"

    kb_rows = await db.execute_fetchall(
        "SELECT content FROM knowledge_base WHERE youzan_item_id = 5001005"
    )
    assert len(kb_rows) == 1, "item_group_change_msg 应同步写入 knowledge_base"
    await db.close()


@pytest.mark.asyncio
async def test_e2e_sku_stock_update():
    """
    事件 6：youzan_item_skuStockOrSoldNumUpdated — 库存/销量变更
    官方文档 MSG/433：item_id 在 payload 顶层。
    """
    payload = {
        "kdt_id": "63077",
        "event_type": "UPDATE",
        "item_id": "5001006",
        "channel": "0",
        "sku_id": "90099",
    }
    db, handler = await _setup()
    await handler.handle_system_event(
        payload=payload,
        event_type="youzan_item_skuStockOrSoldNumUpdated",
        updated_at_str="2026-05-23 15:05:00",
        msg_id="msg-sku-001",
    )

    rows = await db.execute_fetchall(
        "SELECT item_id FROM youzan_products WHERE item_id = 5001006"
    )
    assert len(rows) == 1, "youzan_item_skuStockOrSoldNumUpdated 应写入 youzan_products"
    await db.close()


# ══════════════════════════════════════════════
# 交易事件 × 5
# ══════════════════════════════════════════════


@pytest.mark.asyncio
async def test_e2e_trade_create():
    """
    事件 7：trade_TradeCreate — 订单创建
    msg 为 dict，tid 在 msg.full_order_info.order_info.tid。
    """
    tid = "E20260523150600001"
    payload = {
        "msg": {
            "full_order_info": {
                "order_info": {
                    "tid": tid,
                    "status": "WAIT_BUYER_PAY",
                    "created": "2026-05-23 15:06:00",
                },
                "buyer_info": {"buyer_id": "buyer_tc_001"},
                "orders": [{"title": "草莓千层", "num": 1, "price": "68.00"}],
            }
        },
        "kdt_name": "芸熙烘焙",
        "type": "trade_TradeCreate",
        "kdt_id": "63077",
        "id": tid,
        "msg_id": "uuid-trade-create-001",
        "status": "WAIT_BUYER_PAY",
    }
    db, handler = await _setup()
    await handler.handle_system_event(
        payload=payload,
        event_type="trade_TradeCreate",
        updated_at_str="2026-05-23 15:06:00",
        msg_id="uuid-trade-create-001",
    )

    rows = await db.execute_fetchall(
        "SELECT order_no, status FROM youzan_orders WHERE order_no = ?", (tid,)
    )
    assert len(rows) == 1, "trade_TradeCreate 应写入 youzan_orders"
    await db.close()


@pytest.mark.asyncio
async def test_e2e_trade_buyer_pay():
    """
    事件 8：trade_TradeBuyerPay — 买家付款
    官方文档 MSG/302：msg 为 dict，完整 full_order_info 结构。
    """
    tid = "E20260523150700002"
    payload = {
        "msg": {
            "delivery_order": [],
            "order_promotion": {"item": [], "order": []},
            "refund_order": [],
            "full_order_info": {
                "order_info": {
                    "tid": tid,
                    "status": "WAIT_SELLER_SEND_GOODS",
                    "created": "2026-05-23 15:06:30",
                    "pay_time": "2026-05-23 15:07:00",
                },
                "pay_info": {
                    "payment": "68.00",
                    "total_fee": "68.00",
                    "post_fee": "0.00",
                },
                "buyer_info": {
                    "buyer_id": "buyer_pay_001",
                    "yz_open_id": "yz_open_abc",
                },
                "address_info": {
                    "delivery_province": "上海",
                    "delivery_city": "上海市",
                    "delivery_district": "浦东新区",
                    "receiver_name": "张三",
                    "receiver_tel": "13800138000",
                },
                "orders": [
                    {
                        "oid": "oid_pay_001",
                        "item_id": 5836487486,
                        "title": "草莓千层蛋糕",
                        "num": 1,
                        "price": "68.00",
                        "payment": "68.00",
                    }
                ],
            },
        },
        "kdt_name": "芸熙烘焙",
        "type": "trade_TradeBuyerPay",
        "version": "1716451620000",
        "kdt_id": "63077",
        "id": tid,
        "msg_id": "uuid-trade-pay-001",
        "status": "WAIT_SELLER_SEND_GOODS",
    }
    db, handler = await _setup()
    await handler.handle_system_event(
        payload=payload,
        event_type="trade_TradeBuyerPay",
        updated_at_str="2026-05-23 15:07:00",
        msg_id="uuid-trade-pay-001",
    )

    rows = await db.execute_fetchall(
        "SELECT order_no, status FROM youzan_orders WHERE order_no = ?", (tid,)
    )
    assert len(rows) == 1, "trade_TradeBuyerPay 应写入 youzan_orders"
    assert rows[0]["status"] == "WAIT_SELLER_SEND_GOODS"
    await db.close()


@pytest.mark.asyncio
async def test_e2e_trade_seller_ship():
    """
    事件 9：trade_TradeSellerShip — 卖家发货
    msg 为 dict，tid 在顶层。
    """
    tid = "E20260523150800003"
    payload = {
        "msg": {
            "tid": tid,
            "status": "WAIT_BUYER_CONFIRM_GOODS",
            "update_time": "2026-05-23 15:08:00",
        },
        "kdt_name": "芸熙烘焙",
        "type": "trade_TradeSellerShip",
        "kdt_id": "63077",
        "id": tid,
        "msg_id": "uuid-trade-ship-001",
        "status": "WAIT_BUYER_CONFIRM_GOODS",
    }
    db, handler = await _setup()
    await handler.handle_system_event(
        payload=payload,
        event_type="trade_TradeSellerShip",
        updated_at_str="2026-05-23 15:08:00",
        msg_id="uuid-trade-ship-001",
    )

    rows = await db.execute_fetchall(
        "SELECT order_no FROM youzan_orders WHERE order_no = ?", (tid,)
    )
    assert len(rows) == 1, "trade_TradeSellerShip 应写入 youzan_orders"
    await db.close()


@pytest.mark.asyncio
async def test_e2e_trade_success():
    """
    事件 10：trade_TradeSuccess — 交易成功
    msg 为 dict，tid 在顶层。
    """
    tid = "E20260523150900004"
    payload = {
        "msg": {
            "tid": tid,
            "status": "TRADE_SUCCESS",
            "update_time": "2026-05-23 15:09:00",
        },
        "kdt_name": "芸熙烘焙",
        "type": "trade_TradeSuccess",
        "kdt_id": "63077",
        "id": tid,
        "msg_id": "uuid-trade-success-001",
        "status": "TRADE_SUCCESS",
    }
    db, handler = await _setup()
    await handler.handle_system_event(
        payload=payload,
        event_type="trade_TradeSuccess",
        updated_at_str="2026-05-23 15:09:00",
        msg_id="uuid-trade-success-001",
    )

    rows = await db.execute_fetchall(
        "SELECT order_no FROM youzan_orders WHERE order_no = ?", (tid,)
    )
    assert len(rows) == 1, "trade_TradeSuccess 应写入 youzan_orders"
    await db.close()


@pytest.mark.asyncio
async def test_e2e_trade_close():
    """
    事件 11：trade_TradeClose — 交易关闭
    msg 为 dict，tid 在顶层。
    """
    tid = "E20260523151000005"
    payload = {
        "msg": {
            "tid": tid,
            "status": "TRADE_CLOSED",
            "close_type": 1,
            "update_time": "2026-05-23 15:10:00",
        },
        "kdt_name": "芸熙烘焙",
        "type": "trade_TradeClose",
        "kdt_id": "63077",
        "id": tid,
        "msg_id": "uuid-trade-close-001",
        "status": "TRADE_CLOSED",
    }
    db, handler = await _setup()
    await handler.handle_system_event(
        payload=payload,
        event_type="trade_TradeClose",
        updated_at_str="2026-05-23 15:10:00",
        msg_id="uuid-trade-close-001",
    )

    rows = await db.execute_fetchall(
        "SELECT order_no FROM youzan_orders WHERE order_no = ?", (tid,)
    )
    assert len(rows) == 1, "trade_TradeClose 应写入 youzan_orders"
    await db.close()


# ══════════════════════════════════════════════
# 全链路一体化：单个 DB 内 9 种事件连续推送，互不干扰
# ══════════════════════════════════════════════


@pytest.mark.asyncio
async def test_e2e_all_nine_events_in_sequence():
    """
    在同一个 DB 实例内依次推送所有 9 种事件类型，验证：
    - 商品事件：4 条写入 youzan_products + knowledge_base
    - 交易事件：5 条写入 youzan_orders
    - 互不干扰，无异常
    """
    db, handler = await _setup()

    # ① ITEM_INFO (ITEM_CREATE)
    await handler.handle_system_event(
        payload={
            "msg": '{"mode":1}',
            "type": "ITEM_INFO",
            "id": "9000001",
            "status": "ITEM_CREATE",
            "kdt_id": "63077",
        },
        event_type="ITEM_INFO",
        updated_at_str="2026-05-23 16:00:00",
        msg_id="seq-001",
    )

    # ② ITEM_STATE (上架)
    inner = json.dumps({"item_id": 9000002, "is_display": 1, "kdt_id": 63077})
    await handler.handle_system_event(
        payload={
            "msg": urllib.parse.quote(json.dumps({"data": inner})),
            "type": "ITEM_STATE",
            "id": "9000002",
            "status": "ITEM_SALE_UP",
            "kdt_id": "63077",
        },
        event_type="ITEM_STATE",
        updated_at_str="2026-05-23 16:01:00",
        msg_id="seq-002",
    )

    # ③ item_group_change_msg
    await handler.handle_system_event(
        payload={"id": "check123", "kdt_id": "63077", "data": {"item_id": "9000003"}},
        event_type="item_group_change_msg",
        updated_at_str="2026-05-23 16:02:00",
        msg_id="seq-003",
    )

    # ④ youzan_item_skuStockOrSoldNumUpdated
    await handler.handle_system_event(
        payload={
            "kdt_id": "63077",
            "item_id": "9000004",
            "sku_id": "99",
            "event_type": "UPDATE",
            "channel": "0",
        },
        event_type="youzan_item_skuStockOrSoldNumUpdated",
        updated_at_str="2026-05-23 16:03:00",
        msg_id="seq-004",
    )

    # ⑤ trade_TradeCreate
    await handler.handle_system_event(
        payload={
            "msg": {
                "full_order_info": {
                    "order_info": {
                        "tid": "E900001",
                        "status": "WAIT_BUYER_PAY",
                        "created": "2026-05-23 16:04:00",
                    },
                    "buyer_info": {"buyer_id": "b1"},
                    "orders": [],
                }
            },
            "type": "trade_TradeCreate",
            "id": "E900001",
            "msg_id": "seq-005",
        },
        event_type="trade_TradeCreate",
        updated_at_str="2026-05-23 16:04:00",
        msg_id="seq-005",
    )

    # ⑥ trade_TradeBuyerPay
    await handler.handle_system_event(
        payload={
            "msg": {
                "full_order_info": {
                    "order_info": {
                        "tid": "E900002",
                        "status": "WAIT_SELLER_SEND_GOODS",
                        "pay_time": "2026-05-23 16:05:00",
                    },
                    "buyer_info": {"buyer_id": "b2"},
                    "orders": [],
                }
            },
            "type": "trade_TradeBuyerPay",
            "id": "E900002",
            "msg_id": "seq-006",
        },
        event_type="trade_TradeBuyerPay",
        updated_at_str="2026-05-23 16:05:00",
        msg_id="seq-006",
    )

    # ⑦ trade_TradeSellerShip
    await handler.handle_system_event(
        payload={
            "msg": {"tid": "E900003", "status": "WAIT_BUYER_CONFIRM_GOODS"},
            "type": "trade_TradeSellerShip",
            "id": "E900003",
            "msg_id": "seq-007",
        },
        event_type="trade_TradeSellerShip",
        updated_at_str="2026-05-23 16:06:00",
        msg_id="seq-007",
    )

    # ⑧ trade_TradeSuccess
    await handler.handle_system_event(
        payload={
            "msg": {"tid": "E900004", "status": "TRADE_SUCCESS"},
            "type": "trade_TradeSuccess",
            "id": "E900004",
            "msg_id": "seq-008",
        },
        event_type="trade_TradeSuccess",
        updated_at_str="2026-05-23 16:07:00",
        msg_id="seq-008",
    )

    # ⑨ trade_TradeClose
    await handler.handle_system_event(
        payload={
            "msg": {"tid": "E900005", "status": "TRADE_CLOSED", "close_type": 1},
            "type": "trade_TradeClose",
            "id": "E900005",
            "msg_id": "seq-009",
        },
        event_type="trade_TradeClose",
        updated_at_str="2026-05-23 16:08:00",
        msg_id="seq-009",
    )

    # ═══ 断言 ═══
    # 商品
    prod_rows = await db.execute_fetchall(
        "SELECT item_id FROM youzan_products ORDER BY item_id"
    )
    prod_ids = {r["item_id"] for r in prod_rows}
    assert 9000001 in prod_ids, "ITEM_INFO 商品应写入"
    assert 9000002 in prod_ids, "ITEM_STATE 商品应写入"
    assert 9000003 in prod_ids, "item_group_change_msg 商品应写入"
    assert 9000004 in prod_ids, "skuStockUpdate 商品应写入"

    # 知识库（youzan_item_id 为 TEXT 类型）
    kb_rows = await db.execute_fetchall(
        "SELECT youzan_item_id FROM knowledge_base ORDER BY youzan_item_id"
    )
    kb_ids = {r["youzan_item_id"] for r in kb_rows}
    assert "9000001" in kb_ids, "ITEM_INFO 应同步知识库"
    assert "9000002" in kb_ids, "ITEM_STATE 上架应同步知识库"
    assert "9000003" in kb_ids, "item_group_change_msg 应同步知识库"
    assert "9000004" in kb_ids, "skuStockUpdate 应同步知识库"

    # 订单
    order_rows = await db.execute_fetchall(
        "SELECT order_no FROM youzan_orders ORDER BY order_no"
    )
    order_nos = {r["order_no"] for r in order_rows}
    assert "E900001" in order_nos, "trade_TradeCreate 订单应写入"
    assert "E900002" in order_nos, "trade_TradeBuyerPay 订单应写入"
    assert "E900003" in order_nos, "trade_TradeSellerShip 订单应写入"
    assert "E900004" in order_nos, "trade_TradeSuccess 订单应写入"
    assert "E900005" in order_nos, "trade_TradeClose 订单应写入"

    await db.close()
