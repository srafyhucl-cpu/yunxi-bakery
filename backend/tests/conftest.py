"""
共享测试夹具。

提供内存 SQLite 连接，每个测试函数独享一个完整 schema 的干净数据库
（包含动态迁移列），测试结束后自动关闭，互不干扰。
"""

import os
from collections.abc import AsyncGenerator

import aiosqlite
import pytest

# 测试统一使用轻量编码器，规避真实 Embedding 模型每次构造耗时约 18 秒的加载成本。
# 必须在任何 app 模块导入前设置，确保首个 EmbeddingSearcher 即走 fallback 分支。
os.environ.setdefault("YUNXI_USE_FAKE_EMBEDDING", "1")
os.environ.setdefault("STOREFRONT_AUTH_SECRET", "test-storefront-auth-secret")
os.environ.setdefault("STOREFRONT_AUTH_ALLOW_LEGACY_HEADER", "0")
os.environ.setdefault("ALLOW_MOCK_PAYMENT", "1")
os.environ.setdefault("ADMIN_SESSION_SECRET", "test-admin-session-secret")
os.environ.setdefault("ADMIN_ALLOW_LEGACY_BEARER", "1")
os.environ.setdefault("ADMIN_COOKIE_SECURE", "0")

from app.database import close_db, init_db


@pytest.fixture
async def db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """每个测试独享的内存 SQLite 连接，通过 init_db 完整初始化（含动态迁移）。"""
    conn = await init_db(":memory:")
    yield conn
    await close_db(conn)
