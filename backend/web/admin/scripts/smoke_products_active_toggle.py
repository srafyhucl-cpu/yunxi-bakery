"""后台商品上下架到小程序商品目录的端到端 smoke。"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
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
    request_json,
    start_chrome,
    start_process,
    stop_processes,
    wait_for_expression,
    wait_for_http,
)

DB_PATH = REPORTS_DIR / "products-active-toggle-smoke.db"
SCREENSHOT_PATH = REPORTS_DIR / "products-active-toggle-smoke.png"
FAILURE_SCREENSHOT_PATH = REPORTS_DIR / "products-active-toggle-smoke-failure.png"
CHROME_PROFILE = REPORTS_DIR / "admin-decoration-page-switcher-chrome-profile"
TOKEN = "LOCAL_PRODUCTS_ACTIVE_TOKEN"
BACKEND_PORT = 17002
ADMIN_PORT = 15174
BACKEND_URL = f"http://127.0.0.1:{BACKEND_PORT}"
ADMIN_URL = f"http://127.0.0.1:{ADMIN_PORT}/admin-v2/products"
CDP_PORT = 19225
PRODUCT_ID = "92017004"
PRODUCT_TITLE = "smoke active cheesecake"
PRODUCT_QUERY = quote(PRODUCT_TITLE)

logger = configure_logger("products-active-smoke")
processes: list[subprocess.Popen[Any]] = []


async def seed_catalog() -> None:
    sys.path.insert(0, str(ROOT))
    from app.database import init_db
    from tests.helpers.miniapp_catalog_seed import seed_miniapp_product

    db = await init_db(str(DB_PATH))
    try:
        await seed_miniapp_product(
            db,
            item_id=int(PRODUCT_ID),
            title=PRODUCT_TITLE,
            content="后台上下架 smoke 商品，用于验证小程序目录同步。",
            keywords="烟测,商品上下架,小程序目录",
            price_fen=25800,
            stock=9,
            sold_num=2,
            image="https://img.example/smoke-active.jpg",
            is_active=1,
        )
        await db.commit()
    finally:
        await db.close()


def miniapp_has_product() -> bool:
    payload = request_json(f"{BACKEND_URL}/api/v1/miniapp/products?ids={PRODUCT_ID}")
    return any(item.get("id") == PRODUCT_ID for item in payload.get("data", []))


def wait_for_miniapp_presence(expected: bool, timeout_seconds: float = 20) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if miniapp_has_product() is expected:
            return
        time.sleep(0.5)
    raise RuntimeError(
        f"小程序商品目录未达到期望状态: {PRODUCT_ID} expected={expected}"
    )


def wait_for_row(cdp: CdpClient) -> None:
    wait_for_expression(
        cdp,
        f"document.querySelector('[data-testid=\"products-row-title-{PRODUCT_ID}\"]')",
    )
    wait_for_expression(
        cdp, f"document.body.innerText.includes({js_string(PRODUCT_TITLE)})"
    )


def run_browser_flow() -> CdpClient:
    start_chrome(cdp_port=CDP_PORT, profile_dir=CHROME_PROFILE, processes=processes)
    cdp = connect_page(CDP_PORT)
    try:
        cdp.send(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1366, "height": 900, "deviceScaleFactor": 1, "mobile": False},
        )
        login_admin(
            cdp,
            f"{ADMIN_URL}?keyword={PRODUCT_QUERY}&is_active=1",
            TOKEN,
        )
        cdp.send(
            "Page.navigate", {"url": f"{ADMIN_URL}?keyword={PRODUCT_QUERY}&is_active=1"}
        )
        wait_for_expression(
            cdp, "document.querySelector('[data-testid=\"products-page\"]')"
        )
        wait_for_row(cdp)
        wait_for_miniapp_presence(True)

        click_test_id(cdp, f"products-toggle-active-{PRODUCT_ID}")
        wait_for_miniapp_presence(False)

        click_test_id(cdp, "products-filter-inactive")
        wait_for_row(cdp)
        click_test_id(cdp, f"products-toggle-active-{PRODUCT_ID}")
        wait_for_miniapp_presence(True)
        click_test_id(cdp, "products-filter-active")
        wait_for_row(cdp)
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
    logger.info("seeding temporary catalog")
    asyncio.run(seed_catalog())

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
        wait_for_http(f"{ADMIN_URL}?keyword={PRODUCT_QUERY}&is_active=1")
        logger.info("running browser active toggle flow")
        cdp = run_browser_flow()
        logger.info("screenshot saved: %s", SCREENSHOT_PATH)
        logger.info("products active toggle smoke passed")
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
