"""
轻量级数据库迁移执行器。

管理版本化的 Schema 演进：
- 迁移文件按编号命名：migrations/v001_*.sql、v002_*.sql
- 在数据库中维护 _schema_version 表记录当前版本
- init_db() 完成建表后按序执行未应用的迁移
"""

import os
from pathlib import Path

import aiosqlite

from app.logger import setup_logger

logger = setup_logger()

MIGRATIONS_DIR = Path(__file__).resolve().parent


async def _ensure_version_table(conn: aiosqlite.Connection) -> None:
    """创建 _schema_version 表（如果不存在）。"""
    await conn.execute(
        """CREATE TABLE IF NOT EXISTS _schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT DEFAULT (datetime('now'))
        )"""
    )
    await conn.commit()


async def _get_applied_versions(conn: aiosqlite.Connection) -> set[int]:
    """查询已应用的迁移版本号。"""
    async with conn.execute("SELECT version FROM _schema_version") as cursor:
        rows = await cursor.fetchall()
    return {row["version"] for row in rows}


def _discover_migrations() -> list[tuple[int, str, str]]:
    """扫描 migrations/ 目录，返回 (版本号, 文件名, 文件路径) 排序列表。"""
    migrations: list[tuple[int, str, str]] = []
    if not MIGRATIONS_DIR.is_dir():
        return migrations
    for fname in sorted(os.listdir(MIGRATIONS_DIR)):
        if not fname.endswith(".sql") or not (
            fname[0].isdigit() or fname[0].lower() == "v"
        ):
            continue
        # 提取 v001_xxx.sql 中的版本号
        try:
            version = int(fname.split("_")[0].lstrip("vV"))
        except (ValueError, IndexError):
            continue
        fpath = MIGRATIONS_DIR / fname
        migrations.append((version, fname, str(fpath)))
    migrations.sort(key=lambda x: x[0])
    return migrations


async def run_migrations(conn: aiosqlite.Connection) -> int:
    """
    执行所有未应用的增量迁移。

    返回本次新应用的迁移数量。
    """
    await _ensure_version_table(conn)
    applied = await _get_applied_versions(conn)
    pending = _discover_migrations()
    count = 0

    for version, fname, fpath in pending:
        if version in applied:
            continue
        sql_path = Path(fpath)
        if not sql_path.exists():
            logger.warning("迁移文件不存在，跳过: %s", fname)
            continue
        try:
            sql_content = sql_path.read_text(encoding="utf-8")
            # 逐条执行 SQL 语句，容忍 duplicate column 错误
            for stmt in _split_sql_statements(sql_content):
                if not stmt.strip():
                    continue
                try:
                    await conn.execute(stmt)
                except aiosqlite.OperationalError as exc:
                    if (
                        "duplicate column" in str(exc).lower()
                        or "already exists" in str(exc).lower()
                    ):
                        logger.debug("跳过已存在的列/索引（幂等）: %s", exc)
                        continue
                    raise
            await conn.execute(
                "INSERT INTO _schema_version (version) VALUES (?)", (version,)
            )
            await conn.commit()
            logger.info("已完成迁移: %s (版本 %d)", fname, version)
            count += 1
        except Exception as exc:
            logger.error("迁移执行失败 %s: %s", fname, exc)
            raise

    if count > 0:
        logger.info("共完成 %d 个迁移", count)
    return count


def _split_sql_statements(sql: str) -> list[str]:
    """简单按分号拆分 SQL 语句（不处理字符串内的分号）。"""
    statements = []
    current = []
    for line in sql.splitlines():
        line = line.strip()
        if not line or line.startswith("--"):
            continue
        current.append(line)
        if line.endswith(";"):
            statements.append(" ".join(current))
            current = []
    if current:
        statements.append(" ".join(current))
    return statements
