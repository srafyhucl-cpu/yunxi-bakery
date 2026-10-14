"""Stage 2 核心业务测试：有赞会员认领/储值闭环 & 定制蛋糕/现烤现货双轨履约。"""

from datetime import datetime
from zoneinfo import ZoneInfo
import aiosqlite
import pytest

from app.repository.balance_ledger_repo import BalanceLedgerRepo
from app.repository.config_repo import ConfigRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.repository.session_repo import SessionRepo
from app.repository.youzan_inventory_repo import YouzanInventoryRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.channels.storefront import StorefrontAuthService
from app.service.order.creation import OrderCreationService
from app.service.order.fulfillment_dual_track import OrderFulfillmentDualTrackService
from app.service.order.inventory import OrderInventoryService
from app.service.order.schedule import OrderScheduleService
from app.service.order.timeline import OrderTimelineService
from app.service.shop_operations import ShopOperationsService
from app.service.stored_value import (
    MemberBalanceService,
    StoredValueOrderPaymentService,
)

BEIJING_TZ = ZoneInfo("Asia/Shanghai")


@pytest.mark.asyncio
async def test_member_claim_by_phone_with_history_orders(
    db: aiosqlite.Connection,
) -> None:
    """老会员手机号认领：自动关联客户主档、回显储值本金/赠送金、积分及历史订单。"""
    c_repo = CustomerMasterRepo(db)
    b_repo = MemberBalanceRepo(db)
    auth_service = StorefrontAuthService(
        customer_repo=c_repo, member_balance_repo=b_repo, db=db
    )

    phone = "13912345678"
    user_id = "wx_test_openid_claim"

    # 先模拟有赞导入的会员余额与历史订单
    await b_repo.upsert_identity(mobile=phone, display_name="有赞老会员", is_member=1)
    await b_repo.credit_stored_value(phone, amount_fen=15000, bonus_fen=5000)
    await b_repo.credit_points(phone, 200)

    await db.execute(
        "INSERT INTO youzan_orders (order_no, buyer_id, status, amount_fen, product_titles, total_quantity, pay_time, created_at, updated_at) "
        "VALUES (?, ?, 'TRADE_SUCCESS', 9900, '经典草莓蛋糕', 1, '2026-08-01 12:00:00', '2026-08-01 11:50:00', '2026-08-01 12:00:00')",
        ("E202608010001", phone),
    )
    await db.commit()

    # 用户执行手机号认领
    claimed = await auth_service.claim_member_by_phone(user_id=user_id, phone=phone)

    assert claimed["mobile"] == phone
    assert claimed["isMember"] is True
    assert claimed["storedValueFen"] == 15000
    assert claimed["principalFen"] == 10000
    assert claimed["bonusFen"] == 5000
    assert claimed["points"] == 200
    assert len(claimed["historyOrders"]) == 1
    assert claimed["historyOrders"][0]["orderNo"] == "E202608010001"

    # 验证客户主档与 openid 绑定成功
    resolved_mobile = await MemberBalanceService(
        customer_repo=c_repo, balance_repo=b_repo
    ).resolve_mobile(user_id)
    assert resolved_mobile == phone


