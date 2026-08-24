"""AdminService 的纯业务逻辑单元测试。"""

import pytest
from unittest.mock import AsyncMock

from app.service.admin import AdminService
from app.models.config import FEATURED_PRODUCTS_KEY


@pytest.mark.asyncio
async def test_get_featured_products():
    """
    测试点：确保 Service 正确将获取主推款的请求代理给了 ConfigRepo。
    优势：不需要真实的 SQLite 数据库即可瞬间完成验证。
    """
    # 1. 模拟 (Mock) 底层 Repo 层
    mock_config_repo = AsyncMock()
    # 设定 mock 返回值
    mock_config_repo.get_list.return_value = ["经典提拉米苏盒子", "生椰拿铁"]

    # 2. 实例化被测 Service (注入 mock)
    service = AdminService(
        session_repo=AsyncMock(),
        message_repo=AsyncMock(),
        transfer_repo=AsyncMock(),
        knowledge_repo=AsyncMock(),
        config_repo=mock_config_repo,
    )

    # 3. 执行业务逻辑
    result = await service.get_featured_products()

    # 4. 断言 (Assertions)
    assert len(result) == 2
    assert result[0] == "经典提拉米苏盒子"
    # 验证底层 repo 的方法是否被按预期参数调用过 1 次
    mock_config_repo.get_list.assert_called_once_with(FEATURED_PRODUCTS_KEY)


@pytest.mark.asyncio
async def test_toggle_product_active_not_found():
    """
    测试点：当商品不存在时，toggle 操作应返回 None 且不调用 update_active。
    """
    mock_knowledge_repo = AsyncMock()
    mock_knowledge_repo.get_by_id.return_value = None  # 模拟查不到记录

    service = AdminService(
        session_repo=AsyncMock(),
        message_repo=AsyncMock(),
        transfer_repo=AsyncMock(),
        knowledge_repo=mock_knowledge_repo,
        config_repo=AsyncMock(),
    )

    result = await service.toggle_product_active(999)

    assert result is None
    # 确保没有触发写操作
    mock_knowledge_repo.update_active.assert_not_called()
