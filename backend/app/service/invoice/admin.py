"""发票请求后台管理服务。

依据 docs/specs/2026-08-25-invoice-mvp-plan.md：后台人工登记的最小闭环
（创建 / 列表 / 标记已开）。
"""

from app.repository.invoice_repo import InvoiceRepo


class AdminInvoiceService:
    """发票请求后台管理（人工登记流程，不做电子发票直连）。"""

    def __init__(self, db=None) -> None:
        self._invoice_repo = InvoiceRepo(db)

    async def create_invoice(
        self,
        payload: dict,
    ) -> dict:
        """登记一条发票请求。"""
        invoice_id = await self._invoice_repo.create(
            order_no=payload.get("orderNo") or None,
            customer_name=str(payload.get("customerName", "")).strip(),
            company_title=str(payload.get("companyTitle", "")).strip(),
            tax_no=str(payload.get("taxNo", "")).strip(),
            email=str(payload.get("email", "")).strip(),
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
        record = await self._invoice_repo.mark_issued(invoice_id, issue_note)
        if record is None:
            raise KeyError(f"发票请求不存在: {invoice_id}")
        return record
