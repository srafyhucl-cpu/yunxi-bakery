"""检查 Harness P0 中文治理控制面。"""

from __future__ import annotations

import argparse
import ast
import io
import json
import re
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path

try:
    from check_project_development_register import parse_register
except ModuleNotFoundError:
    from scripts.check_project_development_register import parse_register

ROOT_DIR = Path(__file__).resolve().parents[2]
GOVERNANCE_MODEL_FILE = "docs/harness-engineering/core/chinese-governance.json"
GOVERNANCE_MODEL_PATH = ROOT_DIR / GOVERNANCE_MODEL_FILE
DIMENSION_IDS = (
    "documentation",
    "interface",
    "collaboration",
    "process",
    "delivery",
    "code_comments",
)
DIMENSION_NAMES = {
    "documentation": "文档",
    "interface": "系统界面",
    "collaboration": "协作沟通",
    "process": "流程规范",
    "delivery": "交付物",
    "code_comments": "代码注释",
}
GENERATED_PATH_PARTS = {
    "node_modules",
    "dist",
    "reports",
    "__pycache__",
    ".git",
    ".tea",
}
UI_ATTRIBUTE_RE = re.compile(
    r"(?<![:\w-])(?:placeholder|aria-label|title|label|content|data-content|confirm-text|cancel-text|loading-text|empty-text)\s*=\s*([\"'])(.*?)\1",
    re.IGNORECASE,
)
UI_TEXT_NODE_RE = re.compile(r">([^<>]+)<", re.DOTALL)
COMMENT_DIRECTIVE_RE = re.compile(
    r"^(?:!/?|[-*\s]*coding\s*[:=]|noqa\b|type:\s*ignore\b|pragma\b|pylint\b|mypy\b|pyright\b|ruff\b|fmt:\s*|region\b|endregion\b|reference\b|eslint\b|ts-ignore\b|istanbul\b)",
    re.IGNORECASE,
)
TECHNICAL_COMMENT_WORDS = {
    "ai",
    "api",
    "ascii",
    "cny",
    "css",
    "dom",
    "html",
    "http",
    "https",
    "id",
    "json",
    "js",
    "sql",
    "sku",
    "ts",
    "typescript",
    "url",
    "utf",
    "utf8",
    "vue",
    "wecom",
    "wxml",
    "wxss",
    "youzan",
}
UI_TECHNICAL_WORDS = {
    "ai",
    "api",
    "ascii",
    "chat",
    "checkout",
    "cny",
    "cookie",
    "css",
    "enter",
    "dom",
    "html",
    "http",
    "https",
    "id",
    "ios",
    "json",
    "js",
    "faq",
    "mimo",
    "new",
    "opengid",
    "orders",
    "pc",
    "promotion",
    "rag",
    "shift",
    "sku",
    "token",
    "ts",
    "typescript",
    "url",
    "userid",
    "vip",
    "vue",
    "webhook",
    "wechat",
    "wxml",
    "wxss",
    "yunxi",
}
STATUS_LABELS = {
    "active": "进行中（active）",
    "blocked": "已阻塞（blocked）",
    "completed": "已完成（completed）",
    "pending": "待处理（pending）",
    "deferred": "已暂缓（deferred）",
    "historical": "历史（historical）",
}
DIMENSION_PRIORITIES = {
    "documentation": "P0",
    "interface": "P0",
    "collaboration": "P0",
    "process": "P0",
    "delivery": "P0",
    "code_comments": "P1",
}
MACHINE_STATUS_RE = re.compile(
    r"(?<![\w（(])(active|blocked|completed|pending|deferred|historical)(?![\w）)])",
    re.IGNORECASE,
)
HUMAN_STATUS_GROUP_RE = re.compile(
    r"[\u3400-\u9fff][^（）()\n]{0,20}[（(][^）)\n]*"
    r"(?:active|blocked|completed|pending|deferred|historical)"
    r"[^）)\n]*[）)]",
    re.IGNORECASE,
)
AUTHORITATIVE_FILES = ("AGENTS.md", "PROJECT-STATE.md", "LOGBOOK.md", "ERRORS.md")
GOVERNANCE_FILES = (
    "AGENTS.md",
    "PROJECT-STATE.md",
    "LOGBOOK.md",
    "ERRORS.md",
    "docs/harness-engineering/README.md",
    "docs/harness-engineering/core/traceability-model.md",
    "docs/harness-engineering/core/verification-matrix.md",
    "docs/harness-engineering/core/agent-handoff-template.md",
    "docs/AGENTS/multi-agent-coordination.md",
    "docs/harness-engineering/core/chinese-governance.json",
    "docs/harness-engineering/core/chinese-governance-model.md",
    "docs/harness-engineering/core/delivery-artifact-template.md",
    "docs/AGENTS/communication-template.md",
    ".github/pull_request_template.md",
    ".github/ISSUE_TEMPLATE/bug-report.yml",
    ".github/ISSUE_TEMPLATE/feature-request.yml",
)
HIGH_RISK_FILES = (
    "backend/scripts/preflight_production.py",
    "backend/scripts/check_privacy_outbound_contract.py",
    "backend/scripts/check_security_outbound_contract.py",
    "backend/scripts/smoke_test.py",
    "miniapp/docs/release/manual-acceptance-checklist.md",
)
HIGH_RISK_REQUIRED_TEXT = {
    "backend/scripts/preflight_production.py": (
        "生产同步前只读预检报告",
        "阻断",
        "人工接手",
    ),
    "backend/scripts/check_privacy_outbound_contract.py": (
        "模型外发脱敏",
        "trace",
        "生产关闭态",
    ),
    "backend/scripts/check_security_outbound_contract.py": (
        "远程下载",
        "员工授权出站合同",
        "生产",
    ),
    "backend/scripts/smoke_test.py": (
        "上线前只读冒烟检查",
        "请求失败",
        "生产",
    ),
    "miniapp/docs/release/manual-acceptance-checklist.md": (
        "只用于开发测试和上线准备",
        "真实用户",
        "正式上线",
        "支付",
    ),
}
REQUIRED_REFERENCES = {
    "docs/harness-engineering/README.md": (
        "PROJECT-STATE.md",
        "LOGBOOK.md",
        "ERRORS.md",
        "Harness",
    ),
    "docs/harness-engineering/core/traceability-model.md": (
        "run_id",
        "replayable",
        "中文",
    ),
    "docs/harness-engineering/core/agent-handoff-template.md": (
        "trace_id",
        "run_id",
        "已完成",
        "未验证",
    ),
    "docs/harness-engineering/core/verification-matrix.md": (
        "Harness 中文治理",
        "P0",
    ),
    "docs/harness-engineering/core/chinese-governance-model.md": (
        "六个维度",
        "P0",
        "代码注释",
    ),
    "docs/harness-engineering/core/delivery-artifact-template.md": (
        "结果正确",
        "策略合规",
        "证据完整",
        "可回放",
    ),
    "docs/AGENTS/communication-template.md": (
        "task_id",
        "trace_id",
        "未验证",
    ),
    ".github/pull_request_template.md": (
        "中文治理六维度",
        "验证与证据",
    ),
}


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    details: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "details": list(self.details)}


