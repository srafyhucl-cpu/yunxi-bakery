"""微信支付 v3 协议归一化器（B3.5，评审问题 4）。

支付通知 / 退款通知 / 支付查询 / 退款查询四类报文分别定义**独立**
Normalizer，互不共用字段校验，杜绝「退款复用支付字段」类错误：

- 字段路径按微信支付 v3 **真实报文**：金额在 `amount.total`（原支付金额）、
  `amount.refund`（本次退款金额），币种在 `amount.currency`（顶层无 currency）；
- **退款报文无 `appid`**（微信 v3 退款通知 / 退款查询不携带 appid，只有 mchid）；
- Normalizer 只做报文形状 / 类型校验（纯函数，不访问配置）；
  业务比对（mchid / appid 与配置一致、金额与快照一致）由调用方 Service 完成。

四类报文真实结构（微信支付 v3 API 文档）：
- 支付通知 resource 解密体：appid / mchid / out_trade_no / transaction_id /
  trade_type / trade_state / trade_state_desc / bank_type / attach /
  success_time / payer.openid / amount{ total, payer_total, currency, payer_currency }
- 退款通知 resource 解密体：mchid / out_trade_no / transaction_id /
  out_refund_no / refund_id / refund_status / success_time /
  amount{ total, refund, payer_total, payer_refund } / user_received_account
- 支付查询（订单查询 v3）响应：同支付通知结构（trade_state 含
  SUCCESS / NOTPAY / CLOSED / REVOKED / USERPAYING / PAYERROR）
- 退款查询 v3 响应：同退款通知结构（refund_status 含
  SUCCESS / CLOSED / ABNORMAL）
"""

from dataclasses import dataclass


class WechatProtocolError(ValueError):
    """微信支付 v3 报文校验失败（缺字段 / 类型错误 / 币种不符）。"""


def _require_str(transaction: dict, path: str, label: str) -> str:
    """读取并校验必填字符串字段。"""
    value = transaction.get(path)
    if value is None or str(value).strip() == "":
        raise WechatProtocolError(f"微信报文缺少 {label}（{path}）")
    return str(value).strip()


def _require_amount_fen(amount: dict, path: str, label: str) -> int:
    """读取并校验金额字段（微信 v3 金额为整数分，拒绝小数 / 非数字）。"""
    if not isinstance(amount, dict):
        raise WechatProtocolError(f"微信报文缺少金额对象 amount（{label}）")
    raw = amount.get(path)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise WechatProtocolError(f"微信报文 {label}（amount.{path}）无效") from None
    if value < 0:
        raise WechatProtocolError(f"微信报文 {label}（amount.{path}）为负")
    return value


def _require_amount_obj(transaction: dict, label: str) -> dict:
    amount = transaction.get("amount")
    if not isinstance(amount, dict):
        raise WechatProtocolError(f"微信报文缺少金额对象 amount（{label}）")
    return amount


@dataclass(frozen=True)
class PayNotify:
    """支付通知归一化结果（微信 v3）。"""

    appid: str
    mchid: str
    out_trade_no: str
    transaction_id: str
    trade_type: str
    trade_state: str
    success_time: str
    total_fen: int
    currency: str


class PayNotifyNormalizer:
    """支付通知 Normalizer：独立字段合同，币种取 amount.currency。"""

    def normalize(self, transaction: dict) -> PayNotify:
        appid = _require_str(transaction, "appid", "appid")
        mchid = _require_str(transaction, "mchid", "商户号")
        out_trade_no = _require_str(transaction, "out_trade_no", "商户订单号")
        transaction_id = _require_str(transaction, "transaction_id", "微信支付交易号")
        trade_state = _require_str(transaction, "trade_state", "支付状态")
        success_time = str(transaction.get("success_time", "") or "").strip()
        amount = _require_amount_obj(transaction, "支付通知")
        total_fen = _require_amount_fen(amount, "total", "订单金额")
        currency = _require_str(amount, "currency", "币种")
        if currency != "CNY":
            raise WechatProtocolError(f"微信支付通知币种不匹配：{currency}")
        return PayNotify(
            appid=appid,
            mchid=mchid,
            out_trade_no=out_trade_no,
            transaction_id=transaction_id,
            trade_type=str(transaction.get("trade_type", "") or "").strip(),
            trade_state=trade_state,
            success_time=success_time,
            total_fen=total_fen,
            currency=currency,
        )


@dataclass(frozen=True)
class RefundNotify:
    """退款通知归一化结果（微信 v3；无 appid，金额分原支付与本次退款）。"""

    mchid: str
    out_trade_no: str
    transaction_id: str
    out_refund_no: str
    refund_id: str
    refund_status: str
    success_time: str
    total_fen: int
    refund_fen: int
    payer_total_fen: int
    payer_refund_fen: int
    user_received_account: str


