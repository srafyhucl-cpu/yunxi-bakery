"""有赞同步原文到顾客可读字段的清洗规则。

有赞商品描述是运营后台导出的原文，带内部字段名、秒级库存明细和平台链接。
这些内容只做展示前清洗，不改变同步落库的原始数据，便于随时复核清洗口径。
"""

import re

GENERIC_SPEC_TOKENS = frozenset({"商品", "价格", "推荐", "蛋糕", "在售", "现做"})
MAX_SPEC_TOKEN_LENGTH = 18
# 有赞同步原文里的内部字段与导出痕迹，不对顾客展示
IMPORT_NOISE_LINE_PATTERNS = (
    re.compile(r"^[-\s]*商品名称[:：]"),
    re.compile(r"^[-\s]*在售状态[:：]"),
    re.compile(r"^[-\s]*商品规格及秒级实时库存明细"),
    re.compile(r"^[-\s]*规格(?:型号)?【.*】.*(?:售价|库存)"),
    re.compile(r"^[-\s]*规格[:：].*(?:售价|库存)"),
    re.compile(r"^[-\s]*可定制.*SPU 自定义属性"),
    re.compile(r"^[-\s]*定制加料选项[:：]"),
    re.compile(r"^[-\s]*商品特征与配方属性标签[:：]"),
    re.compile(r"^[-\s]*直购下单链接[:：]"),
)
MAX_SUBTITLE_LENGTH = 36
# 同步原文中属于平台导出痕迹的标记，不对顾客展示
IMPORT_NOISE_MARKERS = ("h5.youzan.com", "yzcdn.cn", "[UMP")


def is_import_noise_line(line: str) -> bool:
    """判断同步原文行是否为不对顾客展示的内部字段或导出痕迹。"""
    text = line.strip()
    if not text:
        return True
    if text.startswith("http://") or text.startswith("https://"):
        return True
    if any(marker in text for marker in IMPORT_NOISE_MARKERS):
        return True
    return any(pattern.search(text) for pattern in IMPORT_NOISE_LINE_PATTERNS)


def build_customer_description(content: str) -> str:
    """剥离有赞同步原文中的内部字段、库存明细与导出痕迹，保留可读正文。"""
    lines = [line.strip() for line in (content or "").splitlines()]
    kept = [line for line in lines if line and not is_import_noise_line(line)]
    return "\n".join(kept)


def build_customer_subtitle(description: str) -> str:
    """用清洗后的描述首句作为卡片副标题，避免把字段名当卖点。"""
    for raw_line in (description or "").splitlines():
        line = raw_line.strip()
        if not line or line.endswith("：") or line.endswith(":"):
            continue
        compact = " ".join(line.split())
        if len(compact) <= MAX_SUBTITLE_LENGTH:
            return compact
        return f"{compact[:MAX_SUBTITLE_LENGTH]}..."
    return ""


def build_customer_specs(tags: list[str], title: str) -> list[str]:
    """过滤规格标签噪声，只保留可读的规格与属性词。"""
    specs: list[str] = []
    seen: set[str] = set()
    title_token = title.strip()
    for raw_tag in tags:
        token = raw_tag.strip()
        if not token or token in seen:
            continue
        if token in GENERIC_SPEC_TOKENS or token == title_token:
            continue
        if token.isdigit() or len(token) > MAX_SPEC_TOKEN_LENGTH:
            continue
        seen.add(token)
        specs.append(token)
    return specs


__all__ = [
    "build_customer_description",
    "build_customer_specs",
    "build_customer_subtitle",
    "is_import_noise_line",
]
