"""检查后台认证前端不会持久化或自动发送长期管理凭证。"""

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_FILES = (
    ROOT_DIR / "web" / "admin" / "src" / "services" / "auth.ts",
    ROOT_DIR / "web" / "admin" / "src" / "services" / "http.ts",
)


def check() -> list[str]:
    failures: list[str] = []
    for path in FRONTEND_FILES:
        content = path.read_text(encoding="utf-8")
        if "localStorage" in content:
            failures.append(f"{path.relative_to(ROOT_DIR)} 包含 localStorage")
        if "Authorization" in content:
            failures.append(f"{path.relative_to(ROOT_DIR)} 包含自动 Authorization")
    config = (ROOT_DIR / "app" / "config.py").read_text(encoding="utf-8")
    if "ADMIN_ALLOW_LEGACY_BEARER: bool = False" not in config:
        failures.append("ADMIN_ALLOW_LEGACY_BEARER 默认值必须为 False")
    return failures


def main() -> int:
    failures = check()
    if failures:
        print("[admin-auth-surface] failed")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("[admin-auth-surface] passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
