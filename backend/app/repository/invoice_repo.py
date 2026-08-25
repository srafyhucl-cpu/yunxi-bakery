"""发票请求数据访问层。

依据 docs/specs/2026-08-25-invoice-mvp-plan.md：P2 试运行前后台人工登记的
最小数据模型（不做电子发票直连）。
"""

from app.repository.base import BaseRepository


class InvoiceRepo(BaseRepository):
    """发票请求仓储（后台人工登记）。"""

    _COLS = (
        "id, order_no, customer_name, company_title, tax_no, email, amount_fen, "
        "status, issue_note, created_at, updated_at"
    )

    async def create(
        self,
        *,
        order_no: str | None = None,
        customer_name: str,
        company_title: str,
        tax_no: str,
        email: str,
        amount_fen: int | None = None,
    ) -> int:
        """登记一条发票请求，返回自增 id。"""
        cursor = await self._db.execute(
            "INSERT INTO invoice_requests "
            "(order_no, customer_name, company_title, tax_no, email, amount_fen, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'applied')",
            (order_no, customer_name, company_title, tax_no, email, amount_fen),
        )
        await self._db.commit()
        return int(cursor.lastrowid)

    async def get(self, invoice_id: int) -> dict | None:
        """按 id 读取一条。"""
        rows = await self._db.execute_fetchall(
            "SELECT " + self._COLS + " FROM invoice_requests WHERE id = ? LIMIT 1",
            (invoice_id,),
        )
        return rows[0] if rows else None

    async def list_all(self, *, status: str = "") -> list[dict]:
        """发票请求列表，可按状态筛选（status 为空时全部）。"""
        if status:
            return await self._db.execute_fetchall(
                "SELECT "
                + self._COLS
                + " FROM invoice_requests WHERE status = ? ORDER BY created_at DESC, id DESC",
                (status,),
            )
        return await self._db.execute_fetchall(
            "SELECT "
            + self._COLS
            + " FROM invoice_requests ORDER BY created_at DESC, id DESC"
        )

    async def mark_issued(self, invoice_id: int, issue_note: str = "") -> dict | None:
        """标记为已开发票（issued），带回最新记录。"""
        await self._db.execute(
            "UPDATE invoice_requests SET status = 'issued', issue_note = ?, "
            "updated_at = datetime('now') WHERE id = ? AND status != 'issued'",
            (issue_note, invoice_id),
        )
        await self._db.commit()
        return await self.get(invoice_id)