class RefundNotifyNormalizer:
    """退款通知 Normalizer：独立字段合同，不复用支付字段，不要求 appid。"""

    def normalize(self, transaction: dict) -> RefundNotify:
        mchid = _require_str(transaction, "mchid", "商户号")
        out_trade_no = _require_str(transaction, "out_trade_no", "原商户订单号")
        out_refund_no = _require_str(transaction, "out_refund_no", "商户退款单号")
        refund_id = _require_str(transaction, "refund_id", "微信退款单号")
        refund_status = _require_str(transaction, "refund_status", "退款状态")
        success_time = str(transaction.get("success_time", "") or "").strip()
        amount = _require_amount_obj(transaction, "退款通知")
        total_fen = _require_amount_fen(amount, "total", "原支付金额")
        refund_fen = _require_amount_fen(amount, "refund", "本次退款金额")
        payer_total_fen = _require_amount_fen(amount, "payer_total", "用户实付金额")
        payer_refund_fen = _require_amount_fen(amount, "payer_refund", "用户退款金额")
        user_received_account = str(
            transaction.get("user_received_account", "") or ""
        ).strip()
        return RefundNotify(
            mchid=mchid,
            out_trade_no=out_trade_no,
            transaction_id=str(transaction.get("transaction_id", "") or "").strip(),
            out_refund_no=out_refund_no,
            refund_id=refund_id,
            refund_status=refund_status,
            success_time=success_time,
            total_fen=total_fen,
            refund_fen=refund_fen,
            payer_total_fen=payer_total_fen,
            payer_refund_fen=payer_refund_fen,
            user_received_account=user_received_account,
        )


@dataclass(frozen=True)
class PayQueryResult:
    """支付查询（订单查询 v3）归一化结果。"""

    appid: str
    mchid: str
    out_trade_no: str
    transaction_id: str
    trade_state: str
    success_time: str
    total_fen: int
    currency: str


class PayQueryNormalizer:
    """支付查询 Normalizer：独立字段合同（trade_state 全枚举由调用方映射）。"""

    def normalize(self, transaction: dict) -> PayQueryResult:
        appid = _require_str(transaction, "appid", "appid")
        mchid = _require_str(transaction, "mchid", "商户号")
        out_trade_no = _require_str(transaction, "out_trade_no", "商户订单号")
        trade_state = _require_str(transaction, "trade_state", "支付状态")
        success_time = str(transaction.get("success_time", "") or "").strip()
        amount = _require_amount_obj(transaction, "支付查询")
        total_fen = _require_amount_fen(amount, "total", "订单金额")
        currency = _require_str(amount, "currency", "币种")
        if currency != "CNY":
            raise WechatProtocolError(f"微信支付查询币种不匹配：{currency}")
        return PayQueryResult(
            appid=appid,
            mchid=mchid,
            out_trade_no=out_trade_no,
            transaction_id=str(transaction.get("transaction_id", "") or "").strip(),
            trade_state=trade_state,
            success_time=success_time,
            total_fen=total_fen,
            currency=currency,
        )


@dataclass(frozen=True)
class RefundQueryResult:
    """退款查询 v3 归一化结果（无 appid）。"""

    mchid: str
    out_trade_no: str
    transaction_id: str
    out_refund_no: str
    refund_id: str
    refund_status: str
    success_time: str
    total_fen: int
    refund_fen: int


class RefundQueryNormalizer:
    """退款查询 Normalizer：独立字段合同，不复用支付字段，不要求 appid。"""

    def normalize(self, transaction: dict) -> RefundQueryResult:
        mchid = _require_str(transaction, "mchid", "商户号")
        out_trade_no = _require_str(transaction, "out_trade_no", "原商户订单号")
        out_refund_no = _require_str(transaction, "out_refund_no", "商户退款单号")
        refund_id = _require_str(transaction, "refund_id", "微信退款单号")
        refund_status = _require_str(transaction, "refund_status", "退款状态")
        success_time = str(transaction.get("success_time", "") or "").strip()
        amount = _require_amount_obj(transaction, "退款查询")
        total_fen = _require_amount_fen(amount, "total", "原支付金额")
        refund_fen = _require_amount_fen(amount, "refund", "本次退款金额")
        return RefundQueryResult(
            mchid=mchid,
            out_trade_no=out_trade_no,
            transaction_id=str(transaction.get("transaction_id", "") or "").strip(),
            out_refund_no=out_refund_no,
            refund_id=refund_id,
            refund_status=refund_status,
            success_time=success_time,
            total_fen=total_fen,
            refund_fen=refund_fen,
        )


__all__ = [
    "PayNotify",
    "PayNotifyNormalizer",
    "PayQueryResult",
    "PayQueryNormalizer",
    "RefundNotify",
    "RefundNotifyNormalizer",
    "RefundQueryResult",
    "RefundQueryNormalizer",
    "WechatProtocolError",
]
