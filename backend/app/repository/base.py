"""Repository 基础基类。

提供 Context-Local 数据库连接的自动路由功能，消除各 Repo 文件中的重复胶水代码。
"""

from collections.abc import Sequence
from contextlib import asynccontextmanager
from typing import Any
from typing import AsyncContextManager

import aiosqlite


class DatabaseHandle:
    """仓库层所需的数据库连接适配器。"""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._connection = connection

    async def execute(self, sql: str, parameters: Sequence[object] = ()) -> Any:
        return await self._connection.execute(sql, parameters)

    async def execute_fetchall(
        self, sql: str, parameters: Sequence[object] = ()
    ) -> list[dict[str, Any]]:
        rows = await self._connection.execute_fetchall(sql, parameters)
        return [dict(row) for row in rows]

    async def commit(self) -> None:
        await self._connection.commit()

    async def rollback(self) -> None:
        await self._connection.rollback()

    async def close(self) -> None:
        await self._connection.close()

    @property
    def in_transaction(self) -> bool:
        """返回底层连接当前是否已经处于事务中。"""
        return self._connection.in_transaction

    @asynccontextmanager
    async def transaction(self):
        """提供可嵌套的事务边界。"""
        if self._connection.in_transaction:
            await self._connection.execute("SAVEPOINT yunxi_order_uow")
            try:
                yield
            except Exception:
                await self._connection.execute("ROLLBACK TO SAVEPOINT yunxi_order_uow")
                await self._connection.execute("RELEASE SAVEPOINT yunxi_order_uow")
                raise
            else:
                await self._connection.execute("RELEASE SAVEPOINT yunxi_order_uow")
            return
        await self._connection.execute("BEGIN")
        try:
            yield
        except Exception:
            await self._connection.rollback()
            raise
        else:
            await self._connection.commit()


class BaseRepository:
    """所有数据访问层仓库的基类。"""

    def __init__(self, db: DatabaseHandle | None = None) -> None:
        self._injected_db = db

    @property
    def _db(self) -> DatabaseHandle:
        if self._injected_db is not None:
            return self._injected_db
        try:
            from app.database import db_conn_var

            return db_conn_var.get()
        except LookupError as exc:
            raise RuntimeError(
                "数据库操作未在 db_session_scope 上下文管理器中执行！"
            ) from exc

    def transaction(self) -> AsyncContextManager[None]:
        """返回供 service 层使用的事务上下文。"""
        return self._transaction()

    @asynccontextmanager
    async def _transaction(self):
        db = self._db
        if hasattr(db, "transaction"):
            async with db.transaction():
                yield
            return
        if db.in_transaction:
            await db.execute("SAVEPOINT yunxi_order_uow")
            try:
                yield
            except Exception:
                await db.execute("ROLLBACK TO SAVEPOINT yunxi_order_uow")
                await db.execute("RELEASE SAVEPOINT yunxi_order_uow")
                raise
            else:
                await db.execute("RELEASE SAVEPOINT yunxi_order_uow")
            return
        await db.execute("BEGIN")
        try:
            yield
        except Exception:
            await db.rollback()
            raise
        else:
            await db.commit()
