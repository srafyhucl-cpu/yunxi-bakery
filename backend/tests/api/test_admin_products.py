from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.admin_products import create_admin_products_router


class FakeReconcileService:
    async def run(self) -> dict[str, object]:
        return {
            "checked": 3,
            "deactivated": 1,
            "deactivated_ids": [202],
            "errors": [],
        }


class FakeKnowledgeSyncService:
    async def sync_all_pending(self) -> dict[str, object]:
        return {"synced": 2, "failed": 0}


def test_admin_products_reconcile_syncs_vectors_and_merges_result(
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.api.admin_products.verify_token", lambda: None)
    app = FastAPI()
    app.include_router(
        create_admin_products_router(
            FakeReconcileService(),  # type: ignore[arg-type]
            FakeKnowledgeSyncService(),  # type: ignore[arg-type]
        )
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/admin/products/reconcile",
        headers={"Authorization": "Bearer token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "code": 0,
        "data": {
            "checked": 3,
            "deactivated": 1,
            "deactivated_ids": [202],
            "errors": [],
            "vector_sync": {"synced": 2, "failed": 0},
        },
    }