def has_chinese(text: str) -> bool:
    return any("\u3400" <= char <= "\u9fff" for char in text)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _repository_path(root_dir: Path, relative: object) -> Path:
    """解析仓内路径并拒绝绝对路径或目录穿越。"""
    relative_text = str(relative or "").strip()
    if not relative_text:
        raise ValueError("治理模型中的路径不能为空")
    relative_path = Path(relative_text)
    if relative_path.is_absolute():
        raise ValueError(f"治理模型路径必须是仓内相对路径: {relative_text}")
    root = root_dir.resolve()
    resolved = (root / relative_path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"治理模型路径越出仓库: {relative_text}") from exc
    return resolved


def load_governance_model(root_dir: Path = ROOT_DIR) -> dict[str, object]:
    """读取六维中文治理模型，避免检查规则只散落在脚本常量中。"""
    path = root_dir / GOVERNANCE_MODEL_FILE
    payload = json.loads(_read(path))
    if not isinstance(payload, dict):
        raise ValueError("中文治理模型根节点必须是对象")
    return payload


def _model_dimensions(root_dir: Path = ROOT_DIR) -> list[dict[str, object]]:
    payload = load_governance_model(root_dir)
    dimensions = payload.get("dimensions")
    if not isinstance(dimensions, list):
        raise ValueError("中文治理模型必须包含 dimensions 数组")
    return [item for item in dimensions if isinstance(item, dict)]


