"""会员账务域共享解析助手。"""


def to_int(value) -> int:
    """容忍转换整数（支持字符串/浮点），失败返回 0。"""
    if value is None:
        return 0
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


def to_bool(value) -> bool:
    """容忍转换布尔值，兼容数字与常见中英文字符串。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "是")
    return False


def to_fen(value) -> int:
    """把优惠券面额换算为分。

    整数按分原样保留；浮点按元换算为分；无法识别返回 0。
    说明：有赞不同接口的面额单位存在差异，真实联调前需按实际返回校准。
    """
    if value is None or value == "":
        return 0
    try:
        numeric = float(str(value))
    except (TypeError, ValueError):
        return 0
    if numeric == int(numeric):
        return int(numeric)
    return int(round(numeric * 100))
