"""后台转人工队列浏览器 smoke。"""

from __future__ import annotations

import json
import os
import subprocess
import time
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
    dispatch_click_test_id,
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

DB_PATH = REPORTS_DIR / "transfers-queue-smoke.db"
SCREENSHOT_PATH = REPORTS_DIR / "transfers-queue-smoke.png"
FAILURE_SCREENSHOT_PATH = REPORTS_DIR / "transfers-queue-smoke-failure.png"
CHROME_PROFILE = REPORTS_DIR / "transfers-queue-chrome-profile"
TOKEN = "LOCAL_TRANSFERS_QUEUE_TOKEN"
BACKEND_PORT = 17007
ADMIN_PORT = 15179
BACKEND_URL = f"http://127.0.0.1:{BACKEND_PORT}"
ADMIN_URL = f"http://127.0.0.1:{ADMIN_PORT}/admin-v2/transfers"
CDP_PORT = 19230
TRACE_KEY = "smoke-transfer-20260617"
USER_ID = "miniapp-transfer-smoke-user"
TRANSFER_REASON = f"{TRACE_KEY} 需要门店人工确认配送和甜度"

logger = configure_logger("transfers-queue-smoke")
processes: list[subprocess.Popen[Any]] = []


def post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def seed_transfer() -> dict[str, str]:
    headers = {"x-miniapp-user-id": USER_ID}
    payload = post_json(
        f"{BACKEND_URL}/api/v1/miniapp/chat/transfer",
        {"reason": TRANSFER_REASON},
        headers=headers,
    )
    session_id = str(payload["data"]["status"]["sessionId"])
    logger.info("created transfer session=%s", session_id)
    return {"session_id": session_id}


def wait_for_transfer(timeout_seconds: float = 30) -> dict[str, str]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        payload = get_json(
            f"{BACKEND_URL}/api/v1/admin/transfers/pending",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        for item in payload.get("data", []):
            if item.get("user_id") == USER_ID and TRACE_KEY in str(
                item.get("reason", "")
            ):
                transfer_id = str(item["id"])
                session_id = str(item["session_id"])
                logger.info("pending transfer=%s session=%s", transfer_id, session_id)
                return {"transfer_id": transfer_id, "session_id": session_id}
        time.sleep(0.5)
    raise RuntimeError("未等到小程序主动转人工工单")


def body_includes(text: str) -> str:
    return f"document.body.innerText.includes({js_string(text)})"


def run_browser_flow(transfer: dict[str, str]) -> CdpClient:
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
            cdp, "document.querySelector('[data-testid=\"transfers-page\"]')"
        )
        wait_for_expression(cdp, body_includes(TRACE_KEY))
        wait_for_expression(cdp, body_includes(USER_ID[:14]))
        wait_for_expression(cdp, body_includes("待处理"))

        click_test_id(cdp, f"transfers-open-detail-{transfer['transfer_id']}")
        wait_for_expression(
            cdp, "document.querySelector('[data-testid=\"transfer-detail-drawer\"]')"
        )
        wait_for_expression(cdp, body_includes(TRANSFER_REASON))

        dispatch_click_test_id(cdp, "transfer-detail-accept")
        wait_for_expression(
            cdp,
            f"document.querySelector('[data-testid=\"transfers-row-status-{transfer['transfer_id']}\"]')"
            "?.innerText.includes('已接单')",
        )
        wait_for_expression(
            cdp,
            """
            document.querySelector('[data-testid="transfer-detail-drawer"]')
              ?.innerText.includes('已接单')
            """,
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
        body_text = cdp.eval("document.body.innerText.slice(0, 1600)")
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
        seed_transfer()
        transfer = wait_for_transfer()
        wait_for_http(ADMIN_URL)
        logger.info("running browser transfer queue flow")
        cdp = run_browser_flow(transfer)
        logger.info("screenshot saved: %s", SCREENSHOT_PATH)
        logger.info("transfers queue smoke passed")
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
