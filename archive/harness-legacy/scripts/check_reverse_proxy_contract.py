"""检查反向代理安全合同示例未回退。"""

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "deploy" / "nginx" / "yunxibakebot.conf.example"
REQUIRED_DIRECTIVES = (
    "client_max_body_size 1m",
    "limit_req_zone",
    "limit_conn_zone",
    "proxy_pass http://127.0.0.1:7001",
    "proxy_read_timeout 45s",
    "proxy_request_buffering on",
    "location = /docs",
    "location = /openapi.json",
    "add_header X-Content-Type-Options nosniff always",
)


def check() -> list[str]:
    if not CONFIG_PATH.exists():
        return [f"缺少 {CONFIG_PATH.relative_to(ROOT_DIR)}"]
    content = CONFIG_PATH.read_text(encoding="utf-8")
    return [
        f"反向代理合同缺少 `{directive}`"
        for directive in REQUIRED_DIRECTIVES
        if directive not in content
    ]


def main() -> int:
    failures = check()
    if failures:
        print("[reverse-proxy-contract] failed")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("[reverse-proxy-contract] passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
