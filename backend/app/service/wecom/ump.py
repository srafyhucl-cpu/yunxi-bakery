"""企微统一媒体协议解析工具。"""

import re
from urllib.parse import unquote

UMP_PATTERN = re.compile(r"\[UMP:\s*(.*?)\]")


def parse_ump_tags(text: str) -> tuple[str, list[dict[str, str]]]:
    """从回复文本中解析 UMP 标记，返回纯文本和参数列表。"""
    ump_list: list[dict[str, str]] = []

    def _replacer(match: re.Match[str]) -> str:
        raw = match.group(1)
        params: dict[str, str] = {}
        for pair in raw.split("&"):
            if "=" in pair:
                key, value = pair.split("=", 1)
                params[key.strip()] = unquote(value.strip())
        if params:
            ump_list.append(params)
        return ""

    clean_text = UMP_PATTERN.sub(_replacer, text).strip()
    return clean_text, ump_list
