"""反向代理安全合同测试。"""

from scripts.check_reverse_proxy_contract import check


def test_reverse_proxy_contract_has_required_directives() -> None:
    """反向代理示例必须保留 body、限流、超时和文档边界。"""
    assert check() == []
