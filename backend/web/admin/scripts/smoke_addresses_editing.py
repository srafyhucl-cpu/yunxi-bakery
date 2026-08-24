"""后台顾客地址新增编辑端到端 smoke。"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from typing import Any
from urllib.parse import quote

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
    fill_test_id,
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

DB_PATH = REPORTS_DIR / "addresses-editing-smoke.db"
SCREENSHOT_PATH = REPORTS_DIR / "addresses-editing-smoke.png"
FAILURE_SCREENSHOT_PATH = REPORTS_DIR / "addresses-editing-smoke-failure.png"
CHROME_PROFILE = REPORTS_DIR / "addresses-editing-chrome-profile"
TOKEN = "LOCAL_ADDRESSES_EDITING_TOKEN"
BACKEND_PORT = 17005
ADMIN_PORT = 15177
BACKEND_URL = f"http://127.0.0.1:{BACKEND_PORT}"
ADMIN_URL = f"http://127.0.0.1:{ADMIN_PORT}/admin-v2/addresses"
CDP_PORT = 19228
TRACE_SUFFIX = "20260617"
USER_ID = f"smoke-address-user-{TRACE_SUFFIX}"
RECEIVER_NAME = "地址烟测新增"
RECEIVER_PHONE = "18800007777"
ADDRESS_TEXT = "smoke 地址新增路 77 号"
UPDATED_NAME = "地址烟测已编辑"
UPDATED_ADDRESS_TEXT = "smoke 地址编辑后 88 号"

logger = configure_logger("addresses-editing-smoke")
processes: list[subprocess.Popen[Any]] = []


def get_admin_addresses(keyword: str) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        f"{BACKEND_URL}/api/v1/admin/addresses?keyword={quote(keyword)}",
        headers={"Authorization": f"Bearer {TOKEN}"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return list(payload.get("data", {}).get("items", []))


def wait_for_admin_address(
    *,
    keyword: str,
    receiver_name: str,
    address_text: str,
    timeout_seconds: float = 20,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for item in get_admin_addresses(keyword):
            if (
                item.get("receiverName") == receiver_name
                and item.get("address") == address_text
            ):
                return item
        time.sleep(0.5)
    raise RuntimeError(f"后台地址未达到期望: {receiver_name} / {address_text}")


def get_miniapp_addresses() -> list[dict[str, Any]]:
    request = urllib.request.Request(
        f"{BACKEND_URL}/api/v1/miniapp/addresses",
        headers={"x-miniapp-user-id": USER_ID},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return list(payload.get("data", []))


def wait_for_miniapp_address(receiver_name: str, timeout_seconds: float = 20) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        items = get_miniapp_addresses()
        if any(item.get("receiverName") == receiver_name for item in items):
            return
        time.sleep(0.5)
    raise RuntimeError("小程序地址簿未读取到后台维护的地址")


def fill_address_form(
    cdp: CdpClient, *, name: str, phone: str, address: str, user_id: str | None = None
) -> None:
    if user_id is not None:
        fill_test_id(cdp, "addresses-form-user-id", user_id)
    fill_test_id(cdp, "addresses-form-receiver-name", name)
    fill_test_id(cdp, "addresses-form-receiver-phone", phone)
    fill_test_id(cdp, "addresses-form-address", address)


def run_browser_flow() -> CdpClient:
    start_chrome(cdp_port=CDP_PORT, profile_dir=CHROME_PROFILE, processes=processes)
    cdp = connect_page(CDP_PORT)
    try:
        cdp.send(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1366, "height": 900, "deviceScaleFactor": 1, "mobile": False},
        )
        login_admin(cdp, ADMIN_URL, TOKEN)
        cdp.send("Page.navigate", {"url": ADMIN_URL})
        wait_for_expression(
            cdp, "document.querySelector('[data-testid=\"addresses-page\"]')"
        )

        click_test_id(cdp, "addresses-create")
        wait_for_expression(
            cdp, "document.querySelector('[data-testid=\"addresses-form-drawer\"]')"
        )
        fill_address_form(
            cdp,
            user_id=USER_ID,
            name=RECEIVER_NAME,
            phone=RECEIVER_PHONE,
            address=ADDRESS_TEXT,
        )
        click_test_id(cdp, "addresses-form-default")
        click_test_id(cdp, "addresses-form-submit")
        wait_for_expression(cdp, "document.body.innerText.includes('地址已新增')")
        created = wait_for_admin_address(
            keyword=USER_ID, receiver_name=RECEIVER_NAME, address_text=ADDRESS_TEXT
        )

        fill_test_id(cdp, "addresses-search-input", USER_ID)
        click_test_id(cdp, "addresses-search-submit")
        wait_for_expression(
            cdp, f"document.body.innerText.includes({js_string(RECEIVER_NAME)})"
        )

        click_test_id(cdp, f"addresses-edit-{created['id']}")
        wait_for_expression(
            cdp, "document.querySelector('[data-testid=\"addresses-form-drawer\"]')"
        )
        fill_address_form(
            cdp, name=UPDATED_NAME, phone=RECEIVER_PHONE, address=UPDATED_ADDRESS_TEXT
        )
        click_test_id(cdp, "addresses-form-submit")
        wait_for_expression(cdp, "document.body.innerText.includes('地址已保存')")
        wait_for_admin_address(
            keyword=USER_ID,
            receiver_name=UPDATED_NAME,
            address_text=UPDATED_ADDRESS_TEXT,
        )
        wait_for_miniapp_address(UPDATED_NAME)

        fill_test_id(cdp, "addresses-search-input", USER_ID)
        click_test_id(cdp, "addresses-search-submit")
        wait_for_expression(
            cdp, f"document.body.innerText.includes({js_string(UPDATED_NAME)})"
        )
        click_test_id(cdp, f"addresses-open-detail-{created['id']}")
        wait_for_expression(
            cdp, "document.querySelector('[data-testid=\"addresses-audit-section\"]')"
        )
        wait_for_expression(cdp, "document.body.innerText.includes('后台编辑地址')")
        wait_for_expression(cdp, "document.body.innerText.includes('最近操作')")
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
        wait_for_http(ADMIN_URL)
        logger.info("running browser addresses editing flow")
        cdp = run_browser_flow()
        logger.info("screenshot saved: %s", SCREENSHOT_PATH)
        logger.info("addresses editing smoke passed")
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
