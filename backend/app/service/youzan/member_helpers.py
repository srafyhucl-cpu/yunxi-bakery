"""会员账务域共享解析助手。"""

from app.utils import yuan_to_fen


def to_int(value) -> int:
    """容忍转换整数（支持字符串/浮点），失败返回 0。"""
    if value is None:
        return 0
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


def is_usable_int(value) -> bool:
    """判断输入能否被 `to_int` 真实解析（而非被折叠成 0）。

    `to_int` 的「失败返回 0」容忍语义适合可选字段，但**不适合**会被当作
    权威值写入的字段：缺失、空串与非数值都会被折叠成 `0`，从而把一个
    「未知」伪装成「确实为零」。权威写入路径必须先用本函数区分
    「输入为真 0」与「输入不可用」。
    """
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    try:
        float(str(value))
    except (TypeError, ValueError):
        return False
    return True


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
    return yuan_to_fen(str(value))
