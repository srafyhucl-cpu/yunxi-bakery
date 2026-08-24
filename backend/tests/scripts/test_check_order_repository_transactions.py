"""订单域 repository 事务静态门禁测试。"""

from scripts.check_order_repository_transactions import check


def test_order_repositories_do_not_commit() -> None:
    """首批订单域 repository 不得自行提交事务。"""
    assert check() == []
