"""后台店铺配置保存到小程序公开配置的端到端 smoke。"""

from __future__ import annotations

import os
import subprocess
import time
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
    fill_test_id,
    login_admin,
    npm_command,
    remove_existing_files,
    request_json,
    start_chrome,
    start_process,
    stop_processes,
    wait_for_expression,
    wait_for_http,
)

DB_PATH = REPORTS_DIR / "shop-settings-smoke.db"
SCREENSHOT_PATH = REPORTS_DIR / "shop-settings-smoke.png"
FAILURE_SCREENSHOT_PATH = REPORTS_DIR / "shop-settings-smoke-failure.png"
CHROME_PROFILE = REPORTS_DIR / "admin-decoration-page-switcher-chrome-profile"
TOKEN = "LOCAL_SHOP_SETTINGS_TOKEN"
BACKEND_PORT = 17004
ADMIN_PORT = 15176
BACKEND_URL = f"http://127.0.0.1:{BACKEND_PORT}"
ADMIN_URL = f"http://127.0.0.1:{ADMIN_PORT}/admin-v2/settings/shop"
CDP_PORT = 19227
TRACE_SUFFIX = "20260617"
SHOP_NAME = f"芸熙烘焙 smoke 店 {TRACE_SUFFIX}"
CUSTOMER_PHONE = "18800008888"
CUSTOMER_WECHAT = "yx-smoke-wechat"
BUSINESS_HOURS = "10:30-19:30"
PICKUP_ADDRESS = "smoke 自提点，后台配置同步验证"
DELIVERY_NOTICE = "smoke 配送说明，以下单后客服确认为准"
PICKUP_NOTICE = "smoke 自提说明，请提前联系门店"

logger = configure_logger("shop-settings-smoke")
processes: list[subprocess.Popen[Any]] = []


def miniapp_settings_match() -> bool:
    payload = request_json(f"{BACKEND_URL}/api/v1/miniapp/shop-settings")
    data = payload.get("data", {})
    return (
        data.get("shopName") == SHOP_NAME
        and data.get("customerPhone") == CUSTOMER_PHONE
        and data.get("customerWechat") == CUSTOMER_WECHAT
        and data.get("businessHours") == BUSINESS_HOURS
        and data.get("pickupAddress") == PICKUP_ADDRESS
        and data.get("deliveryNotice") == DELIVERY_NOTICE
        and data.get("pickupNotice") == PICKUP_NOTICE
    )


def wait_for_miniapp_settings(timeout_seconds: float = 20) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if miniapp_settings_match():
            return
        time.sleep(0.5)
    raise RuntimeError("小程序公开店铺配置未同步为后台保存值")


def fill_settings_form(cdp: CdpClient) -> None:
    fill_test_id(cdp, "shop-settings-shop-name", SHOP_NAME)
    fill_test_id(cdp, "shop-settings-customer-phone", CUSTOMER_PHONE)
    fill_test_id(cdp, "shop-settings-customer-wechat", CUSTOMER_WECHAT)
    fill_test_id(cdp, "shop-settings-business-hours", BUSINESS_HOURS)
    fill_test_id(cdp, "shop-settings-pickup-address", PICKUP_ADDRESS)
    fill_test_id(cdp, "shop-settings-delivery-notice", DELIVERY_NOTICE)
    fill_test_id(cdp, "shop-settings-pickup-notice", PICKUP_NOTICE)


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
            cdp, "document.querySelector('[data-testid=\"shop-settings-page\"]')"
        )
        wait_for_expression(
            cdp,
            "!document.querySelector('[data-testid=\"shop-settings-refresh\"]')?.classList.contains('is-loading')",
        )
        fill_settings_form(cdp)
        click_test_id(cdp, "shop-settings-save")
        wait_for_expression(cdp, "document.body.innerText.includes('店铺配置已保存')")
        wait_for_miniapp_settings()
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
        wait_for_http(ADMIN_URL)
        logger.info("running browser shop settings flow")
        cdp = run_browser_flow()
        logger.info("screenshot saved: %s", SCREENSHOT_PATH)
        logger.info("shop settings smoke passed")
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
