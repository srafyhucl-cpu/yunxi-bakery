"""客户群运营服务测试。"""

from datetime import datetime
from zoneinfo import ZoneInfo

import aiosqlite
import pytest

from app.repository.customer_group_repo import CustomerGroupRepo
from app.service.customer import CustomerGroupOperationsService
from app.service.order.schedule import OrderScheduleService


BEIJING_TIME_ZONE = ZoneInfo("Asia/Shanghai")
DEFAULT_TEST_NOW = datetime(2026, 9, 14, 16, 0, tzinfo=BEIJING_TIME_ZONE)


class _FixedShopOperationsService:
    """测试用营业时间提供器。"""

    async def get_shop_operations(self) -> dict[str, str]:
        return {"businessHours": "09:00-19:30"}


def _build_schedule_service(now: datetime) -> OrderScheduleService:
    return OrderScheduleService(
        _FixedShopOperationsService(),
        now_provider=lambda: now,
    )


@pytest.fixture
def service(db: aiosqlite.Connection) -> CustomerGroupOperationsService:
    """构建客户群运营服务。"""
    return CustomerGroupOperationsService(
        CustomerGroupRepo(db),
        schedule_service=_build_schedule_service(DEFAULT_TEST_NOW),
    )


@pytest.mark.asyncio
async def test_customer_group_registration_summary_flow(
    service: CustomerGroupOperationsService,
) -> None:
    """服务层应支持客户群绑定、建批次、登记和汇总文案。"""
    group = await service.bind_group(
        {
            "chatId": "wr_group_1",
            "opengid": "opengid-1",
            "name": "周末团购群",
            "ownerUserid": "staff-1",
        }
    )
    campaign = await service.create_campaign(
        {
            "groupId": group["id"],
            "title": "周六蛋糕团购",
        }
    )
    first = await service.submit_registration(
        {
            "campaignId": campaign["id"],
            "customerName": "王女士",
            "customerPhone": "18800000001",
            "productName": "草莓奶油蛋糕",
            "quantity": 2,
            "fulfillmentMethod": "pickup",
            "desiredTime": "2026-09-15 18:00",
        },
        user_id="miniapp-user-1",
    )
    await service.submit_registration(
        {
            "campaignId": campaign["id"],
            "customerName": "李先生",
            "customerPhone": "18800000002",
            "productName": "芒果千层",
            "quantity": 1,
            "fulfillmentMethod": "delivery",
            "address": "测试路 1 号",
            "desiredTime": "2026-09-15 18:30",
        },
        user_id="miniapp-user-2",
    )
    await service.update_registration_status(first["id"], "confirmed")

    summary = await service.get_campaign_summary(campaign["id"])

    assert summary["totalRegistrations"] == 2
    assert summary["totalQuantity"] == 3
    assert summary["statusCounts"] == {"confirmed": 1, "pending": 1}
    assert {"productName": "草莓奶油蛋糕", "quantity": 2} in summary["productTotals"]
    assert "周六蛋糕团购登记汇总" in summary["summaryText"]
    assert "李先生" in summary["summaryText"]


@pytest.mark.asyncio
async def test_customer_group_registration_validates_required_fields(
    service: CustomerGroupOperationsService,
) -> None:
    """登记服务应拒绝缺少关键字段的请求。"""
    group = await service.bind_group({"chatId": "wr_group_2"})
    campaign = await service.create_campaign(
        {"groupId": group["id"], "title": "校验团购"}
    )

    with pytest.raises(ValueError, match="请填写正确的 11 位手机号"):
        await service.submit_registration(
            {
                "campaignId": campaign["id"],
                "customerName": "手机号错误",
                "customerPhone": "123",
                "productName": "草莓奶油蛋糕",
                "quantity": 1,
                "desiredTime": "2026-09-15 18:00",
            },
            user_id="miniapp-user-invalid",
        )


@pytest.mark.asyncio
async def test_customer_group_registration_requires_desired_time(
    service: CustomerGroupOperationsService,
) -> None:
    """登记服务必须要求期望取货或配送时间。"""
    group = await service.bind_group({"chatId": "wr_group_missing_time"})
    campaign = await service.create_campaign(
        {"groupId": group["id"], "title": "缺少时间"}
    )

    with pytest.raises(ValueError, match="请选择期望取货/配送时间"):
        await service.submit_registration(
            {
                "campaignId": campaign["id"],
                "customerName": "未选时间",
                "customerPhone": "18800000003",
                "productName": "草莓奶油蛋糕",
                "quantity": 1,
            },
            user_id="miniapp-user-missing-time",
        )


@pytest.mark.asyncio
async def test_customer_group_registration_rejects_closed_same_day(
    db: aiosqlite.Connection,
) -> None:
    """当天 17:00 后不得再登记当天履约时间。"""
    now = datetime(2026, 9, 14, 17, 1, tzinfo=BEIJING_TIME_ZONE)
    service = CustomerGroupOperationsService(
        CustomerGroupRepo(db),
        schedule_service=_build_schedule_service(now),
    )
    group = await service.bind_group({"chatId": "wr_group_closed"})
    campaign = await service.create_campaign(
        {"groupId": group["id"], "title": "截单校验"}
    )

    with pytest.raises(ValueError, match="当天订单已于 17:00 截止"):
        await service.submit_registration(
            {
                "campaignId": campaign["id"],
                "customerName": "截单客户",
                "customerPhone": "18800000004",
                "productName": "草莓奶油蛋糕",
                "quantity": 1,
                "desiredTime": "2026-09-14 18:00",
            },
            user_id="miniapp-user-closed",
        )


@pytest.mark.asyncio
async def test_customer_group_registration_rejects_outside_business_hours(
    service: CustomerGroupOperationsService,
) -> None:
    """登记时间必须落在门店营业时段内。"""
    group = await service.bind_group({"chatId": "wr_group_hours"})
    campaign = await service.create_campaign(
        {"groupId": group["id"], "title": "营业时段校验"}
    )

    with pytest.raises(ValueError, match="预约时间不在营业时间内"):
        await service.submit_registration(
            {
                "campaignId": campaign["id"],
                "customerName": "超时客户",
                "customerPhone": "18800000005",
                "productName": "草莓奶油蛋糕",
                "quantity": 1,
                "desiredTime": "2026-09-15 20:00",
            },
            user_id="miniapp-user-hours",
        )
