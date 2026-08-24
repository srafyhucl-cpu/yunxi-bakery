"""后台手机端轻量运营入口 smoke。"""

from __future__ import annotations

import os
import subprocess
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
    login_admin,
    npm_command,
    remove_existing_files,
    start_chrome,
    start_process,
    stop_processes,
    wait_for_expression,
    wait_for_http,
)

DB_PATH = REPORTS_DIR / "mobile-operations-smoke.db"
SCREENSHOT_PATH = REPORTS_DIR / "mobile-operations-smoke.png"
FAILURE_SCREENSHOT_PATH = REPORTS_DIR / "mobile-operations-smoke-failure.png"
CHROME_PROFILE = REPORTS_DIR / "mobile-operations-chrome-profile"
TOKEN = "LOCAL_MOBILE_OPERATIONS_TOKEN"
BACKEND_PORT = 17008
ADMIN_PORT = 15180
BACKEND_URL = f"http://127.0.0.1:{BACKEND_PORT}"
ADMIN_URL = f"http://127.0.0.1:{ADMIN_PORT}/admin-v2/overview"
CDP_PORT = 19231

logger = configure_logger("mobile-ops-smoke")
processes: list[subprocess.Popen[Any]] = []


def run_browser_flow() -> CdpClient:
    start_chrome(cdp_port=CDP_PORT, profile_dir=CHROME_PROFILE, processes=processes)
    cdp = connect_page(CDP_PORT)
    try:
        cdp.send(
            "Emulation.setDeviceMetricsOverride",
            {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True},
        )
        login_admin(cdp, ADMIN_URL, TOKEN)
        cdp.send("Page.navigate", {"url": ADMIN_URL})
        wait_for_expression(
            cdp, "document.querySelector('[data-testid=\"overview-mobile-ops\"]')"
        )
        for test_id in [
            "bottom-nav-overview",
            "bottom-nav-products",
            "bottom-nav-orders",
            "bottom-nav-transfers",
            "bottom-nav-settings",
        ]:
            wait_for_expression(
                cdp, f"document.querySelector('[data-testid=\"{test_id}\"]')"
            )

        click_test_id(cdp, "bottom-nav-orders")
        wait_for_expression(cdp, "location.href.includes('/admin-v2/orders')")
        wait_for_expression(
            cdp, "document.querySelector('[data-testid=\"orders-page\"]')"
        )

        click_test_id(cdp, "bottom-nav-products")
        wait_for_expression(cdp, "location.href.includes('/admin-v2/products')")
        wait_for_expression(
            cdp, "document.querySelector('[data-testid=\"products-page\"]')"
        )

        click_test_id(cdp, "bottom-nav-transfers")
        wait_for_expression(cdp, "location.href.includes('/admin-v2/transfers')")
        wait_for_expression(
            cdp, "document.querySelector('[data-testid=\"transfers-page\"]')"
        )

        click_test_id(cdp, "bottom-nav-settings")
        wait_for_expression(cdp, "location.href.includes('/admin-v2/settings/shop')")
        wait_for_expression(
            cdp, "document.querySelector('[data-testid=\"shop-settings-page\"]')"
        )

        click_test_id(cdp, "bottom-nav-overview")
        wait_for_expression(cdp, "location.href.includes('/admin-v2/overview')")
        wait_for_expression(
            cdp, "document.querySelector('[data-testid=\"overview-mobile-ops\"]')"
        )
        capture_screenshot(cdp, SCREENSHOT_PATH)
    except Exception:
        capture_screenshot(cdp, FAILURE_SCREENSHOT_PATH)
        test_ids = cdp.eval(
            """
            Array.from(document.querySelectorAll('[data-testid]'))
              .map((node) => node.getAttribute('data-testid'))
              .slice(0, 120)
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
            "YUNXI_USE_FAKE_EMBEDDING": "1",
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
        logger.info("running browser mobile operations flow")
        cdp = run_browser_flow()
        logger.info("screenshot saved: %s", SCREENSHOT_PATH)
        logger.info("mobile operations smoke passed")
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
