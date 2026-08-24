"""后台订单经营看板 summary 浏览器 smoke。"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.parse
import urllib.request
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

DB_PATH = REPORTS_DIR / "orders-summary-smoke.db"
SCREENSHOT_PATH = REPORTS_DIR / "orders-summary-smoke.png"
FAILURE_SCREENSHOT_PATH = REPORTS_DIR / "orders-summary-smoke-failure.png"
CHROME_PROFILE = REPORTS_DIR / "orders-summary-chrome-profile"
TOKEN = "LOCAL_ORDERS_SUMMARY_TOKEN"
BACKEND_PORT = 17006
ADMIN_PORT = 15178
BACKEND_URL = f"http://127.0.0.1:{BACKEND_PORT}"
ADMIN_URL = f"http://127.0.0.1:{ADMIN_PORT}/admin-v2/orders"
CDP_PORT = 19229
TRACE_KEY = "smoke-order-summary-20260617"
PENDING_USER = "summary-smoke-pending-user"
FULFILLING_USER = "summary-smoke-fulfilling-user"
CLOSED_USER = "summary-smoke-closed-user"

logger = configure_logger("orders-summary-smoke")
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


def create_order(*, title: str, price_fen: int, user_id: str) -> str:
    payload = post_json(
        f"{BACKEND_URL}/api/v1/miniapp/orders",
        {
            "items": [
                {
                    "productId": title.replace(" ", "-"),
                    "title": title,
                    "priceFen": price_fen,
                    "quantity": 1,
                }
            ],
            "receiverName": "订单看板烟测",
            "receiverPhone": "18800006666",
            "deliveryType": "pickup",
            "deliveryAddress": "",
            "expectTime": "2026-06-18 18:00",
            "remark": TRACE_KEY,
        },
        headers={"x-miniapp-user-id": user_id},
    )
    order_id = str(payload["data"]["orderId"])
    logger.info("created order %s title=%s", order_id, title)
    return order_id


def seed_orders() -> dict[str, str]:
    pending_id = create_order(
        title=f"{TRACE_KEY} 待支付蛋糕",
        price_fen=12800,
        user_id=PENDING_USER,
    )
    fulfilling_id = create_order(
        title=f"{TRACE_KEY} 履约中蛋糕",
        price_fen=22800,
        user_id=FULFILLING_USER,
    )
    closed_id = create_order(
        title=f"{TRACE_KEY} 已关闭蛋糕",
        price_fen=32800,
        user_id=CLOSED_USER,
    )
    admin_headers = {"Authorization": f"Bearer {TOKEN}"}
    post_json(
        f"{BACKEND_URL}/api/v1/admin/orders/{fulfilling_id}/status",
        {"status": "confirmed"},
        headers=admin_headers,
    )
    post_json(
        f"{BACKEND_URL}/api/v1/miniapp/orders/{fulfilling_id}/mock-pay",
        {},
        headers={"x-miniapp-user-id": FULFILLING_USER},
    )
    post_json(
        f"{BACKEND_URL}/api/v1/admin/orders/{closed_id}/expire-unpaid",
        {},
        headers=admin_headers,
    )
    return {"pending": pending_id, "fulfilling": fulfilling_id, "closed": closed_id}


def wait_for_summary_count(count: int, timeout_seconds: float = 20) -> None:
    query = urllib.parse.urlencode({"keyword": TRACE_KEY})
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        payload = get_json(
            f"{BACKEND_URL}/api/v1/admin/orders/summary?{query}",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        if int(payload.get("data", {}).get("totalCount", 0)) == count:
            return
        time.sleep(0.5)
    raise RuntimeError("后台订单 summary 未达到期望数量")


def body_includes(cdp: CdpClient, text: str) -> str:
    return f"document.body.innerText.includes({js_string(text)})"


def wait_for_row(cdp: CdpClient, order_id: str) -> None:
    wait_for_expression(
        cdp, f"document.querySelector('[data-testid=\"orders-row-title-{order_id}\"]')"
    )


def wait_for_row_absent(cdp: CdpClient, order_id: str) -> None:
    wait_for_expression(
        cdp, f"!document.querySelector('[data-testid=\"orders-row-title-{order_id}\"]')"
    )


def wait_for_board_card(cdp: CdpClient, key: str, count_text: str) -> None:
    selector = f'[data-testid="orders-board-filter-{key}"]'
    wait_for_expression(cdp, f"document.querySelector({js_string(selector)})")
    wait_for_expression(
        cdp,
        f"document.querySelector({js_string(selector)}).innerText.includes({js_string(count_text)})",
    )


def run_browser_flow(order_ids: dict[str, str]) -> CdpClient:
    start_chrome(cdp_port=CDP_PORT, profile_dir=CHROME_PROFILE, processes=processes)
    cdp = connect_page(CDP_PORT)
    try:
        cdp.send(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1366, "height": 900, "deviceScaleFactor": 1, "mobile": False},
        )
        url = f"{ADMIN_URL}?{urllib.parse.urlencode({'keyword': TRACE_KEY})}"
        login_admin(cdp, url, TOKEN)
        cdp.send("Page.navigate", {"url": url})
        wait_for_expression(
            cdp, "document.querySelector('[data-testid=\"orders-page\"]')"
        )
        wait_for_expression(
            cdp, "document.querySelector('[data-testid=\"orders-board\"]')"
        )
        wait_for_board_card(cdp, "all", "3")
        wait_for_board_card(cdp, "unpaid", "1")
        wait_for_board_card(cdp, "fulfilling", "1")
        wait_for_board_card(cdp, "closed", "1")
        wait_for_expression(cdp, body_includes(cdp, "全量 3 单"))
        wait_for_row(cdp, order_ids["pending"])
        wait_for_row(cdp, order_ids["fulfilling"])
        wait_for_row(cdp, order_ids["closed"])

        click_test_id(cdp, "orders-board-filter-fulfilling")
        wait_for_row(cdp, order_ids["fulfilling"])
        wait_for_row_absent(cdp, order_ids["pending"])
        wait_for_row_absent(cdp, order_ids["closed"])

        click_test_id(cdp, "orders-board-filter-closed")
        wait_for_row(cdp, order_ids["closed"])
        wait_for_row_absent(cdp, order_ids["pending"])
        wait_for_row_absent(cdp, order_ids["fulfilling"])

        capture_screenshot(cdp, SCREENSHOT_PATH)
    except Exception:
        capture_screenshot(cdp, FAILURE_SCREENSHOT_PATH)
        test_ids = cdp.eval(
            """
            Array.from(document.querySelectorAll('[data-testid]'))
              .map((node) => node.getAttribute('data-testid'))
              .slice(0, 100)
            """
        )
        body_text = cdp.eval("document.body.innerText.slice(0, 1200)")
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
        order_ids = seed_orders()
        wait_for_summary_count(3)
        wait_for_http(f"{ADMIN_URL}?{urllib.parse.urlencode({'keyword': TRACE_KEY})}")
        logger.info("running browser order summary board flow")
        cdp = run_browser_flow(order_ids)
        logger.info("screenshot saved: %s", SCREENSHOT_PATH)
        logger.info("orders summary smoke passed")
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
