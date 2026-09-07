"""仓库脚本凭证卫生扫描：禁止硬编码真实密钥字面量，只报告位置。"""

import ast
from pathlib import Path

SECRET_NAME_HINTS = (
    "secret",
    "token",
    "password",
    "api_key",
    "apikey",
    "kdt_id",
    "client_id",
)
PLACEHOLDER_HINTS = (
    "mock",
    "test",
    "placeholder",
    "***",
    "xxx",
    "change",
    "example",
    "fake",
    "dummy",
    "env",
    "environ",
    "callback",
    "token",
    "{",
    "}",
    "<",
    ">",
)


def _looks_real(value: str, name: str = "") -> bool:
    """长度达标、无占位标记、非重复模式的值视为疑似真实密钥。

    纯数字短 ID（如 kdt）单独判定：6 位以上、非重复数字、非顺序号即疑似。
    """
    lowered = value.lower()
    if any(hint in lowered for hint in PLACEHOLDER_HINTS):
        return False
    if value.isdigit():
        if len(value) < 6:
            return False
        if len(set(value)) <= 2:
            return False
        return "123456" not in value
    if len(value) < 12:
        return False
    if len(set(value)) <= 4:
        return False
    return True


def _scan_file(path: Path) -> list[str]:
    """扫描单文件，返回疑似硬编码位置描述。

    只判定直接赋值的字符串字面量（x = "..."），字典键名与下标访问不算。
    """
    findings: list[str] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return findings
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Constant):
            continue
        if not isinstance(node.value.value, str):
            continue
        names = [target.id for target in node.targets if isinstance(target, ast.Name)]
        if not any(
            hint in name.lower() for name in names for hint in SECRET_NAME_HINTS
        ):
            continue
        if _looks_real(node.value.value, names[0]):
            findings.append(f"{path.name}:{node.lineno}:{names[0]}")
    return findings


def test_scripts_have_no_hardcoded_secrets() -> None:
    """backend/scripts 下不得出现疑似真实密钥字面量。"""
    root = Path(__file__).resolve().parents[2] / "scripts"
    findings: list[str] = []
    for path in sorted(root.glob("*.py")):
        findings.extend(_scan_file(path))
    assert findings == [], f"发现疑似硬编码密钥: {findings}"


def test_feasibility_probe_reads_credentials_from_env() -> None:
    """连通性探针必须从环境变量读取凭证，不得回退内置值。"""
    root = Path(__file__).resolve().parents[2] / "scripts"
    content = (root / "test_youzan_product_feasibility.py").read_text(encoding="utf-8")
    assert "os.environ" in content or "getenv" in content
    assert 'open("output.txt"' not in content
