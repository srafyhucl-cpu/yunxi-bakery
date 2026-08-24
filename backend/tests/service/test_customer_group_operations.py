"""客户群运营服务测试。"""

import aiosqlite
import pytest

from app.repository.customer_group_repo import CustomerGroupRepo
from app.service.customer import CustomerGroupOperationsService


@pytest.fixture
def service(db: aiosqlite.Connection) -> CustomerGroupOperationsService:
    """构建客户群运营服务。"""
    return CustomerGroupOperationsService(CustomerGroupRepo(db))


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
            },
            user_id="miniapp-user-invalid",
        )
