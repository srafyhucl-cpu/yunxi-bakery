"""
validate_products.py 单元测试。

使用内存 SQLite 构造包含脏数据、截断 emoji、空价格、正常数据的多种 Case，
确保校验脚本的漏报率为 0。
"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import aiosqlite

from scripts.validate_products import (
    extract_prices,
    has_encoding_issues,
    check_title_anomaly,
    validate_product,
)

# ── 辅助：创建内存知识库 ──


async def create_memory_db(rows: list[dict]) -> aiosqlite.Connection:
    """创建内存 SQLite 并插入测试数据。"""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.execute(
        """CREATE TABLE knowledge_base (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            keywords TEXT DEFAULT '',
            priority INTEGER DEFAULT 0
        )"""
    )
    for row in rows:
        await conn.execute(
            "INSERT INTO knowledge_base (id, category, title, content, keywords, priority) "
            "VALUES (?, 'product', ?, ?, ?, 1)",
            (row["id"], row["title"], row["content"], row.get("keywords", "")),
        )
    await conn.commit()
    return conn


def run_validate(rows: list[dict]) -> list[tuple[int, str, str]]:
    """对测试数据执行 validate_product 并返回 issues。"""

    async def _run():
        conn = await create_memory_db(rows)
        cursor = await conn.execute(
            "SELECT id, category, title, content, keywords, priority "
            "FROM knowledge_base WHERE category = 'product' ORDER BY id ASC"
        )
        db_rows = await cursor.fetchall()
        await conn.close()

        all_issues: list[tuple[int, str, str]] = []
        for idx, row in enumerate(db_rows, start=1):
            product = dict(row)
            issues = validate_product(product, idx)
            for issue in issues:
                all_issues.append((product["id"], product["title"], issue))
        return all_issues

    return asyncio.run(_run())


# ══════════════════════════════════════════
# Tool functions: extract_prices
# ══════════════════════════════════════════


def test_extract_prices_normal() -> None:
    """正常价格提取。"""
    result = extract_prices("分类: 甜品 | 标准规格: 48元, 配送: 自提")
    assert result == [48.0], f"Expected [48.0], got {result}"


def test_extract_prices_multiple() -> None:
    """多个价格。"""
    result = extract_prices("6寸 128元 / 8寸 178元 / 10寸 278元")
    assert result == [128.0, 178.0, 278.0], f"Expected [128, 178, 278], got {result}"


def test_extract_prices_decimal() -> None:
    """小数价格。"""
    result = extract_prices("标准规格: 19.9元")
    assert result == [19.9], f"Expected [19.9], got {result}"


def test_extract_prices_empty() -> None:
    """无价格。"""
    result = extract_prices("分类: 甜品 | 仅展示")
    assert result == [], f"Expected [], got {result}"


# ══════════════════════════════════════════
# Tool functions: has_encoding_issues
# ══════════════════════════════════════════


def test_encoding_normal() -> None:
    """正常文本应返回 None。"""
    assert has_encoding_issues("经典提拉米苏盒子 48元") is None


def test_encoding_replacement_char() -> None:
    """替换字符 U+FFFD。"""
    assert has_encoding_issues("奶酪\ufffd面包") is not None


def test_encoding_control_char() -> None:
    """异常控制字符。"""
    assert has_encoding_issues("奶酪\x00面包") is not None


def test_encoding_bracket_mismatch() -> None:
    """括号未闭合。"""
    issue = has_encoding_issues("商品（仅展示")
    assert issue is not None and "未闭合" in issue


def test_encoding_bracket_halfwidth_mismatch() -> None:
    """
    中英文括号混用：(xxx）或（xxx)
    这是种子数据常见的真实问题，应被检测到。
    """
    # 英文开 + 中文闭
    issue1 = has_encoding_issues("商品(仅展示）")
    assert issue1 is not None, "应检测到 ( 和 ） 不匹配"
    # 中文开 + 英文闭
    issue2 = has_encoding_issues("商品（仅展示)")
    assert issue2 is not None, "应检测到（ 和 ) 不匹配"


# ══════════════════════════════════════════
# Tool functions: check_title_anomaly
# ══════════════════════════════════════════


def test_title_normal() -> None:
    """正常标题应返回 None。"""
    assert check_title_anomaly("提拉米苏") is None


def test_title_replacement_char() -> None:
    """替换字符。"""
    assert check_title_anomaly("奶酪\ufffd面包") is not None


def test_title_double_question() -> None:
    """连续问号（emoji 残留）。"""
    assert check_title_anomaly("??抹茶巧克力") is not None


def test_title_too_short() -> None:
    """过短标题。"""
    assert check_title_anomaly("") is not None
    assert check_title_anomaly("a") is not None


# ══════════════════════════════════════════
# Integration: validate_product
# ══════════════════════════════════════════


def test_validate_normal_product() -> None:
    """正常商品应无缺陷。"""
    rows = [
        {
            "id": 1,
            "title": "经典提拉米苏盒子",
            "content": "分类: 甜品小食类 | 标准规格: 48元，配送方式: 同城配送",
            "keywords": "提拉米苏盒子",
        }
    ]
    issues = run_validate(rows)
    assert len(issues) == 0, f"正常商品不应有缺陷: {issues}"


def test_validate_empty_content() -> None:
    """空 content 应报 ERROR。"""
    rows = [
        {
            "id": 2,
            "title": "空内容商品",
            "content": "",
            "keywords": "测试",
        }
    ]
    issues = run_validate(rows)
    error_issues = [i for i in issues if "[ERROR]" in i[2]]
    assert len(error_issues) > 0, "空内容应报 ERROR"


def test_validate_no_price() -> None:
    """缺少价格应报 ERROR。"""
    rows = [
        {
            "id": 3,
            "title": "无价格商品",
            "content": "分类: 甜品 | 仅展示，无价格",
            "keywords": "测试",
        }
    ]
    issues = run_validate(rows)
    error_issues = [i for i in issues if "[ERROR]" in i[2]]
    assert len(error_issues) > 0, "无价格应报 ERROR"


def test_validate_encoding_issue() -> None:
    """编码异常应报 WARNING。"""
    rows = [
        {
            "id": 4,
            "title": "异常商品",
            "content": "分类: 甜品 | 标准规格: 48元",
            "keywords": "\x00测试",  # 控制字符
        }
    ]
    issues = run_validate(rows)
    warning_issues = [i for i in issues if "[WARNING]" in i[2]]
    assert len(warning_issues) > 0, "编码异常应报 WARNING"


def test_validate_price_out_of_range() -> None:
    """价格超出基准区间应报 WARNING。"""
    rows = [
        {
            "id": 5,
            "title": "提拉米苏生日蛋糕",
            "content": "分类: 蛋糕 | 8寸: 999元",
            "keywords": "提拉米苏,生日蛋糕",
        }
    ]
    issues = run_validate(rows)
    warning_issues = [i for i in issues if "[WARNING]" in i[2] and "超出" in i[2]]
    assert len(warning_issues) > 0, "价格超出区间应报 WARNING"


def test_validate_truncated_content() -> None:
    """省略号结尾应报 WARNING。"""
    rows = [
        {
            "id": 6,
            "title": "被截断商品",
            "content": "分类: 甜品 | 规格: 6寸 价格: 128元 配送方式: 同城配送…",
            "keywords": "测试",
        }
    ]
    issues = run_validate(rows)
    warning_issues = [i for i in issues if "[WARNING]" in i[2] and "截断" in i[2]]
    assert len(warning_issues) > 0, "省略号结尾应报 WARNING"


def test_validate_missing_category() -> None:
    """缺少分类信息应报 WARNING。"""
    rows = [
        {
            "id": 7,
            "title": "无分类商品",
            "content": "标准规格: 48元",
            "keywords": "",
        }
    ]
    issues = run_validate(rows)
    warning_issues = [i for i in issues if "[WARNING]" in i[2] and "缺少分类" in i[2]]
    assert len(warning_issues) > 0, "缺少分类应报 WARNING"


def test_validate_mixed_data() -> None:
    """
    混合数据：正常 + 脏数据 + 空价格 + 正常。
    确保校验函数正确处理每条记录，不互相干扰。
    """
    rows = [
        {"id": 10, "title": "正常商品", "content": "分类: 甜品 | 48元", "keywords": ""},
        {"id": 11, "title": "??脏数据", "content": "分类: 面包 | 15元", "keywords": ""},
        {"id": 12, "title": "空价格", "content": "分类: 蛋糕 | 仅展示", "keywords": ""},
        {
            "id": 13,
            "title": "另一个正常",
            "content": "分类: 饮品 | 38元",
            "keywords": "",
        },
    ]
    issues = run_validate(rows)
    # 第1条正常 → 无缺陷
    # 第2条标题异常 → 有缺陷
    # 第3条无价格 → ERROR
    # 第4条正常 → 无缺陷
    issue_ids = [pid for pid, _, _ in issues]
    assert 10 not in issue_ids, "正常商品不应有缺陷"
    assert 11 in issue_ids, "脏数据应被检出"
    assert 12 in issue_ids, "空价格应被检出"
    assert 13 not in issue_ids, "正常商品不应有缺陷"


# ══════════════════════════════════════════
# 入口
# ══════════════════════════════════════════

if __name__ == "__main__":
    test_functions = [
        (
            "extract_prices",
            [
                test_extract_prices_normal,
                test_extract_prices_multiple,
                test_extract_prices_decimal,
                test_extract_prices_empty,
            ],
        ),
        (
            "has_encoding_issues",
            [
                test_encoding_normal,
                test_encoding_replacement_char,
                test_encoding_control_char,
                test_encoding_bracket_mismatch,
                test_encoding_bracket_halfwidth_mismatch,
            ],
        ),
        (
            "check_title_anomaly",
            [
                test_title_normal,
                test_title_replacement_char,
                test_title_double_question,
                test_title_too_short,
            ],
        ),
        (
            "validate_product",
            [
                test_validate_normal_product,
                test_validate_empty_content,
                test_validate_no_price,
                test_validate_encoding_issue,
                test_validate_price_out_of_range,
                test_validate_truncated_content,
                test_validate_missing_category,
                test_validate_mixed_data,
            ],
        ),
    ]

    passed = 0
    failed = 0
    for group_name, funcs in test_functions:
        print(f"\n  [{group_name}]")
        for fn in funcs:
            try:
                fn()
                print(f"    ✅ {fn.__name__}")
                passed += 1
            except AssertionError as e:
                print(f"    ❌ {fn.__name__}: {e}")
                failed += 1
            except Exception as e:
                print(f"    ❌ {fn.__name__}: {type(e).__name__}: {e}")
                failed += 1

    print(f"\n  {'=' * 30}")
    print(f"  结果: {passed} passed, {failed} failed")
    sys.exit(1 if failed > 0 else 0)
