"""小程序下单到后台确认再回读小程序订单状态的端到端 smoke。"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from urllib.parse import quote
from typing import Any

from admin_smoke_utils import (
    ADMIN_ROOT,
    REPORTS_DIR,
    ROOT,
    CdpClient,
    capture_screenshot,
    click_test_id,
    configure_logger,
    connect_page,
    dump_process_tail,
    js_string,
    login_admin,
    npm_command,
    remove_existing_files,
    start_chrome,
    start_process,
    stop_processes,
    wait_for_expression,
    wait_for_http,
)

DB_PATH = REPORTS_DIR / "orders-confirmation-smoke.db"
SCREENSHOT_PATH = REPORTS_DIR / "orders-confirmation-smoke.png"
FAILURE_SCREENSHOT_PATH = REPORTS_DIR / "orders-confirmation-smoke-failure.png"
CHROME_PROFILE = REPORTS_DIR / "admin-decoration-page-switcher-chrome-profile"
TOKEN = "LOCAL_ORDERS_CONFIRM_TOKEN"
BACKEND_PORT = 17003
ADMIN_PORT = 15175
BACKEND_URL = f"http://127.0.0.1:{BACKEND_PORT}"
ADMIN_URL = f"http://127.0.0.1:{ADMIN_PORT}/admin-v2/orders"
CDP_PORT = 19226
MINIAPP_USER_ID = "smoke-order-user"
PRODUCT_ID = "order-smoke-product"
PRODUCT_TITLE = "smoke order strawberry tart"
ORDER_STATUS_SEQUENCE: list[tuple[str, str]] = [
    ("confirmed", "已确认"),
    ("making", "制作中"),
    ("delivering", "配送中"),
    ("done", "已完成"),
]

logger = configure_logger("orders-confirm-smoke")
processes: list[subprocess.Popen[Any]] = []


def post_json(
    url: str, payload: dict[str, Any], headers: dict[str, str] | None = None
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def create_miniapp_order() -> str:
    payload = post_json(
        f"{BACKEND_URL}/api/v1/miniapp/orders",
        {
            "items": [
                {
                    "productId": PRODUCT_ID,
                    "title": PRODUCT_TITLE,
                    "priceFen": 26800,
                    "quantity": 1,
                }
            ],
            "receiverName": "订单烟测",
            "receiverPhone": "18800001234",
            "deliveryType": "pickup",
            "deliveryAddress": "",
            "expectTime": "2026-06-18 18:00",
            "remark": "后台确认 smoke",
        },
        headers={"x-miniapp-user-id": MINIAPP_USER_ID},
    )
    order_id = str(payload["data"]["orderId"])
    logger.info("created miniapp order %s", order_id)
    return order_id


def miniapp_order_status(order_id: str) -> str:
    payload = get_json(
        f"{BACKEND_URL}/api/v1/miniapp/orders/{order_id}",
        headers={"x-miniapp-user-id": MINIAPP_USER_ID},
    )
    return str(payload["data"]["status"])


def wait_for_miniapp_status(
    order_id: str, status: str, timeout_seconds: float = 20
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if miniapp_order_status(order_id) == status:
            return
        time.sleep(0.5)
    raise RuntimeError(f"小程序订单状态未达到期望: {order_id} expected={status}")


def wait_for_order_row(cdp: CdpClient, order_id: str) -> None:
    wait_for_expression(
        cdp, f"document.querySelector('[data-testid=\"orders-row-title-{order_id}\"]')"
    )
    wait_for_expression(
        cdp, f"document.body.innerText.includes({js_string(PRODUCT_TITLE)})"
    )


def wait_for_order_row_status(cdp: CdpClient, order_id: str, status: str) -> None:
    wait_for_expression(
        cdp, f"document.querySelector('[data-testid=\"orders-row-status-{order_id}\"]')"
    )
    wait_for_expression(
        cdp,
        f"document.querySelector('[data-testid=\"orders-row-status-{order_id}\"]').innerText.includes({js_string(status)})",
    )


def wait_for_order_detail_status(cdp: CdpClient, order_id: str, status: str) -> None:
    wait_for_expression(
        cdp,
        f"document.querySelector('[data-testid=\"orders-detail-status-{order_id}\"]')",
    )
    wait_for_expression(
        cdp,
        f"document.querySelector('[data-testid=\"orders-detail-status-{order_id}\"]').innerText.includes({js_string(status)})",
    )


def run_browser_flow(order_id: str) -> CdpClient:
    start_chrome(cdp_port=CDP_PORT, profile_dir=CHROME_PROFILE, processes=processes)
    cdp = connect_page(CDP_PORT)
    try:
        cdp.send(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1366, "height": 900, "deviceScaleFactor": 1, "mobile": False},
        )
        login_admin(
            cdp,
            f"{ADMIN_URL}?keyword={quote(order_id)}&status=pending",
            TOKEN,
        )
        cdp.send(
            "Page.navigate",
            {"url": f"{ADMIN_URL}?keyword={quote(order_id)}&status=pending"},
        )
        wait_for_expression(
            cdp, "document.querySelector('[data-testid=\"orders-page\"]')"
        )
        wait_for_order_row(cdp, order_id)
        wait_for_miniapp_status(order_id, "pending")

        for status, label in ORDER_STATUS_SEQUENCE:
            click_test_id(cdp, f"orders-update-status-{order_id}-{status}")
            wait_for_expression(
                cdp,
                f"document.body.innerText.includes({js_string(f'订单已更新为{label}')})",
            )
            wait_for_order_row_status(cdp, order_id, label)
            wait_for_miniapp_status(order_id, status)

        click_test_id(cdp, f"orders-open-detail-{order_id}")
        wait_for_order_detail_status(cdp, order_id, "已完成")
        capture_screenshot(cdp, SCREENSHOT_PATH)
    except Exception:
        capture_screenshot(cdp, FAILURE_SCREENSHOT_PATH)
        test_ids = cdp.eval(
            """
            Array.from(document.querySelectorAll('[data-testid]'))
              .map((node) => node.getAttribute('data-testid'))
              .slice(0, 80)
            """
        )
        body_text = cdp.eval("document.body.innerText.slice(0, 1000)")
        logger.info("failure screenshot saved: %s", FAILURE_SCREENSHOT_PATH)
        logger.info("visible test ids: %s", test_ids)
        logger.info("body text head: %s", body_text)
        raise
    return cdp


def cleanup_files() -> None:
    remove_existing_files(
        [
            DB_PATH.with_name(f"{DB_PATH.name}-shm"),
            DB_PATH.with_name(f"{DB_PATH.name}-wal"),
            DB_PATH,
        ]
    )


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "DB_PATH": str(DB_PATH),
            "ADMIN_API_TOKEN": TOKEN,
            "ADMIN_SESSION_SECRET": "local-admin-session-secret",
            "ADMIN_COOKIE_SECURE": "false",
            "ADMIN_ALLOWED_ORIGINS": f"http://127.0.0.1:{ADMIN_PORT}",
            "ADMIN_ALLOW_LEGACY_BEARER": "true",
            "STOREFRONT_AUTH_ALLOW_LEGACY_HEADER": "true",
            "ALLOW_MOCK_PAYMENT": "true",
            "VITE_API_TARGET": BACKEND_URL,
            "VITE_API_BASE": "/api/v1/admin",
            "VITE_ROUTER_BASE": "/admin-v2/",
        }
    )
    os.environ.update(env)
    backend: subprocess.Popen[str] | None = None
    vite: subprocess.Popen[str] | None = None
    cdp: CdpClient | None = None
    try:
        logger.info("starting backend and admin dev server")
        backend = start_process(
            [
                "python",
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(BACKEND_PORT),
            ],
            cwd=ROOT,
            env=env,
            label="backend",
            processes=processes,
            logger=logger,
        )
        vite = start_process(
            [
                npm_command(),
                "run",
                "dev",
                "--",
                "--host",
                "127.0.0.1",
                "--port",
                str(ADMIN_PORT),
                "--strictPort",
            ],
            cwd=ADMIN_ROOT,
            env=env,
            label="vite",
            processes=processes,
            logger=logger,
        )
        wait_for_http(f"{BACKEND_URL}/health")
        order_id = create_miniapp_order()
        wait_for_http(f"{ADMIN_URL}?keyword={quote(order_id)}&status=pending")
        logger.info("running browser order confirmation flow")
        cdp = run_browser_flow(order_id)
        logger.info("screenshot saved: %s", SCREENSHOT_PATH)
        logger.info("orders confirmation smoke passed")
    except Exception:
        if backend is not None:
            dump_process_tail(backend, "backend", logger)
        if vite is not None:
            dump_process_tail(vite, "vite", logger)
        raise
    finally:
        if cdp is not None:
            cdp.close()
        stop_processes(processes)
        cleanup_files()


if __name__ == "__main__":
    main()