@pytest.mark.asyncio
async def test_stored_value_payment_and_refund_idempotency(
    db: aiosqlite.Connection,
) -> None:
    """储值支付原子防透支、全额付清进入 PAID 状态，取消退款幂等写流水。"""
    c_repo = CustomerMasterRepo(db)
    b_repo = MemberBalanceRepo(db)
    l_repo = BalanceLedgerRepo(db)
    order_repo = OrderRepo(db)
    auth_service = StorefrontAuthService(
        customer_repo=c_repo, member_balance_repo=b_repo, db=db
    )
    phone = "13700001111"
    user_id = "wx_user_pay_test"

    await auth_service.claim_member_by_phone(user_id=user_id, phone=phone)
    await b_repo.credit_stored_value(phone, amount_fen=10000, bonus_fen=2000)

    member_service = MemberBalanceService(
        balance_repo=b_repo, ledger_repo=l_repo, customer_repo=c_repo
    )
    pay_service = StoredValueOrderPaymentService(
        order_repo=order_repo, member_service=member_service
    )

    # 插入 sessions 记录，满足 orders 外键约束
    await db.execute(
        "INSERT INTO sessions (id, channel, user_id, status) VALUES ('s1', 'miniapp', ?, 'active')",
        (user_id,),
    )
    await db.commit()

    # 1. 余额不足拒绝透支
    order_id_expensive = "order_exp_001"
    await db.execute(
        "INSERT INTO orders (id, session_id, channel, user_id, products, total_amount, payment, status) "
        "VALUES (?, 's1', 'miniapp', ?, '[]', 200.0, '{}', 'pending')",
        (order_id_expensive, user_id),
    )
    await db.commit()

    with pytest.raises(ValueError, match="储值余额不足"):
        await pay_service.pay_order_with_balance(order_id_expensive, user_id=user_id)

    # 2. 正常全额支付：成功扣减，订单变 PAID
    order_id = "order_normal_001"
    await db.execute(
        "INSERT INTO orders (id, session_id, channel, user_id, products, total_amount, payment, status) "
        "VALUES (?, 's1', 'miniapp', ?, '[]', 50.0, '{}', 'pending')",
        (order_id, user_id),
    )
    await db.commit()

    res = await pay_service.pay_order_with_balance(order_id, user_id=user_id)
    assert res["paymentStatus"] == "paid"
    assert res["balanceFen"] == 5000

    balance_now = await b_repo.get_by_mobile(phone)
    assert balance_now["stored_value_fen"] == 5000

    # 3. 退款幂等返还储值
    order_paid = await order_repo.get_order(order_id)
    await pay_service.refund_order_balance(order_paid)
    balance_refunded = await b_repo.get_by_mobile(phone)
    assert balance_refunded["stored_value_fen"] == 10000

    # 重复退款幂等：不重复加款
    await pay_service.refund_order_balance(order_paid)
    balance_repeat = await b_repo.get_by_mobile(phone)
    assert balance_repeat["stored_value_fen"] == 10000


@pytest.mark.asyncio
async def test_dual_track_cake_customization_and_advance_hours(
    db: aiosqlite.Connection,
) -> None:
    """定制蛋糕（PREORDER_CAKE）：缺少定制字段报错、预约不足最小提前小时数报错。"""
    order_repo = OrderRepo(db)
    session_repo = SessionRepo(db)
    event_repo = OrderEventRepo(db)
    p_repo = YouzanProductRepo(db)
    inv_repo = YouzanInventoryRepo(db)

    # 插入定制蛋糕商品（含 updated_at 满足非空约束）
    await db.execute(
        "INSERT INTO youzan_products (item_id, title, alias, price_fen, stock, is_active, updated_at) "
        "VALUES (101, '生巧慕斯定制蛋糕', 'cake_001', 19800, 10, 1, '2026-10-20 09:00:00')"
    )
    await db.commit()

    now = datetime(2026, 10, 20, 10, 0, tzinfo=BEIJING_TZ)
    inv_service = OrderInventoryService(p_repo, inv_repo)
    sched_service = OrderScheduleService(
        ShopOperationsService(ConfigRepo(db)), now_provider=lambda: now
    )
    timeline_service = OrderTimelineService(order_repo, event_repo)
    dual_track_service = OrderFulfillmentDualTrackService(
        order_repo=order_repo, now_provider=lambda: now
    )

    creation_service = OrderCreationService(
        order_repo=order_repo,
        session_repo=session_repo,
        inventory_service=inv_service,
        schedule_service=sched_service,
        timeline_service=timeline_service,
        dual_track_service=dual_track_service,
    )

    # 1. 缺少定制信息报错
    with pytest.raises(ValueError, match="定制信息"):
        await creation_service.create_order(
            {
                "items": [{"productId": 101, "quantity": 1}],
                "expectTime": "2026-10-20 16:00",
                "receiverName": "张三",
                "receiverPhone": "13800000000",
            }
        )

    # 2. 定制信息缺项报错
    with pytest.raises(ValueError, match="夹心口味"):
        await creation_service.create_order(
            {
                "items": [
                    {
                        "productId": 101,
                        "quantity": 1,
                        "customization": {
                            "size": "6寸",
                            "greeting": "生日快乐",
                            "accessories": "蜡烛",
                        },
                    }
                ],
                "expectTime": "2026-10-20 16:00",
                "receiverName": "张三",
                "receiverPhone": "13800000000",
            }
        )

    # 3. 提前预约时间不足（当前 10:00，预约 12:00，仅 2 小时 < 4 小时）
    with pytest.raises(ValueError, match="需至少提前 4 小时预约"):
        await creation_service.create_order(
            {
                "items": [
                    {
                        "productId": 101,
                        "quantity": 1,
                        "customization": {
                            "size": "6寸",
                            "filling": "芒果夹心",
                            "greeting": "生日快乐",
                            "accessories": "标配餐具+数字蜡烛",
                        },
                    }
                ],
                "expectTime": "2026-10-20 12:00",
                "receiverName": "张三",
                "receiverPhone": "13800000000",
            }
        )


