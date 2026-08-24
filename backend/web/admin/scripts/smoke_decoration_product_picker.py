"""后台装修商品选择器端到端烟测。"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
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
    dispatch_click_test_id,
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

DB_PATH = REPORTS_DIR / "decoration-product-picker-smoke.db"
SCREENSHOT_PATH = REPORTS_DIR / "decoration-product-picker-smoke.png"
CHROME_PROFILE = REPORTS_DIR / "admin-decoration-page-switcher-chrome-profile"
TOKEN = "LOCAL_DECORATION_PICKER_TOKEN"
BACKEND_PORT = 17001
ADMIN_PORT = 15173
BACKEND_URL = f"http://127.0.0.1:{BACKEND_PORT}"
ADMIN_URL = f"http://127.0.0.1:{ADMIN_PORT}/admin-v2/decoration"
CDP_PORT = 19224
PRODUCT_ID = "91017003"
PRODUCT_TITLE = "smoke picker strawberry cake"
FAILURE_SCREENSHOT_PATH = REPORTS_DIR / "decoration-product-picker-smoke-failure.png"

logger = configure_logger("decoration-smoke")
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
            content="浏览器烟测商品，用于后台装修商品选择器。",
            keywords="烟测,装修,商品选择器",
            price_fen=23800,
            stock=12,
            sold_num=3,
            image="https://img.example/smoke-picker.jpg",
            is_active=1,
        )
        await db.commit()
    finally:
        await db.close()


def select_products_page(cdp: CdpClient) -> None:
    dispatch_click_test_id(cdp, "decoration-page-tab-products")
    wait_for_expression(
        cdp, "document.querySelector('[data-testid=\"decoration-block-products-all\"]')"
    )


def run_browser_flow() -> CdpClient:
    start_chrome(cdp_port=CDP_PORT, profile_dir=CHROME_PROFILE, processes=processes)
    cdp = connect_page(CDP_PORT)
    try:
        login_admin(cdp, ADMIN_URL, TOKEN)
        cdp.send("Page.navigate", {"url": ADMIN_URL})
        wait_for_expression(
            cdp, "document.querySelector('[data-testid=\"decoration-page-select\"]')"
        )
        select_products_page(cdp)
        dispatch_click_test_id(cdp, "decoration-block-products-all")
        wait_for_expression(cdp, "document.body.innerText.includes('商品 ID')")
        click_test_id(cdp, "decoration-open-product-picker")
        fill_test_id(cdp, "decoration-product-picker-search", PRODUCT_TITLE)
        click_test_id(cdp, "decoration-product-picker-search-button")
        click_test_id(cdp, f"decoration-product-picker-add-{PRODUCT_ID}")
        wait_for_expression(
            cdp,
            f"document.querySelector('[data-testid=\"decoration-selected-product-{PRODUCT_ID}\"]')",
        )
        capture_screenshot(cdp, SCREENSHOT_PATH)
        click_test_id(cdp, "decoration-save-draft")
        wait_for_expression(cdp, "document.body.textContent.includes('装修草稿已保存')")
        click_test_id(cdp, "decoration-publish")
        wait_for_expression(cdp, "document.body.textContent.includes('已发布到小程序')")
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


def verify_miniapp_published_config() -> None:
    payload = request_json(f"{BACKEND_URL}/api/v1/miniapp/pages/products")
    product_ids = [
        product_id
        for block in payload["data"]["blocks"]
        for product_id in block.get("props", {}).get("productIds", [])
    ]
    if PRODUCT_ID not in product_ids:
        raise RuntimeError(f"发布版商品页未包含 {PRODUCT_ID}: {product_ids}")
    logger.info("miniapp products page published productIds include %s", PRODUCT_ID)


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
        wait_for_http(ADMIN_URL)
        logger.info("running browser product picker flow")
        cdp = run_browser_flow()
        verify_miniapp_published_config()
        logger.info("screenshot saved: %s", SCREENSHOT_PATH)
        logger.info("decoration product picker smoke passed")
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
