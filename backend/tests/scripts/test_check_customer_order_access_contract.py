"""客户订单归属静态合同测试。"""

from scripts.check_customer_order_access_contract import check, check_source


def test_customer_order_access_contract_passes_for_current_tools() -> None:
    assert check() == []


def test_customer_order_access_contract_rejects_unscoped_tool_calls() -> None:
    failures = check_source(
        """
async def get_order_info_tool(order_no, order_repo):
    await get_order_info(order_no=order_no, order_repo=order_repo)
    await order_repo.get_by_order_no(order_no)
""",
        "fixture/customer.py",
    )

    assert len(failures) == 2
    assert "get_order_info 缺少身份参数" in failures[0]
    assert "get_by_order" in failures[-1]
