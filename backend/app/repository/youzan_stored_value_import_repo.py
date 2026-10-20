"""有赞储值余额导入批次与 staging 明细数据访问层。"""

from collections.abc import Sequence

from app.repository.base import BaseRepository
from app.utils import now_str


class YouzanStoredValueImportRepo(BaseRepository):
    """导入批次/明细仓储（不自动提交，事务边界由服务层掌控）。"""

    BATCH_COLUMNS = (
        "id, source_file, source_sha256, status, total_rows, valid_rows, "
        "invalid_rows, applied_rows, total_principal_fen, total_bonus_fen, "
        "total_stored_value_fen, created_at, applied_at, rolled_back_at, note"
    )
    ROW_COLUMNS = (
        "id, batch_id, row_no, mobile, display_name, principal_fen, bonus_fen, "
        "reported_total_fen, yz_open_id, card_no, card_alias, status, error, "
        "created_at, applied_at"
    )

    async def create_batch(
        self,
        *,
        batch_id: str,
        source_file: str,
        source_sha256: str,
        total_rows: int,
        note: str = "",
    ) -> None:
        """创建导入批次（初始状态 created）。"""
        await self._db.execute(
            "INSERT INTO youzan_stored_value_import_batches (id, source_file, "
            "source_sha256, status, total_rows, created_at, note) "
            "VALUES (?, ?, ?, 'created', ?, ?, ?)",
            (batch_id, source_file, source_sha256, total_rows, now_str(), note),
        )

    async def get_batch(self, batch_id: str) -> dict | None:
        """按批次 ID 读取批次。"""
        rows = await self._db.execute_fetchall(
            "SELECT " + self.BATCH_COLUMNS + " FROM youzan_stored_value_import_batches "
            "WHERE id = ? LIMIT 1",
            (batch_id,),
        )
        return dict(rows[0]) if rows else None

    async def get_latest_batch_by_sha256(self, source_sha256: str) -> dict | None:
        """按文件摘要读取最近一个批次，用于同源文件复用与幂等。"""
        rows = await self._db.execute_fetchall(
            "SELECT " + self.BATCH_COLUMNS + " FROM youzan_stored_value_import_batches "
            "WHERE source_sha256 = ? ORDER BY created_at DESC, id DESC LIMIT 1",
            (source_sha256,),
        )
        return dict(rows[0]) if rows else None

    async def update_batch_validation(
        self,
        batch_id: str,
        *,
        status: str,
        valid_rows: int,
        invalid_rows: int,
        total_principal_fen: int,
        total_bonus_fen: int,
        total_stored_value_fen: int,
        note: str = "",
    ) -> None:
        """写回校验结果与合格行金额合计。"""
        await self._db.execute(
            "UPDATE youzan_stored_value_import_batches SET status = ?, valid_rows = ?, "
            "invalid_rows = ?, total_principal_fen = ?, total_bonus_fen = ?, "
            "total_stored_value_fen = ?, note = ? WHERE id = ?",
            (
                status,
                valid_rows,
                invalid_rows,
                total_principal_fen,
                total_bonus_fen,
                total_stored_value_fen,
                note,
                batch_id,
            ),
        )

    async def mark_batch_applied(
        self, batch_id: str, *, applied_rows: int, note: str = ""
    ) -> None:
        """标记批次入账完成。"""
        await self._db.execute(
            "UPDATE youzan_stored_value_import_batches SET status = 'applied', "
            "applied_rows = ?, applied_at = ?, note = ? WHERE id = ?",
            (applied_rows, now_str(), note, batch_id),
        )

    async def mark_batch_failed(self, batch_id: str, *, note: str) -> None:
        """标记批次失败（校验失败或入账中止）。"""
        await self._db.execute(
            "UPDATE youzan_stored_value_import_batches SET status = 'failed', "
            "note = ? WHERE id = ?",
            (note, batch_id),
        )

    async def mark_batch_rolled_back(self, batch_id: str, *, note: str = "") -> None:
        """标记批次已回滚。"""
        await self._db.execute(
            "UPDATE youzan_stored_value_import_batches SET status = 'rolled_back', "
            "rolled_back_at = ?, note = ? WHERE id = ?",
            (now_str(), note, batch_id),
        )

    async def insert_rows(
        self, batch_id: str, rows: Sequence[dict[str, object]]
    ) -> None:
        """批量写入 staging 明细行（初始状态 valid，待校验覆盖）。"""
        now = now_str()
        for row in rows:
            await self._db.execute(
                "INSERT INTO youzan_stored_value_import_rows (batch_id, row_no, "
                "mobile, display_name, principal_fen, bonus_fen, reported_total_fen, "
                "yz_open_id, card_no, card_alias, status, error, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'valid', '', ?)",
                (
                    batch_id,
                    int(row["row_no"]),
                    str(row["mobile"]),
                    str(row["display_name"]),
                    int(row["principal_fen"]),
                    int(row["bonus_fen"]),
                    row["reported_total_fen"],
                    str(row["yz_open_id"]),
                    str(row["card_no"]),
                    str(row["card_alias"]),
                    now,
                ),
            )

    async def list_rows(self, batch_id: str, *, status: str = "") -> list[dict]:
        """列出批次明细行，可按状态过滤，按行号升序。"""
        sql = (
            "SELECT " + self.ROW_COLUMNS + " FROM youzan_stored_value_import_rows "
            "WHERE batch_id = ?"
        )
        params: list[object] = [batch_id]
        if status:
            sql += " AND status = ?"
            params.append(status)
        rows = await self._db.execute_fetchall(
            sql + " ORDER BY row_no ASC", tuple(params)
        )
        return [dict(row) for row in rows]

    async def reset_row_statuses(self, batch_id: str) -> None:
        """重置未入账行的状态，使批次可在修正后重新校验。"""
        await self._db.execute(
            "UPDATE youzan_stored_value_import_rows SET status = 'valid', error = '' "
            "WHERE batch_id = ? AND status != 'applied'",
            (batch_id,),
        )

    async def update_row_status(
        self, row_id: int, *, status: str, error: str = ""
    ) -> None:
        """更新单行校验状态与错误说明。"""
        await self._db.execute(
            "UPDATE youzan_stored_value_import_rows SET status = ?, error = ? WHERE id = ?",
            (status, error, row_id),
        )

    async def mark_row_applied(self, row_id: int) -> None:
        """标记单行已入账。"""
        await self._db.execute(
            "UPDATE youzan_stored_value_import_rows SET status = 'applied', "
            "applied_at = ?, error = '' WHERE id = ?",
            (now_str(), row_id),
        )

    async def mark_rows_rolled_back(self, batch_id: str) -> None:
        """把批次内已入账行标记为已回滚。"""
        await self._db.execute(
            "UPDATE youzan_stored_value_import_rows SET status = 'rolled_back' "
            "WHERE batch_id = ? AND status = 'applied'",
            (batch_id,),
        )
