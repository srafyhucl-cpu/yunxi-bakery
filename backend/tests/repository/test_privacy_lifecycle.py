"""主体隐私导出、删除与保留期仓库合同测试。"""

import pytest
from datetime import datetime

from app.repository.privacy_repo import PrivacyRepo
from app.service.privacy_lifecycle import (
    PrivacyLifecycleService,
    PrivacyRetentionPolicy,
)


@pytest.mark.asyncio
async def test_subject_export_and_delete_covers_linked_records(db) -> None:
    await db.execute(
        "INSERT INTO sessions (id, channel, user_id) VALUES (?, ?, ?)",
        ("privacy-session", "miniapp", "privacy-user"),
    )
    await db.execute(
        "INSERT INTO messages (id, session_id, role, content) VALUES (?, ?, ?, ?)",
        ("privacy-message", "privacy-session", "user", "手机号 13812345678"),
    )
    await db.execute(
        "INSERT INTO customer_profiles (id, channel, user_id, display_name) "
        "VALUES (?, ?, ?, ?)",
        ("privacy-profile", "miniapp", "privacy-user", "测试用户"),
    )
    await db.execute(
        "INSERT INTO customer_consent_ledger (channel, user_id, status) "
        "VALUES (?, ?, ?)",
        ("miniapp", "privacy-user", "granted"),
    )
    await db.execute(
        "INSERT INTO miniapp_addresses (id, user_id, receiver_name, receiver_phone, address) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            "privacy-address",
            "privacy-user",
            "测试用户",
            "13812345678",
            "北京市幸福路1号",
        ),
    )
    await db.execute(
        "INSERT INTO orders (id, session_id, channel, user_id, products) "
        "VALUES (?, ?, ?, ?, ?)",
        ("privacy-order", "privacy-session", "miniapp", "privacy-user", "[]"),
    )
    await db.execute(
        "INSERT INTO customer_master (id, tenant_id, primary_phone, display_name) "
        "VALUES (?, ?, ?, ?)",
        ("privacy-customer", "default", "13812345678", "测试用户"),
    )
    await db.execute(
        "INSERT INTO customer_identity_links "
        "(id, tenant_id, customer_id, identity_type, identity_value, source_system) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            "privacy-identity",
            "default",
            "privacy-customer",
            "miniapp_openid",
            "privacy-user",
            "miniapp",
        ),
    )
    await db.commit()

    service = PrivacyLifecycleService(PrivacyRepo(db))
    exported = await service.export_subject("privacy-user")
    assert len(exported["records"]["messages"]) == 1
    assert len(exported["records"]["orders"]) == 1
    assert len(exported["records"]["addresses"]) == 1
    assert len(exported["records"]["customer_master"]) == 1

    await service.delete_subject("privacy-user")
    remaining = await db.execute_fetchall(
        "SELECT COUNT(*) AS count FROM messages WHERE session_id = ?",
        ("privacy-session",),
    )
    consent = await db.execute_fetchall(
        "SELECT status FROM customer_consent_ledger WHERE user_id = ?",
        ("privacy-user",),
    )
    assert remaining[0]["count"] == 0
    assert consent[0]["status"] == "revoked"
    customer_rows = await db.execute_fetchall(
        "SELECT COUNT(*) AS count FROM customer_master WHERE id = ?",
        ("privacy-customer",),
    )
    assert customer_rows[0]["count"] == 0


@pytest.mark.asyncio
async def test_purge_expired_uses_explicit_retention_cutoffs(db) -> None:
    await db.execute(
        "INSERT INTO knowledge_retrieval_logs "
        "(bot_type, audience, query, query_hash, query_category, retrieval_mode, "
        "created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "customer",
            "customer",
            "",
            "hash",
            "other",
            "keyword_only",
            "2020-01-01 00:00:00",
        ),
    )
    await db.commit()

    service = PrivacyLifecycleService(PrivacyRepo(db))
    deleted = await service.purge_expired(
        now=datetime(2026, 1, 1),
        policy=PrivacyRetentionPolicy(retrieval_logs_days=30),
    )

    assert deleted["retrieval_logs"] == 1
