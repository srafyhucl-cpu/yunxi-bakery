from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_encoding_module() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "check_text_encoding.py"
    )
    spec = importlib.util.spec_from_file_location("check_text_encoding", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_scan_file_passes_normal_chinese(tmp_path: Path) -> None:
    encoding = load_encoding_module()
    text_file = tmp_path / "normal.md"
    text_file.write_text("芸熙烘焙 Harness Engineering\n", encoding="utf-8")

    assert encoding._scan_file(text_file) == []


def test_scan_file_detects_replacement_character(tmp_path: Path) -> None:
    encoding = load_encoding_module()
    text_file = tmp_path / "broken.md"
    text_file.write_text("中文\ufffd坏字符\n", encoding="utf-8")

    issues = encoding._scan_file(text_file)

    assert any("replacement character" in issue for issue in issues)


def test_scan_file_detects_mojibake_marker(tmp_path: Path) -> None:
    encoding = load_encoding_module()
    text_file = tmp_path / "mojibake.md"
    text_file.write_text("\u947a\u54e5\u5553\n", encoding="utf-8")

    issues = encoding._scan_file(text_file)

    assert any("mojibake" in issue for issue in issues)


def test_scan_file_detects_non_utf8_bytes(tmp_path: Path) -> None:
    encoding = load_encoding_module()
    text_file = tmp_path / "gbk.md"
    text_file.write_bytes("芸熙".encode("gbk"))

    issues = encoding._scan_file(text_file)

    assert any("无法按 UTF-8 解码" in issue for issue in issues)
