"""生产后台只读导航浏览器 smoke。"""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Any

from admin_smoke_utils import (
    REPORTS_DIR,
    CdpClient,
    capture_screenshot,
    configure_logger,
    connect_page,
    js_string,
    login_admin,
    start_chrome,
    stop_processes,
    wait_for_expression,
    wait_for_http,
)

TRACE_ID = "20260617-production-admin-browser-smoke"
ADMIN_URL = os.environ.get("YUNXI_PRODUCTION_ADMIN_URL", "https://yunxifood.cn/admin/")
TOKEN = os.environ.get("YUNXI_ADMIN_API_TOKEN") or os.environ.get("ADMIN_API_TOKEN", "")
CDP_PORT = int(os.environ.get("YUNXI_PRODUCTION_ADMIN_CDP_PORT", "19241"))
CHROME_PROFILE = REPORTS_DIR / "production-admin-browser-chrome-profile"
SCREENSHOT_PATH = REPORTS_DIR / "production-admin-browser-smoke.png"
FAILURE_SCREENSHOT_PATH = REPORTS_DIR / "production-admin-browser-smoke-failure.png"
REPORT_PATH = REPORTS_DIR / "production-admin-browser-smoke.json"

PAGE_CHECKS = [
    {
        "name": "overview",
        "path": "overview",
        "selector": '[data-testid="overview-mobile-ops"]',
    },
    {
        "name": "decoration",
        "path": "decoration",
        "selector": '[data-testid="decoration-page-select"]',
    },
    {
        "name": "orders",
        "path": "orders",
        "selector": '[data-testid="orders-page"]',
    },
    {
        "name": "addresses",
        "path": "addresses",
        "selector": '[data-testid="addresses-page"]',
    },
    {
        "name": "products",
        "path": "products",
        "selector": '[data-testid="products-page"]',
    },
    {
        "name": "transfers",
        "path": "transfers",
        "selector": '[data-testid="transfers-page"]',
    },
    {
        "name": "shop settings",
        "path": "settings/shop",
        "selector": '[data-testid="shop-settings-page"]',
    },
]

logger = configure_logger("production-admin-browser-smoke")
processes: list[subprocess.Popen[Any]] = []


def admin_page_url(path: str) -> str:
    return f"{ADMIN_URL.rstrip('/')}/{path.lstrip('/')}"


def write_report(status: str, checks: list[dict[str, Any]], error: str = "") -> None:
    payload = {
        "traceId": TRACE_ID,
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": status,
        "adminUrl": ADMIN_URL,
        "screenshot": str(SCREENSHOT_PATH),
        "failureScreenshot": str(FAILURE_SCREENSHOT_PATH),
        "checks": checks,
        "error": error,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n", encoding="utf-8"
    )


def collect_page_state(cdp: CdpClient) -> dict[str, Any]:
    return cdp.eval(
        """
        (() => ({
          href: location.href,
          title: document.title,
          bodyHead: document.body.innerText.slice(0, 500),
          testIds: Array.from(document.querySelectorAll('[data-testid]'))
            .map((node) => node.getAttribute('data-testid'))
            .slice(0, 80)
        }))()
        """
    )


def verify_page(cdp: CdpClient, check: dict[str, str]) -> dict[str, Any]:
    url = admin_page_url(check["path"])
    selector = check["selector"]
    started_at = time.monotonic()
    cdp.send("Page.navigate", {"url": url})
    wait_for_expression(
        cdp, f"location.href.includes({js_string(check['path'])})", timeout_seconds=20
    )
    wait_for_expression(
        cdp, f"document.querySelector({js_string(selector)})", timeout_seconds=25
    )
    state = collect_page_state(cdp)
    return {
        "name": check["name"],
        "url": url,
        "selector": selector,
        "ok": True,
        "durationMs": int((time.monotonic() - started_at) * 1000),
        "href": state.get("href", ""),
        "title": state.get("title", ""),
        "bodyHead": state.get("bodyHead", ""),
    }


def run_browser_flow() -> CdpClient:
    if not TOKEN:
        raise RuntimeError("YUNXI_ADMIN_API_TOKEN or ADMIN_API_TOKEN is required")

    start_chrome(cdp_port=CDP_PORT, profile_dir=CHROME_PROFILE, processes=processes)
    cdp = connect_page(CDP_PORT)
    try:
        cdp.send(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1440, "height": 960, "deviceScaleFactor": 1, "mobile": False},
        )
        login_admin(cdp, ADMIN_URL, TOKEN)

        checks: list[dict[str, Any]] = []
        for page_check in PAGE_CHECKS:
            logger.info("checking %s", page_check["name"])
            checks.append(verify_page(cdp, page_check))

        capture_screenshot(cdp, SCREENSHOT_PATH)
        write_report("pass", checks)
    except Exception as exc:
        try:
            capture_screenshot(cdp, FAILURE_SCREENSHOT_PATH)
        except Exception:
            pass
        state = collect_page_state(cdp)
        logger.info("failure page state: %s", state)
        write_report("fail", [], error=str(exc))
        raise
    return cdp


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    cdp: CdpClient | None = None
    try:
        wait_for_http(ADMIN_URL, timeout_seconds=20)
        cdp = run_browser_flow()
        logger.info("screenshot saved: %s", SCREENSHOT_PATH)
        logger.info("report saved: %s", REPORT_PATH)
        logger.info("production admin browser smoke passed")
    finally:
        if cdp is not None:
            cdp.close()
        stop_processes(processes)


if __name__ == "__main__":
    main()
