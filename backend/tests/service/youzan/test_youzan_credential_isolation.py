"""有赞凭证隔离测试：单点构造、异常脱敏、无日志泄漏。"""

import ast
from pathlib import Path

from app.service.youzan.client import (
    build_api_url,
    sanitize_credential_text,
)


def test_api_url_builder_is_single_construction_site() -> None:
    """凭证进入地址只能经统一构造器。"""
    root = Path(__file__).resolve().parents[3]
    content = (root / "app" / "service" / "youzan" / "client.py").read_text(
        encoding="utf-8"
    )
    url_lines = [line for line in content.splitlines() if "?access_token=" in line]
    assert len(url_lines) == 1
    assert "build_api_url" in content
    assert build_api_url("youzan.trade.get", "4.0.0", "secret-token").endswith(
        "youzan.trade.get/4.0.0?access_token=secret-token"
    )


def test_httpx_error_text_is_redacted() -> None:
    """异常文本中的凭证必须脱敏。"""
    leaked = (
        "Client error '403 Forbidden' for url "
        "'https://open.youzanyun.com/api/youzan.trade.get/4.0.0"
        "?access_token=real-secret-token' For more information check"
    )
    redacted = sanitize_credential_text(leaked)
    assert "real-secret-token" not in redacted
    assert "access_token=***" in redacted
    assert "youzan.trade.get/4.0.0" in redacted


def test_json_token_text_is_redacted() -> None:
    """JSON 形态凭证同样脱敏。"""
    redacted = sanitize_credential_text("{'access_token': 'real-secret-token'}")
    assert "real-secret-token" not in redacted


def test_no_credential_logging_in_youzan_client() -> None:
    """客户端日志调用不得携带凭证变量。"""
    root = Path(__file__).resolve().parents[3]
    content = (root / "app" / "service" / "youzan" / "client.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(content)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_logger = (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "logger"
        )
        if not is_logger:
            continue
        for arg in (*node.args, *(keyword.value for keyword in node.keywords)):
            for child in ast.walk(arg):
                if isinstance(child, ast.Name) and child.id == "token":
                    raise AssertionError("日志调用携带凭证变量")


ALLOWED_QUERY_TOKEN_SITES = {
    # 有赞云与企微官方协议要求凭证走查询参数，集中构造并脱敏异常。
    "app/service/youzan/client.py": ("build_api_url",),
    "app/service/wecom/client.py": ("params=",),
    "app/service/wecom/client_kf.py": ("params=",),
    "app/service/transfer_manager.py": ("params=",),
}


def test_all_query_token_sites_are_registered() -> None:
    """全仓凭证查询参数构造点必须登记在册，新增需评审。"""
    import re

    root = Path(__file__).resolve().parents[3] / "app"
    found: dict[str, list[str]] = {}
    pattern = re.compile(r"\?access_token=|params=\{\s*\"access_token\"")
    for path in sorted(root.rglob("*.py")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if pattern.search(text):
            rel = path.relative_to(root.parent).as_posix()
            found[rel] = sorted(
                {
                    line.strip()[:60]
                    for line in text.splitlines()
                    if pattern.search(line)
                }
            )
    assert set(found) == set(ALLOWED_QUERY_TOKEN_SITES), (
        f"未登记的凭证构造点: {set(found) ^ set(ALLOWED_QUERY_TOKEN_SITES)}"
    )
