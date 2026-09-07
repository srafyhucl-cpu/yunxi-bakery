"""发票请求后台管理服务。

依据 docs/specs/2026-08-25-invoice-mvp-plan.md：后台人工登记的最小闭环
（创建 / 列表 / 标记已开）。
"""

from app.repository.invoice_repo import InvoiceRepo


class InvoiceStateError(ValueError):
    """发票请求不允许执行目标状态流转。"""


class AdminInvoiceService:
    """发票请求后台管理（人工登记流程，不做电子发票直连）。"""

    def __init__(self, db=None) -> None:
        self._invoice_repo = InvoiceRepo(db)

    async def create_invoice(
        self,
        payload: dict,
    ) -> dict:
        """登记一条发票请求。"""
        required_fields = ("companyTitle", "taxNo", "email")
        normalized_values: dict[str, str] = {}
        missing_fields: list[str] = []
        for field in required_fields:
            value = payload.get(field)
            if not isinstance(value, str) or not value.strip():
                missing_fields.append(field)
            else:
                normalized_values[field] = value.strip()
        if missing_fields:
            raise ValueError(f"发票必填字段不能为空: {', '.join(missing_fields)}")
        invoice_id = await self._invoice_repo.create(
            order_no=payload.get("orderNo") or None,
            customer_name=str(payload.get("customerName", "")).strip(),
            company_title=normalized_values["companyTitle"],
            tax_no=normalized_values["taxNo"],
            email=normalized_values["email"],
            amount_fen=payload.get("amountFen"),
        )
        record = await self._invoice_repo.get(invoice_id)
        if record is None:
            raise RuntimeError("发票请求创建后读取失败")
        return record

    async def list_invoices(self, *, status: str = "") -> list[dict]:
        """发票请求列表。"""
        return await self._invoice_repo.list_all(status=status)

    async def mark_issued(self, invoice_id: int, issue_note: str = "") -> dict:
        """标记已开发票。"""
        updated, record = await self._invoice_repo.mark_issued(invoice_id, issue_note)
        if record is None:
            raise KeyError(f"发票请求不存在: {invoice_id}")
        if not updated:
            raise InvoiceStateError(f"发票请求状态不允许标记已开票: {invoice_id}")
        return record
