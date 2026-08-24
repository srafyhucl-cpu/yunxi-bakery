"""
数据库初始化与管理。

职责：
- 启动时创建所有表与索引（WAL 模式）
- 数据库 Schema 定义存放在 app/migrations/schema.py
- 运行时微创迁移逻辑在本文件维护
- 提供连接生命周期管理
- 所有 repository 层共用同一个连接
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from pathlib import Path

import aiosqlite

from app.config import settings
from app.logger import setup_logger
from app.repository.base import DatabaseHandle
from app.migrations.schema import SCHEMA_STATEMENTS, PRAGMA_STATEMENTS

logger = setup_logger()
ROOT_DIR = Path(__file__).resolve().parent.parent
MISSING_COLUMN_ERROR = "no such column"
CREATE_INDEX_PREFIX = "CREATE INDEX"


def resolve_database_path(db_path: str | Path | None = None) -> str:
    """将数据库相对路径固定到项目根，避免受进程工作目录影响。"""
    path = Path(db_path or settings.DB_PATH)
    if str(path) == ":memory:" or path.is_absolute():
        return str(path)
    return str(ROOT_DIR / path)


async def init_db(db_path: str) -> aiosqlite.Connection:
    """初始化数据库：建表 + 索引 + 版本化迁移。"""
    resolved_db_path = resolve_database_path(db_path)
    conn = await aiosqlite.connect(resolved_db_path)
    conn.row_factory = aiosqlite.Row
    for pragma in PRAGMA_STATEMENTS:
        await conn.execute(pragma)
    await _execute_schema_statements(conn)
    await conn.commit()

    # 执行版本化增量迁移（含动态迁移逻辑）
    from app.migrations.runner import run_migrations

    await run_migrations(conn)

    logger.info("Database initialized at %s", resolved_db_path)
    return conn


async def _execute_schema_statements(conn: aiosqlite.Connection) -> None:
    """执行全量 schema，并允许旧库先跳过缺列索引。"""
    for stmt in SCHEMA_STATEMENTS:
        try:
            await conn.execute(stmt)
        except aiosqlite.OperationalError as exc:
            if _is_missing_column_index_statement(stmt, exc):
                logger.debug("跳过待迁移字段索引，稍后由版本化迁移补齐: %s", exc)
                continue
            raise


def _is_missing_column_index_statement(
    stmt: str,
    exc: aiosqlite.OperationalError,
) -> bool:
    return stmt.lstrip().upper().startswith(CREATE_INDEX_PREFIX) and (
        MISSING_COLUMN_ERROR in str(exc).lower()
    )


async def close_db(conn: aiosqlite.Connection) -> None:
    await conn.close()
    logger.info("Database connection closed")


@asynccontextmanager
async def get_connection(db_path: str) -> AsyncGenerator[DatabaseHandle, None]:
    conn = await init_db(db_path)
    try:
        yield DatabaseHandle(conn)
    finally:
        await close_db(conn)


# Context-Local 数据库连接上下文变量
db_conn_var: ContextVar[DatabaseHandle] = ContextVar("db_connection")


@asynccontextmanager
async def db_session_scope(
    db_path: str | None = None,
) -> AsyncGenerator[DatabaseHandle, None]:
    """
    异步上下文管理器：生命周期内绑定一个独立的 aiosqlite.Connection 并绑定到 ContextVar 中。
    自动处理事务提交与回滚。
    """
    path = resolve_database_path(db_path)
    conn = await aiosqlite.connect(path)
    conn.row_factory = aiosqlite.Row
    for pragma in PRAGMA_STATEMENTS:
        await conn.execute(pragma)

    handle = DatabaseHandle(conn)
    token = db_conn_var.set(handle)
    try:
        yield handle
        await conn.commit()
    except Exception as exc:
        await conn.rollback()
        logger.error("数据库事务出错，已回滚: %s", exc)
        raise
    finally:
        db_conn_var.reset(token)
        await conn.close()


async def get_db_session() -> AsyncGenerator[DatabaseHandle, None]:
    """FastAPI 依赖注入项，为单个 HTTP 请求获取并隔离数据库连接。"""
    async with db_session_scope() as conn:
        yield conn