def check_governance_model(root_dir: Path = ROOT_DIR) -> Check:
    """检查六维模型的 ID、优先级和最小结构。"""
    try:
        payload = load_governance_model(root_dir)
        dimensions = payload.get("dimensions")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return Check("中文治理六维模型", False, (f"模型不可读取: {exc}",))
    issues: list[str] = []
    if payload.get("schema_version") != "1.0":
        issues.append("schema_version 必须为 1.0")
    if payload.get("model_id") != "yunxi-chinese-governance":
        issues.append("model_id 不符合项目约定")
    if not isinstance(dimensions, list):
        issues.append("dimensions 必须是数组")
        return Check("中文治理六维模型", False, tuple(issues))
    found: list[str] = []
    for index, item in enumerate(dimensions):
        if not isinstance(item, dict):
            issues.append(f"dimensions[{index}] 必须是对象")
            continue
        dimension_id = str(item.get("id") or "")
        found.append(dimension_id)
        if not dimension_id:
            issues.append(f"dimensions[{index}] 缺少 id")
            continue
        name = str(item.get("name") or "")
        if not has_chinese(name):
            issues.append(f"{dimension_id}: name 必须包含中文")
        expected_priority = DIMENSION_PRIORITIES.get(dimension_id)
        if item.get("priority") != expected_priority:
            issues.append(
                f"{dimension_id}: priority 应为 {expected_priority}，"
                f"实际为 {item.get('priority') or '<empty>'}"
            )
        markers = item.get("required_markers")
        if not isinstance(markers, list) or not markers:
            issues.append(f"{dimension_id}: 缺少 required_markers 数组")
        if "required_files" not in item and "targets" not in item:
            issues.append(f"{dimension_id}: 必须声明 required_files 或 targets")
        file_markers = item.get("file_markers", {})
        if not isinstance(file_markers, dict):
            issues.append(f"{dimension_id}: file_markers 必须是对象")
        elif isinstance(item.get("required_files"), list):
            required_files = {str(path) for path in item["required_files"]}
            for relative, required in file_markers.items():
                if str(relative) not in required_files:
                    issues.append(
                        f"{dimension_id}: file_markers 引用了未登记文件 {relative}"
                    )
                if not isinstance(required, list) or not required:
                    issues.append(
                        f"{dimension_id}: {relative} 的逐文件标识必须是非空数组"
                    )
    if tuple(found) != DIMENSION_IDS:
        issues.append(f"六维 ID 必须按约定出现: 实际为 {found}")
    return Check("中文治理六维模型", not issues, tuple(issues))


def _required_files_for_dimension(
    root_dir: Path, dimension_id: str
) -> tuple[list[Path], list[str], dict[str, list[str]]]:
    dimensions = _model_dimensions(root_dir)
    dimension = next(
        (item for item in dimensions if item.get("id") == dimension_id), None
    )
    if dimension is None:
        raise ValueError(f"模型缺少维度 {dimension_id}")
    files = [
        _repository_path(root_dir, relative)
        for relative in dimension.get("required_files", [])
    ]
    markers = [str(marker) for marker in dimension.get("required_markers", [])]
    raw_file_markers = dimension.get("file_markers", {})
    if not isinstance(raw_file_markers, dict):
        raise ValueError(f"{dimension_id}: file_markers 必须是对象")
    file_markers = {
        str(relative): [str(marker) for marker in required]
        for relative, required in raw_file_markers.items()
        if isinstance(required, list)
    }
    return files, markers, file_markers


