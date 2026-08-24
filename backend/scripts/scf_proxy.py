"""腾讯云函数（SCF）— 企微回调转发代理。

SCF 的函数 URL 收到企微回调请求后，原样转发到 VPS。
"""

import urllib.request
import urllib.error


VPS_URL = "http://47.94.102.250:7001"


def main_handler(event: dict, context: dict) -> dict:
    method = event.get("httpMethod", "GET")
    path = event.get("path", "/api/v1/wecom/callback")
    qs = event.get("queryString") or ""
    headers = {
        k: v
        for k, v in (event.get("headers") or {}).items()
        if k.lower() not in ("host", "x-request-id")
    }
    body = event.get("body") or ""

    url = f"{VPS_URL}{path}"
    if qs:
        url += f"?{qs}"

    try:
        req = urllib.request.Request(
            url,
            data=body.encode() if body else None,
            headers=headers,
            method=method,
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp_body = resp.read()
    except urllib.error.HTTPError as e:
        resp_body = e.read()

    return {
        "isBase64Encoded": False,
        "statusCode": 200,
        "headers": {"Content-Type": "text/plain"},
        "body": resp_body.decode(),
    }
