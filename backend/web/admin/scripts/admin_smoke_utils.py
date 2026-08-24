"""管理后台浏览器 smoke 共享工具。"""

from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import websocket

ROOT = Path(__file__).resolve().parents[3]
ADMIN_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports" / "ui"


def configure_logger(name: str) -> logging.Logger:
    logging.basicConfig(level=logging.INFO, format=f"[{name}] %(message)s")
    return logging.getLogger(name)


def request_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_http(url: str, timeout_seconds: float = 30) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error = ""
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status < 500:
                    return
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"等待服务超时: {url}; {last_error}")


class CdpClient:
    def __init__(self, websocket_url: str) -> None:
        self._ws = websocket.create_connection(websocket_url, timeout=10)
        self._next_id = 1

    def send(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        message_id = self._next_id
        self._next_id += 1
        self._ws.send(
            json.dumps({"id": message_id, "method": method, "params": params or {}})
        )
        while True:
            payload = json.loads(self._ws.recv())
            if payload.get("id") == message_id:
                if "error" in payload:
                    raise RuntimeError(payload["error"].get("message", "CDP 调用失败"))
                return payload.get("result", {})

    def eval(self, expression: str, await_promise: bool = True) -> Any:
        result = self.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": await_promise,
                "returnByValue": True,
            },
        )
        if "exceptionDetails" in result:
            raise RuntimeError(
                result["exceptionDetails"].get("text", "页面脚本执行失败")
            )
        return result.get("result", {}).get("value")

    def close(self) -> None:
        self._ws.close()


def get_page_websocket_url(cdp_port: int) -> str:
    targets = request_json(f"http://127.0.0.1:{cdp_port}/json/list")
    for target in targets:
        if target.get("type") == "page" and target.get("webSocketDebuggerUrl"):
            return str(target["webSocketDebuggerUrl"])
    raise RuntimeError("未找到可用的 Chrome 页面 target")


def connect_page(cdp_port: int) -> CdpClient:
    wait_for_http(f"http://127.0.0.1:{cdp_port}/json/version", 20)
    wait_for_http(f"http://127.0.0.1:{cdp_port}/json/list", 20)
    cdp = CdpClient(get_page_websocket_url(cdp_port))
    cdp.send("Page.enable")
    cdp.send("Runtime.enable")
    return cdp


def wait_for_expression(
    cdp: CdpClient, expression: str, timeout_seconds: float = 20
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if cdp.eval(f"Boolean({expression})"):
            return
        time.sleep(0.25)
    raise RuntimeError(f"等待页面条件超时: {expression}")


def js_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def login_admin(cdp: CdpClient, admin_url: str, token: str) -> None:
    """通过后台登录 API 写入会话 Cookie，替代已失效的 localStorage 写入。"""
    cdp.send("Page.navigate", {"url": admin_url})
    wait_for_expression(
        cdp,
        "location.href.includes('/login') || document.querySelector('input[type=password]')",
        timeout_seconds=20,
    )
    cdp.eval(
        f"""
        (async () => {{
          const response = await fetch('/api/v1/admin/auth/login', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ token: {js_string(token)} }})
          }});
          if (!response.ok) return false;
          location.href = {js_string(admin_url)};
          return true;
        }})()
        """
    )
    wait_for_expression(
        cdp,
        "!location.href.includes('/login') && !document.querySelector('input[type=password]')",
        timeout_seconds=25,
    )


def click_test_id(cdp: CdpClient, test_id: str) -> None:
    selector = f'[data-testid="{test_id}"]'
    selector_js = js_string(selector)
    wait_for_expression(cdp, f"document.querySelector({selector_js})")
    cdp.eval(
        f"""
        (() => {{
          const el = document.querySelector({selector_js});
          el.scrollIntoView({{ block: 'center', inline: 'center' }});
          el.click();
          return true;
        }})()
        """
    )


def dispatch_click_test_id(cdp: CdpClient, test_id: str) -> None:
    selector = f'[data-testid="{test_id}"]'
    selector_js = js_string(selector)
    wait_for_expression(cdp, f"document.querySelector({selector_js})")
    cdp.eval(
        f"""
        (() => {{
          const el = document.querySelector({selector_js});
          el.scrollIntoView({{ block: 'center', inline: 'center' }});
          el.dispatchEvent(new MouseEvent('click', {{ bubbles: true, cancelable: true, view: window }}));
          return true;
        }})()
        """
    )


def fill_test_id(cdp: CdpClient, test_id: str, value: str) -> None:
    selector = f'[data-testid="{test_id}"]'
    selector_js = js_string(selector)
    value_js = js_string(value)
    wait_for_expression(cdp, f"document.querySelector({selector_js})")
    cdp.eval(
        f"""
        (() => {{
          const host = document.querySelector({selector_js});
          const control = host.matches('input, textarea')
            ? host
            : host.querySelector('input, textarea');
          if (!control) {{
            throw new Error(`找不到可填充控件: {test_id}`);
          }}
          control.focus();
          control.value = {value_js};
          control.dispatchEvent(new Event('input', {{ bubbles: true }}));
          control.dispatchEvent(new Event('change', {{ bubbles: true }}));
          return control.value;
        }})()
        """
    )


def capture_screenshot(cdp: CdpClient, path: Path) -> None:
    screenshot = cdp.send(
        "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True}
    )
    path.write_bytes(base64.b64decode(screenshot["data"]))


def start_process(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    label: str,
    processes: list[subprocess.Popen[Any]],
    logger: logging.Logger,
) -> subprocess.Popen[str]:
    """启动子进程并把输出落盘，避免 PIPE 缓冲区填满后阻塞进程。"""
    log_dir = REPORTS_DIR / "smoke-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{label}-{time.strftime('%Y%m%d-%H%M%S')}.log"
    log_file = open(log_path, "w", encoding="utf-8")
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    process._smoke_log_path = log_path  # type: ignore[attr-defined]
    logger.info("%s pid=%s log=%s", label, process.pid, log_path)
    processes.append(process)
    return process


def dump_process_tail(
    process: subprocess.Popen[str], label: str, logger: logging.Logger
) -> None:
    if process.stdout is None:
        return
    try:
        line = process.stdout.readline()
        if line:
            logger.info("[%s] %s", label, line.rstrip())
    except Exception:
        return


def start_chrome(
    *,
    cdp_port: int,
    profile_dir: Path,
    processes: list[subprocess.Popen[Any]],
) -> None:
    chrome_path = Path("C:/Program Files/Google/Chrome/Application/chrome.exe")
    if not chrome_path.exists():
        raise RuntimeError(f"找不到 Chrome: {chrome_path}")
    chrome = subprocess.Popen(
        [
            str(chrome_path),
            f"--remote-debugging-port={cdp_port}",
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--remote-allow-origins=*",
            f"--user-data-dir={profile_dir}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    processes.append(chrome)


def stop_processes(processes: list[subprocess.Popen[Any]]) -> None:
    for process in reversed(processes):
        process.terminate()
    time.sleep(1)
    for process in reversed(processes):
        if process.poll() is None:
            process.kill()
    for process in processes:
        stdout = getattr(process, "stdout", None)
        if stdout is not None and hasattr(stdout, "close"):
            try:
                stdout.close()
            except Exception:
                pass


def remove_existing_files(paths: list[Path]) -> None:
    for path in paths:
        if path.exists():
            path.unlink()


def npm_command() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"