def _check_single_dimension_files(root_dir: Path, dimension_id: str) -> Check:
    """检查单个文件型维度的文件与中文标识。"""
    issues: list[str] = []
    try:
        paths, markers, file_markers = _required_files_for_dimension(
            root_dir, dimension_id
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        issues.append(f"{dimension_id}: 模型解析失败: {exc}")
        return Check(
            f"中文治理维度：{DIMENSION_NAMES.get(dimension_id, dimension_id)}",
            False,
            tuple(issues),
        )
    existing_text: list[str] = []
    text_by_relative: dict[str, str] = {}
    for path in paths:
        relative = path.relative_to(root_dir)
        if not path.is_file():
            issues.append(f"{dimension_id}: 文件不存在: {relative}")
            continue
        try:
            text = _read(path)
        except OSError as exc:
            issues.append(f"{dimension_id}: 文件无法读取 {relative}: {exc}")
            continue
        existing_text.append(text)
        text_by_relative[relative.as_posix()] = text
        if path.suffix.lower() not in {".json", ".yml", ".yaml"} and not has_chinese(
            text
        ):
            issues.append(f"{dimension_id}: 缺少中文人类可读内容: {relative}")
    combined = "\n".join(existing_text)
    missing = [marker for marker in markers if marker not in combined]
    issues.extend(f"{dimension_id}: 缺少治理标识 {marker}" for marker in missing)
    for relative, required in file_markers.items():
        text = text_by_relative.get(Path(relative).as_posix())
        if text is None:
            continue
        for marker in required:
            if marker not in text:
                issues.append(f"{dimension_id}: {relative} 缺少逐文件标识 {marker}")
    return Check(
        f"中文治理维度：{DIMENSION_NAMES.get(dimension_id, dimension_id)}",
        not issues,
        tuple(issues),
    )


def check_dimension_file_contract(root_dir: Path = ROOT_DIR) -> Check:
    """兼容入口：检查四个文件型维度。"""
    results = [
        _check_single_dimension_files(root_dir, dimension_id)
        for dimension_id in ("documentation", "collaboration", "process", "delivery")
    ]
    issues = tuple(detail for result in results for detail in result.details)
    return Check("中文治理维度文件契约", not issues, issues)


def check_documentation_contract(root_dir: Path = ROOT_DIR) -> Check:
    return _check_single_dimension_files(root_dir, "documentation")


def check_collaboration_contract(root_dir: Path = ROOT_DIR) -> Check:
    return _check_single_dimension_files(root_dir, "collaboration")


def check_process_contract(root_dir: Path = ROOT_DIR) -> Check:
    return _check_single_dimension_files(root_dir, "process")


def check_delivery_contract(root_dir: Path = ROOT_DIR) -> Check:
    return _check_single_dimension_files(root_dir, "delivery")


def _iter_model_target_files(
    root_dir: Path, dimension_id: str
) -> tuple[list[Path], list[str]]:
    dimensions = _model_dimensions(root_dir)
    dimension = next(
        (item for item in dimensions if item.get("id") == dimension_id), None
    )
    if dimension is None:
        raise ValueError(f"模型缺少维度 {dimension_id}")
    files: list[Path] = []
    seen: set[Path] = set()
    markers = [str(marker) for marker in dimension.get("required_markers", [])]
    targets = dimension.get("targets", [])
    if not isinstance(targets, list):
        raise ValueError(f"{dimension_id}: targets 必须是数组")
    for target in targets:
        if not isinstance(target, dict):
            raise ValueError(f"{dimension_id}: target 必须是对象")
        path = _repository_path(root_dir, target.get("path"))
        extensions = {
            str(extension).lower() for extension in target.get("extensions", [])
        }
        if not extensions:
            raise ValueError(f"{dimension_id}: target 必须声明 extensions")
        if path.is_file():
            if path.suffix.lower() in extensions:
                files.append(path)
                seen.add(path)
            continue
        if not path.is_dir():
            raise ValueError(
                f"{dimension_id}: target 路径不存在: {path.relative_to(root_dir)}"
            )
        for candidate in sorted(path.rglob("*")):
            if (
                candidate.is_file()
                and candidate.suffix.lower() in extensions
                and not any(part in GENERATED_PATH_PARTS for part in candidate.parts)
                and candidate not in seen
            ):
                files.append(candidate)
                seen.add(candidate)
    return files, markers


def _without_template_expression(value: str) -> str:
    return re.sub(r"\{\{.*?\}\}", " ", value, flags=re.DOTALL)


def _has_untranslated_ui_text(value: str) -> bool:
    """判断用户可见字面量是否含非技术英文单词。"""
    cleaned = _without_template_expression(value).strip()
    cleaned = re.sub(r"https?://\S+|www\.\S+", " ", cleaned)
    cleaned = re.sub(r"&[A-Za-z][A-Za-z0-9#]*;", " ", cleaned)
    if not cleaned:
        return False
    if re.fullmatch(r"[\W_]*[A-Za-z]?[\W_]*", cleaned):
        return False
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]*", cleaned)
    if not words:
        return False
    return any(
        word.lower() not in UI_TECHNICAL_WORDS
        and "_" not in word
        and "-" not in word
        and not any(char.isdigit() for char in word)
        for word in words
    )


