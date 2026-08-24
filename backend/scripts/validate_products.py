"""
商品数据与价格对齐校验脚本。

异步连接 SQLite，逐条校验知识库中 765 条商品数据：
- 价格字段：非空、合法数字、核心商品价格区间
- 文本字段：emoji/控制字符导致的截断、乱码、未闭合符号
输出 [WARNING]/[ERROR] 缺陷清单。
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import aiosqlite

from app.config import settings
from app.database import PRAGMA_STATEMENTS
from app.logger import setup_logger

logger = setup_logger()

# 核心敏感商品价格基准（名称关键字 → (最低价, 最高价)）
CORE_PRICE_RANGES: dict[str, tuple[float, float]] = {
    "提拉米苏": (48, 140),
    "生日蛋糕": (100, 400),
    "北海道": (80, 200),
    "可露丽": (10, 40),
}

# 价格提取正则：匹配 "XXX元" 格式（支持小数）
PRICE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)元")


async def get_all_products() -> list[dict]:
    """从知识库读取所有商品（category='product'）。"""
    async with aiosqlite.connect(settings.DB_PATH) as db:
        for pragma in PRAGMA_STATEMENTS:
            await db.execute(pragma)
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, category, title, content, keywords, priority "
            "FROM knowledge_base WHERE category = 'product' "
            "ORDER BY id ASC"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


def extract_prices(content: str) -> list[float]:
    """从 content 字段中提取所有价格数值。"""
    return [float(m) for m in PRICE_PATTERN.findall(content)]


def has_encoding_issues(text: str) -> str | None:
    """
    检测文本中的编码异常。

    返回 None 表示正常，返回描述字符串表示有问题。
    """
    # 检查代理字符/替换字符
    if "\ufffd" in text:
        return "包含替换字符 U+FFFD"

    # 检查孤立代理项（surrogate）
    for ch in text:
        if 0xD800 <= ord(ch) <= 0xDFFF:
            return f"包含孤立代理项 U+{ord(ch):04X}"

    # 检查控制字符（允许 \t \n \r）
    for i, ch in enumerate(text):
        cp = ord(ch)
        if cp < 0x20 and cp not in (0x09, 0x0A, 0x0D):
            return f"包含控制字符 U+{cp:04X} 位于位置 {i}"

    # 检查未闭合的括号/引号
    pairs: list[tuple[str, str, str]] = [
        ("(", ")", "圆括号(半角)"),
        ("（", "）", "圆括号(全角)"),
        ("【", "】", "方括号"),
        ("「", "」", "尖括号"),
    ]
    for open_ch, close_ch, name in pairs:
        open_count = text.count(open_ch)
        close_count = text.count(close_ch)
        if open_count != close_count:
            return f"{name}未闭合 (开={open_count}, 闭={close_count})"

    return None


def check_title_anomaly(title: str) -> str | None:
    """检查标题是否包含异常字符。"""
    # 问号占位符（通常是 emoji 未正确解析）
    if "\ufffd" in title:
        return f"标题包含替换字符: {title}"

    # 连续问号
    if "??" in title:
        return f"标题包含连续问号（疑似 emoji 残留）: {title}"

    # 标题极短（＜2个中文字符或空的商品名）
    stripped = title.strip()
    if len(stripped) < 2:
        return f"标题过短: '{title}'"

    return None


def validate_product(product: dict, index: int) -> list[str]:
    """对单条商品执行完整校验，返回缺陷列表。"""
    issues: list[str] = []
    pid = product["id"]
    title = product.get("title", "")
    content = product.get("content", "")
    keywords = product.get("keywords", "")

    # 1. 标题校验
    title_issue = check_title_anomaly(title)
    if title_issue:
        issues.append(f"[ERROR]  行{pid} 标题异常: {title_issue}")

    # 2. 内容为空
    if not content or not content.strip():
        issues.append(f"[ERROR]  行{pid} '{title}' content 字段为空")
        return issues

    # 3. 编码异常检测
    for field_name, field_value in [
        ("title", title),
        ("content", content),
        ("keywords", keywords),
    ]:
        issue = has_encoding_issues(field_value)
        if issue:
            issues.append(f"[WARNING] 行{pid} '{title}' {field_name} 编码异常: {issue}")

    # 4. 价格提取与校验
    prices = extract_prices(content)
    if not prices:
        issues.append(f"[ERROR]  行{pid} '{title}' content 中未找到价格（无 X元 格式）")
    else:
        # 检查是否有非数字内容
        for price_str in PRICE_PATTERN.findall(content):
            try:
                float(price_str)
            except ValueError:
                issues.append(f"[ERROR]  行{pid} '{title}' 价格非法: '{price_str}'")

        # 核心商品价格区间校验
        for keyword, (min_price, max_price) in CORE_PRICE_RANGES.items():
            if keyword in title or keyword in keywords:
                for p in prices:
                    if p < min_price or p > max_price:
                        issues.append(
                            f"[WARNING] 行{pid} '{title}' 价格 {p}元 超出"
                            f" [{keyword}] 基准区间 [{min_price}, {max_price}]"
                        )

    # 5. 省略号/字段截断检测
    if content.rstrip().endswith(("…", "...")):
        issues.append(f"[WARNING] 行{pid} '{title}' content 以省略号结尾，可能被截断")

    # 6. 分类信息缺失
    if "分类:" not in content and "分类:" not in keywords:
        issues.append(f"[WARNING] 行{pid} '{title}' content 缺少分类信息")

    return issues


async def main() -> None:
    """主入口：获取所有商品、逐条校验、输出报告。"""
    print("=" * 60)
    print("  芸熙烘焙 商品数据校验报告")
    print("=" * 60)

    products = await get_all_products()
    total = len(products)
    print(f"\n  商品总数: {total}")
    print(f"  基准路径: {settings.DB_PATH}\n")

    all_issues: list[tuple[int, str, str]] = []  # (id, title, issue)
    for idx, product in enumerate(products, start=1):
        issues = validate_product(product, idx)
        for issue in issues:
            all_issues.append((product["id"], product["title"], issue))

    # 输出缺陷清单
    if all_issues:
        print("-" * 60)
        print(f"  发现 {len(all_issues)} 个缺陷:\n")
        for pid, title, issue in all_issues:
            print(f"  {issue}")
        print("-" * 60)
        error_count = sum(1 for _, _, i in all_issues if i.startswith("[ERROR]"))
        warning_count = len(all_issues) - error_count
        print(f"\n  结果: {error_count} ERROR, {warning_count} WARNING\n")
        sys.exit(1 if error_count > 0 else 0)
    else:
        print(f"  ✅ 全部 {total} 条商品数据校验通过，无异常\n")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
