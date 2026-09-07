"""金额模型统一合同测试：分是唯一 canonical 单位。"""

import ast
from pathlib import Path

import pytest

from app.service.youzan.order_parser import parse_youzan_order_response
from app.utils import fen_to_yuan, yuan_to_fen

MONEY_CRITICAL_FILES = (
    "app/service/youzan/order_parser.py",
    "app/service/youzan/event_trade.py",
    "app/service/order/creation.py",
    "app/service/order/payment_notification.py",
)


def _raw_order(payment: object, total_fee: object, post_fee: object) -> dict:
    """构造有赞 trade.get 最小响应。"""
    return {
        "data": {
            "full_order_info": {
                "order_info": {"status": "TRADE_PAID"},
                "pay_info": {
                    "payment": payment,
                    "total_fee": total_fee,
                    "post_fee": post_fee,
                },
                "buyer_info": {"buyer_id": "buyer-1"},
                "address_info": {},
                "orders": [],
            }
        }
    }


@pytest.mark.parametrize(
    ("yuan", "fen"),
    [
        (0, 0),
        ("0.01", 1),
        (0.01, 1),
        ("0.29", 29),
        (0.29, 29),
        ("1", 100),
        (19.99, 1999),
        ("19.99", 1999),
        ("2.675", 268),
        ("2.665", 267),
        ("99999999.99", 9999999999),
        (100, 10000),
    ],
)
def test_yuan_to_fen_boundary_values(yuan: object, fen: int) -> None:
    """边界值换算必须精确，半分半向上舍入。"""
    assert yuan_to_fen(yuan) == fen


@pytest.mark.parametrize("raw", ["", "abc", "12.34.56", "--5", None, True])
def test_yuan_to_fen_invalid_inputs_rejected(raw: object) -> None:
    """非法输入直接拒绝，不静默归零。"""
    with pytest.raises(ValueError, match="金额"):
        yuan_to_fen(raw)


@pytest.mark.parametrize(
    "fen",
    [0, 1, 2, 29, 99, 100, 101, 999, 12345, 19800, 39600, 158400, 9999999999],
)
def test_fen_float_round_trip_is_exact(fen: int) -> None:
    """分→浮点存储→分往返必须精确，覆盖数据库 REAL 路径。"""
    assert yuan_to_fen(fen_to_yuan(fen)) == fen


def test_youzan_parser_uses_integer_math() -> None:
    """有赞解析全链路整数分，无浮点中转残差。"""
    parsed = parse_youzan_order_response(_raw_order("19.99", "18.00", "2.00"))
    assert parsed is not None
    assert parsed.payment_fen == 1999
    assert parsed.post_fee_fen == 200
    assert parsed.discount_fen == 1
    assert parsed.payment_fen + parsed.discount_fen == 1800 + 200


def test_youzan_parser_classic_float_trap() -> None:
    """0.29 类经典浮点陷阱不得差一分。"""
    parsed = parse_youzan_order_response(_raw_order("0.29", "0.29", "0.00"))
    assert parsed is not None
    assert parsed.payment_fen == 29
    assert parsed.discount_fen == 0


def test_youzan_parser_partial_refund_accumulates() -> None:
    """部分退款累计口径：多次解析同一订单金额一致。"""
    first = parse_youzan_order_response(_raw_order("100.00", "100.00", "0.00"))
    second = parse_youzan_order_response(_raw_order("100.00", "100.00", "0.00"))
    assert first is not None and second is not None
    assert first.payment_fen == second.payment_fen == 10000
    assert first.discount_fen == second.discount_fen == 0


def test_money_critical_files_have_no_raw_float_math() -> None:
    """静态守卫：关键金额路径禁止裸 float 与裸分乘除。

     唯一例外是经规范边界适配器 fen_to_yuan_str 的显式转换
    （float(fen_to_yuan_str(...))），REAL 列只作只读传输形态，
     账务判定一律整数分。
    """
    root = Path(__file__).resolve().parents[2]
    for rel in MONEY_CRITICAL_FILES:
        content = (root / rel).read_text(encoding="utf-8")
        tree = ast.parse(content)
        float_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "float"
            and not _is_canonical_boundary_call(node)
        ]
        assert float_calls == [], f"{rel} 存在裸 float 转换"
        for line_number, line in enumerate(content.splitlines(), start=1):
            code = line.split("#", 1)[0]
            if "* 100" in code or "/ 100" in code:
                raise AssertionError(f"{rel}:{line_number} 存在裸分乘除")


def _is_canonical_boundary_call(node: ast.Call) -> bool:
    """是否为规范边界适配器转换 float(fen_to_yuan_str(...))。"""
    if len(node.args) != 1 or node.keywords:
        return False
    inner = node.args[0]
    return (
        isinstance(inner, ast.Call)
        and isinstance(inner.func, ast.Name)
        and inner.func.id == "fen_to_yuan_str"
    )