def _interface_literals(path: Path) -> list[tuple[int, str]]:
    """提取 WXML/Vue 模板中的文本节点和用户可见属性。"""
    text = _read(path)
    literals: list[tuple[int, str]] = []

    def preserve_lines(match: re.Match[str]) -> str:
        return "\n" * match.group(0).count("\n")

    scan_text = text
    if path.suffix.lower() == ".vue":
        scan_text = re.sub(
            r"<script\b[^>]*>.*?</script>",
            preserve_lines,
            scan_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        scan_text = re.sub(
            r"<style\b[^>]*>.*?</style>",
            preserve_lines,
            scan_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
    scan_text = re.sub(r"<!--.*?-->", preserve_lines, scan_text, flags=re.DOTALL)
    for match in UI_ATTRIBUTE_RE.finditer(scan_text):
        line_number = scan_text.count("\n", 0, match.start(2)) + 1
        literals.append((line_number, match.group(2)))
    text_node_scan = re.sub(r"\{\{.*?\}\}", preserve_lines, scan_text, flags=re.DOTALL)
    for match in UI_TEXT_NODE_RE.finditer(text_node_scan):
        line_number = text_node_scan.count("\n", 0, match.start(1)) + 1
        literals.append((line_number, match.group(1)))
    return literals


def check_interface_copy(root_dir: Path = ROOT_DIR) -> Check:
    """检查小程序和后台模板中的非技术英文用户文案。"""
    issues: list[str] = []
    try:
        files, markers = _iter_model_target_files(root_dir, "interface")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return Check("系统界面中文文案", False, (f"模型解析失败: {exc}",))
    if not files:
        issues.append("没有可扫描的系统界面文件")
    all_text: list[str] = []
    for path in files:
        try:
            text = _read(path)
            all_text.append(text)
            for line_number, value in _interface_literals(path):
                if _has_untranslated_ui_text(value):
                    relative = path.relative_to(root_dir)
                    issues.append(
                        f"{relative}:{line_number}: 用户可见英文文案未中文化: {value.strip()}"
                    )
        except (OSError, UnicodeError) as exc:
            issues.append(f"{path}: 界面文件无法读取: {exc}")
    combined = "\n".join(all_text)
    issues.extend(
        f"系统界面: 缺少治理标识 {marker}"
        for marker in markers
        if marker not in combined
    )
    return Check("系统界面中文文案", not issues, tuple(issues))


def _is_technical_comment(body: str) -> bool:
    cleaned = body.strip()
    if not cleaned or COMMENT_DIRECTIVE_RE.search(cleaned):
        return True
    cleaned = re.sub(r"https?://\S+|www\.\S+", " ", cleaned)
    cleaned = re.sub(r"data:image/[^\s]+", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\\u[0-9a-fA-F]{4,8}", " ", cleaned)
    cleaned = cleaned.replace("stroke=", " ").strip()
    if not cleaned:
        return True
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]*", cleaned)
    if not words:
        return True
    if "/" in cleaned and not any(
        word.lower() not in TECHNICAL_COMMENT_WORDS for word in words
    ):
        return True
    return all(
        word.lower() in TECHNICAL_COMMENT_WORDS
        or word.upper() == word
        or "_" in word
        or any(char.isdigit() for char in word)
        for word in words
    )


def _natural_language_comments(path: Path) -> list[tuple[int, str]]:
    text = _read(path)
    comments: list[tuple[int, str]] = []
    if path.suffix.lower() == ".py":
        try:
            tokens = tokenize.generate_tokens(io.StringIO(text).readline)
            for token in tokens:
                if token.type != tokenize.COMMENT:
                    continue
                body = token.string[1:].strip()
                if not has_chinese(body) and not _is_technical_comment(body):
                    comments.append((token.start[0], body))
        except (IndentationError, SyntaxError, tokenize.TokenError) as exc:
            raise ValueError(f"Python 注释无法解析: {exc}") from exc
        return comments
    for line_number, body in _non_python_comment_bodies(text):
        if body and not has_chinese(body) and not _is_technical_comment(body):
            comments.append((line_number, body))
    return comments


def _non_python_comment_bodies(text: str) -> list[tuple[int, str]]:
    """提取非 Python 源码中的注释，并避开字符串、URL 和内嵌资源。"""
    comments: list[tuple[int, str]] = []
    block_close: str | None = None
    block_start = 0
    block_parts: list[str] = []
    quote: str | None = None
    for line_number, line in enumerate(text.splitlines(), start=1):
        if (
            block_close is None
            and quote is None
            and line.lstrip().startswith("/// <reference")
        ):
            continue
        index = 0
        escaped = False
        while index < len(line):
            if block_close is not None:
                end = line.find(block_close, index)
                if end < 0:
                    block_parts.append(line[index:])
                    break
                block_parts.append(line[index:end])
                comments.append((block_start, " ".join(block_parts).strip()))
                close_length = len(block_close)
                block_close = None
                block_parts = []
                index = end + close_length
                continue
            char = line[index]
            if quote is not None:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                index += 1
                continue
            if line.startswith("//", index):
                prefix = line[max(0, index - 6) : index].lower()
                if prefix.endswith("http:") or prefix.endswith("https:"):
                    index += 2
                    continue
                comments.append((line_number, line[index + 2 :].strip()))
                break
            if line.startswith("<!--", index):
                block_close, block_start = "-->", line_number
                block_parts = []
                index += 4
                continue
            if line.startswith("/*", index):
                block_close, block_start = "*/", line_number
                block_parts = []
                index += 2
                continue
            if char in {"'", '"', "`"}:
                quote = char
            index += 1
        if quote in {"'", '"'}:
            quote = None
    if block_close is not None and block_parts:
        comments.append((block_start, " ".join(block_parts).strip()))
    return comments


def check_code_comments(root_dir: Path = ROOT_DIR) -> Check:
    """检查全仓自然语言注释；协议和工具指令由白名单保留。"""
    issues: list[str] = []
    checked_files = 0
    try:
        files, markers = _iter_model_target_files(root_dir, "code_comments")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return Check("代码注释中文基线", False, (f"模型解析失败: {exc}",))
    for path in files:
        checked_files += 1
        try:
            for line_number, body in _natural_language_comments(path):
                relative = path.relative_to(root_dir)
                issues.append(
                    f"{relative}:{line_number}: 自然语言注释应使用中文: {body}"
                )
        except (OSError, ValueError, UnicodeError) as exc:
            issues.append(f"{path}: 注释无法扫描: {exc}")
    if not checked_files:
        issues.append("没有可扫描的代码文件")
    # required_markers 是模型自身的中文说明，不要求写入业务源文件。
    if not markers:
        issues.append("代码注释维度缺少 required_markers")
    return Check("代码注释中文基线", not issues, tuple(issues))


def check_authoritative_files(root_dir: Path = ROOT_DIR) -> Check:
    missing = [path for path in AUTHORITATIVE_FILES if not (root_dir / path).is_file()]
    return Check(
        "中文权威入口",
        not missing,
        tuple(f"缺少权威入口: {path}" for path in missing),
    )


def check_authoritative_references(root_dir: Path = ROOT_DIR) -> Check:
    issues: list[str] = []
    for relative, required in REQUIRED_REFERENCES.items():
        path = root_dir / relative
        if not path.is_file():
            issues.append(f"文件不存在: {relative}")
            continue
        text = _read(path)
        for token in required:
            if token not in text:
                issues.append(f"{relative}: 缺少治理标识 {token}")
    return Check("权威入口与治理引用", not issues, tuple(issues))


def check_project_state(root_dir: Path = ROOT_DIR) -> Check:
    result = parse_register(root_dir / "PROJECT-STATE.md")
    issues = tuple(issue for issue in result.issues if "中文" in issue)
    return Check("项目状态中文展示", not issues, issues)


def _task_metadata(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in _read(path).splitlines():
        match = re.match(r"^\s*(?:>\s*)?([a-z_]+):\s*(.*?)\s*$", line)
        if match:
            fields[match.group(1)] = match.group(2).strip()
        elif fields:
            break
    return fields


def check_task_status_labels(root_dir: Path = ROOT_DIR) -> Check:
    tasks_dir = root_dir / "docs" / "tasks"
    if not tasks_dir.is_dir():
        return Check("任务中文状态标签", False, ("缺少 docs/tasks 目录",))
    issues: list[str] = []
    checked = 0
    for path in sorted(tasks_dir.glob("*.md")):
        metadata = _task_metadata(path)
        if "status" not in metadata:
            continue
        checked += 1
        status = metadata.get("status", "")
        expected = STATUS_LABELS.get(status)
        actual = metadata.get("status_label", "")
        if expected is None:
            issues.append(
                f"{path.relative_to(root_dir)}: status 使用了未知机器状态 {status}"
            )
        elif actual != expected:
            issues.append(
                f"{path.relative_to(root_dir)}: status_label 应为 {expected}，实际为 {actual or '<empty>'}"
            )
    if not checked:
        issues.append("未发现带 status 元数据的任务指令")
    return Check("任务中文状态标签", not issues, tuple(issues))


def _human_lines_without_fences(text: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    in_fence = False
    for line_no, line in enumerate(text.splitlines(), start=1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            lines.append((line_no, line))
    return lines


def check_project_state_no_bare_status(root_dir: Path = ROOT_DIR) -> Check:
    path = root_dir / "PROJECT-STATE.md"
    if not path.is_file():
        return Check("禁止裸机器状态码", False, ("PROJECT-STATE.md 不存在",))
    issues: list[str] = []
    for line_no, line in _human_lines_without_fences(_read(path)):
        if re.match(
            r"^\s*\|.*\|\s*(active|blocked|completed|pending|deferred|historical)\s*\|",
            line,
            re.IGNORECASE,
        ):
            continue
        if re.match(
            r"^\s*(?:>\s*)?(?:status|status_label)\s*:",
            line,
            re.IGNORECASE,
        ):
            continue
        human_readable_line = HUMAN_STATUS_GROUP_RE.sub("", line)
        match = MACHINE_STATUS_RE.search(human_readable_line)
        if match:
            issues.append(
                f"PROJECT-STATE.md:{line_no}: 状态码 {match.group(1)} 缺少中文标签"
            )
    return Check("禁止裸机器状态码", not issues, tuple(issues))


def check_governance_file_coverage(root_dir: Path = ROOT_DIR) -> Check:
    issues: list[str] = []
    checked = 0
    for relative in GOVERNANCE_FILES:
        path = root_dir / relative
        if not path.is_file():
            issues.append(f"文件不存在: {relative}")
            continue
        checked += 1
        if not has_chinese(_read(path)):
            issues.append(f"缺少中文人类可读内容: {relative}")
    if checked == 0:
        issues.append("没有可统计的治理文件")
    return Check("治理文档中文覆盖", not issues, tuple(issues))


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _literal_cli_text(path: Path) -> tuple[str, ...]:
    """提取 argparse 中真正展示给 CLI 使用者的字面量文本。"""
    tree = ast.parse(_read(path), filename=str(path))
    values: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        call_name = _call_name(node)
        if call_name not in {"ArgumentParser", "add_argument"}:
            continue
        for keyword in node.keywords:
            if keyword.arg not in {"description", "epilog", "help"}:
                continue
            if isinstance(keyword.value, ast.Constant) and isinstance(
                keyword.value.value, str
            ):
                values.append(keyword.value.value)
    return tuple(values)


def _high_risk_readable_text(path: Path) -> tuple[str, ...]:
    if path.suffix != ".py":
        return (_read(path),)
    return _literal_cli_text(path)


def check_high_risk_path_readability(root_dir: Path = ROOT_DIR) -> Check:
    issues: list[str] = []
    for relative in HIGH_RISK_FILES:
        path = root_dir / relative
        if not path.is_file():
            issues.append(f"高风险文件不存在: {relative}")
            continue
        try:
            text = "\n".join(_high_risk_readable_text(path))
        except (OSError, SyntaxError) as exc:
            issues.append(f"{relative}: 无法解析高风险用户可见文本: {exc}")
            continue
        required = HIGH_RISK_REQUIRED_TEXT.get(relative, ())
        missing = [token for token in required if token not in text]
        if missing:
            issues.append(f"{relative}: 高风险语义断言缺失: {', '.join(missing)}")
    return Check("高风险路径中文可读性", not issues, tuple(issues))


def build_report(root_dir: Path = ROOT_DIR) -> dict[str, object]:
    checks = (
        check_governance_model,
        check_authoritative_files,
        check_authoritative_references,
        check_project_state,
        check_task_status_labels,
        check_project_state_no_bare_status,
        check_governance_file_coverage,
        check_documentation_contract,
        check_collaboration_contract,
        check_process_contract,
        check_delivery_contract,
        check_interface_copy,
        check_code_comments,
        check_high_risk_path_readability,
    )
    results = [check(root_dir) for check in checks]
    existing = [
        root_dir / relative
        for relative in GOVERNANCE_FILES
        if (root_dir / relative).is_file()
    ]
    chinese = [path for path in existing if has_chinese(_read(path))]
    issues = [
        f"{result.name}: {detail}"
        for result in results
        if not result.passed
        for detail in result.details
    ]
    dimension_checks = {
        "documentation": (
            "中文权威入口",
            "权威入口与治理引用",
            "治理文档中文覆盖",
            "中文治理维度：文档",
        ),
        "interface": ("系统界面中文文案", "高风险路径中文可读性"),
        "collaboration": ("中文治理维度：协作沟通",),
        "process": (
            "项目状态中文展示",
            "任务中文状态标签",
            "禁止裸机器状态码",
            "中文治理维度：流程规范",
        ),
        "delivery": ("中文治理维度：交付物",),
        "code_comments": ("代码注释中文基线",),
    }
    dimension_report: dict[str, object] = {}
    for dimension_id, names in dimension_checks.items():
        selected = [result for result in results if result.name in names]
        dimension_report[dimension_id] = {
            "name": DIMENSION_NAMES[dimension_id],
            "passed": bool(selected) and all(result.passed for result in selected),
            "checks": [result.to_dict() for result in selected],
        }
    return {
        "status": "passed" if not issues else "failed",
        "checks": [result.to_dict() for result in results],
        "coverage": {
            "governance_files": len(existing),
            "files_with_chinese": len(chinese),
            "ratio": round(len(chinese) / len(existing), 4) if existing else 0.0,
            "dimensions": dimension_report,
            "dimension_ratio": round(
                sum(
                    1
                    for item in dimension_report.values()
                    if isinstance(item, dict) and item.get("passed") is True
                )
                / len(dimension_report),
                4,
            )
            if dimension_report
            else 0.0,
        },
        "issues": issues,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查 Harness P0 中文治理")
    parser.add_argument("--root", type=Path, default=ROOT_DIR)
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--json-out", type=Path)
    return parser.parse_args(argv)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    if path.exists():
        raise FileExistsError(f"拒绝覆盖已有中文治理报告: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = build_report(args.root.resolve())
        if args.json_out:
            _write_json(args.json_out, report)
    except (OSError, ValueError) as exc:
        print(f"[中文治理] FAIL {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.summary:
        coverage = report["coverage"]
        print(
            "chinese_governance "
            f"status={report['status']} files={coverage['governance_files']} "
            + f"chinese={coverage['files_with_chinese']} coverage={coverage['ratio']} "
            + f"dimensions={coverage['dimension_ratio']} failed={len(report['issues'])}"
        )
    elif report["issues"]:
        print("[中文治理] FAIL")
        for issue in report["issues"]:
            print(f"  - {issue}")
    else:
        print(f"[中文治理] PASS coverage={report['coverage']['ratio']}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
