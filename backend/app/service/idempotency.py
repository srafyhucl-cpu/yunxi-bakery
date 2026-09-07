"""幂等主体合同：同键必须同主体、同业务、同金额。

储值与积分记账共用本契约，防止同一幂等键被不同账户、不同业务或
不同金额复用。冲突一律抛 IdempotencyConflict（ValueError 子类，
保持旧调用方 except ValueError 兼容）。
"""

import hashlib


class IdempotencyConflict(ValueError):
    """幂等键与已存在流水的主体、业务或金额不一致。"""


def build_request_fingerprint(
    *,
    account: str,
    biz_type: str,
    biz_id: str,
    signed_amount: int,
) -> str:
    """由账户主体、业务归属与带符号金额生成请求指纹。"""
    raw = "|".join(
        [
            str(account or ""),
            str(biz_type or ""),
            str(biz_id or ""),
            str(int(signed_amount)),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def check_idempotency_contract(
    *,
    existing: dict,
    account: str,
    amount_field: str,
    signed_amount: int,
    unique_id: str,
) -> None:
    """校验已存在流水与本次请求的幂等合同，不一致抛冲突。

    账户主体不一致抛主体冲突；金额不一致抛金额冲突（保持旧错误文案
    兼容）；历史缺指纹流水仍按明文字段比对，保证兼容历史数据。
    """
    stored_account = str(existing.get("mobile", "") or existing.get("customer_id", ""))
    if stored_account and stored_account != str(account or ""):
        raise IdempotencyConflict(
            f"幂等主体冲突 unique_id={unique_id} "
            f"existing_account={stored_account} request_account={account}"
        )
    _check_amount(existing, amount_field, signed_amount, unique_id)


def _check_amount(
    existing: dict, amount_field: str, signed_amount: int, unique_id: str
) -> None:
    """同键金额不一致直接拒绝，保持旧错误文案兼容。"""
    if int(existing.get(amount_field, 0) or 0) != int(signed_amount):
        raise IdempotencyConflict(
            f"幂等键金额冲突 unique_id={unique_id} "
            f"existing={existing.get(amount_field)} expected={signed_amount}"
        )


def check_biz_binding(
    *,
    existing: dict,
    biz_type: str,
    biz_id: str,
    unique_id: str,
) -> None:
    """校验业务归属一致，同键不同业务必须冲突。"""
    for field, expected in (("biz_type", biz_type), ("biz_id", biz_id)):
        if str(existing.get(field, "") or "") != str(expected or ""):
            raise IdempotencyConflict(
                f"幂等主体冲突 unique_id={unique_id} field={field} "
                f"existing={existing.get(field)} request={expected}"
            )


def check_fingerprint_match(
    *, existing: dict, expected_fingerprint: str, unique_id: str
) -> None:
    """已落指纹的流水必须与本次请求指纹一致，跨路径复用直接拒绝。

    历史空指纹流水跳过本检查（仍受明文字段合同约束）。
    """
    stored = str(existing.get("request_fingerprint", "") or "")
    if stored and stored != str(expected_fingerprint or ""):
        raise IdempotencyConflict(
            f"幂等指纹冲突 unique_id={unique_id}，疑似跨业务复用幂等键"
        )


__all__ = [
    "IdempotencyConflict",
    "build_request_fingerprint",
    "check_biz_binding",
    "check_fingerprint_match",
    "check_idempotency_contract",
]
