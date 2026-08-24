"""小程序主体隐私权利 API 合同测试。"""

import httpx
import pytest
from fastapi import FastAPI

from app.api.channels.storefront.privacy import create_storefront_privacy_router
from app.repository.customer_profile_repo import CustomerProfileRepo
from app.repository.privacy_repo import PrivacyRepo
from app.service.customer_consent import CustomerConsentService
from app.service.privacy_lifecycle import PrivacyLifecycleService
from tests.helpers.storefront_auth import storefront_auth_headers


@pytest.mark.asyncio
async def test_subject_export_and_delete_api_uses_authenticated_user_scope(db) -> None:
    await db.execute(
        "INSERT INTO sessions (id, channel, user_id) VALUES (?, ?, ?)",
        ("api-privacy-session", "miniapp", "api-privacy-user"),
    )
    await db.execute(
        "INSERT INTO messages (id, session_id, role, content) VALUES (?, ?, ?, ?)",
        ("api-privacy-message", "api-privacy-session", "user", "隐私记录"),
    )
    await db.commit()

    app = FastAPI()
    app.include_router(
        create_storefront_privacy_router(
            CustomerConsentService(CustomerProfileRepo(db)),
            PrivacyLifecycleService(PrivacyRepo(db)),
        )
    )
    transport = httpx.ASGITransport(app=app)
    headers = storefront_auth_headers("api-privacy-user")
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        exported = await client.get(
            "/api/v1/miniapp/privacy/subject/export", headers=headers
        )
        deleted = await client.delete(
            "/api/v1/miniapp/privacy/subject", headers=headers
        )

    assert exported.status_code == 200
    assert len(exported.json()["data"]["records"]["messages"]) == 1
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "revoked"