@pytest.mark.asyncio
async def test_dual_track_slot_capacity_and_daily_stock(
    db: aiosqlite.Connection,
) -> None:
    """定制蛋糕时段限流防爆单 & 现烤现货原子扣减防超卖与取消释放。"""
    order_repo = OrderRepo(db)
    session_repo = SessionRepo(db)
    event_repo = OrderEventRepo(db)
    p_repo = YouzanProductRepo(db)
    inv_repo = YouzanInventoryRepo(db)

    # 插入定制蛋糕与现烤面包（含 updated_at）
    await db.execute(
        "INSERT INTO youzan_products (item_id, title, alias, price_fen, stock, is_active, updated_at) "
        "VALUES (201, '现烤法棍', 'bread_001', 1500, 2, 1, '2026-10-20 09:00:00')"
    )
    await db.execute(
        "INSERT INTO youzan_products (item_id, title, alias, price_fen, stock, is_active, updated_at) "
        "VALUES (202, '定制鲜奶蛋糕', 'cake_002', 15800, 20, 1, '2026-10-20 09:00:00')"
    )
    await db.commit()

    now = datetime(2026, 10, 20, 9, 0, tzinfo=BEIJING_TZ)
    inv_service = OrderInventoryService(p_repo, inv_repo)
    sched_service = OrderScheduleService(
        ShopOperationsService(ConfigRepo(db)), now_provider=lambda: now
    )
    timeline_service = OrderTimelineService(order_repo, event_repo)
    dual_track_service = OrderFulfillmentDualTrackService(
        order_repo=order_repo,
        slot_max_capacity=2,
        now_provider=lambda: now,
    )

    creation_service = OrderCreationService(
        order_repo=order_repo,
        session_repo=session_repo,
        inventory_service=inv_service,
        schedule_service=sched_service,
        timeline_service=timeline_service,
        dual_track_service=dual_track_service,
    )

    # 1. 现烤库存原子扣减防超卖
    # 下单 2 个法棍（库存刚好为 2）
    await creation_service.create_order(
        {
            "items": [
                {"productId": 201, "quantity": 2, "fulfillment_type": "DAILY_READY"}
            ],
            "expectTime": "2026-10-20 15:00",
            "receiverName": "李四",
            "receiverPhone": "13800000001",
        }
    )
    p_row = await p_repo.get_by_id(201)
    assert p_row["stock"] == 0

    # 再次下单法棍应超卖/售罄报错
    with pytest.raises(ValueError, match="商品已售罄|商品库存不足"):
        await creation_service.create_order(
            {
                "items": [{"productId": 201, "quantity": 1}],
                "expectTime": "2026-10-20 15:00",
                "receiverName": "李四",
                "receiverPhone": "13800000001",
            }
        )

    # 2. 定制蛋糕时段容量上限（设置容量为 2）
    cake_payload = {
        "items": [
            {
                "productId": 202,
                "quantity": 1,
                "customization": {
                    "size": "8寸",
                    "filling": "草莓",
                    "greeting": "快乐",
                    "accessories": "餐具",
                },
            }
        ],
        "expectTime": "2026-10-20 15:30",
        "receiverName": "王五",
        "receiverPhone": "13800000002",
    }
    await creation_service.create_order(cake_payload)
    await creation_service.create_order(cake_payload)

    # 第 3 单同一时段应触发爆单限流
    with pytest.raises(ValueError, match="接单已满"):
        await creation_service.create_order(cake_payload)
