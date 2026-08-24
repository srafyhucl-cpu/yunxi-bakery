"""
编码红线规则自测模块。

为全部 12 条编码红线编写违规样本和合规样本的端到端验证，
确保 check_project.py 的扫描规则不会因为代码重构或正则漂移而失效。
每次 commit 前由 pre-commit 钩子 `check-redline-selftest` 自动运行。
"""

import sys
from pathlib import Path

# 将项目根目录加入 sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from scripts.check_project import RED_LINE_RULES, ScanRule, scan_rule  # noqa: E402


class TestRedLineRuleViolations:
    """验证每条红线能正确检测违规样本。"""

    def _run_rule_on_text(self, rule: ScanRule, content: str) -> list[str]:
        """将文本写入项目目录内临时文件，运行规则扫描，返回匹配行列表。"""
        # 必须在项目目录内创建临时文件，因为 scan_rule 中会调用 relative_to(ROOT_DIR)
        tmp_path = ROOT_DIR / "tests" / f".tmp_redline_test_{hash(content) & 0xFFFF}.py"
        try:
            tmp_path.write_text(content, encoding="utf-8")
            result = scan_rule(
                ScanRule(rule.name, rule.pattern, (tmp_path,), rule.should_block)
            )
            return result.details
        finally:
            tmp_path.unlink(missing_ok=True)

    def _assert_violations(
        self, rule: ScanRule, violation_code: str, expected_line_count: int = 1
    ) -> None:
        """断言违规代码被正确检测。"""
        details = self._run_rule_on_text(rule, violation_code)
        assert len(details) >= expected_line_count, (
            f"规则[{rule.name}]应检测到至少 {expected_line_count} 处违规，实际只有 {len(details)} 处。\n"
            f"违规代码:\n{violation_code}\n"
            f"正则: {rule.pattern}"
        )

    def _assert_no_violations(self, rule: ScanRule, compliant_code: str) -> None:
        """断言合规代码不被误报。"""
        details = self._run_rule_on_text(rule, compliant_code)
        assert len(details) == 0, (
            f"规则[{rule.name}]不应检测到违规（误报！）。\n"
            f"合规代码:\n{compliant_code}\n"
            f"误报详情: {details}"
        )

    # ── 规则 1: 禁止 Optional/Union ─────────────────────────────────────────────

    def test_rule_1_optional_union_violation(self) -> None:
        """检测 Optional[X] 和 Union[X,Y] 违规。"""
        code = """
from typing import Optional, Union

def get_name(user_id: Optional[int]) -> Optional[str]:
    return None

def parse(value: Union[str, int]) -> str:
    return str(value)
"""
        self._assert_violations(RED_LINE_RULES[0], code, expected_line_count=2)

    def test_rule_1_optional_union_compliant(self) -> None:
        """X|None 和 X|Y 语法不误报。"""
        code = """
def get_name(user_id: int | None) -> str | None:
    return None

def parse(value: str | int) -> str:
    return str(value)
"""
        self._assert_no_violations(RED_LINE_RULES[0], code)

    # ── 规则 2: 禁止 TODO 占位 ───────────────────────────────────────────────────

    def test_rule_2_todo_violation(self) -> None:
        """检测 # TODO 占位符。"""
        code = """# TODO 这里需要重构\nx = 1\n"""
        self._assert_violations(RED_LINE_RULES[1], code)

    def test_rule_2_todo_compliant(self) -> None:
        """普通注释不误报。"""
        code = """# 这里需要重构\nx = 1\n"""
        self._assert_no_violations(RED_LINE_RULES[1], code)

    # ── 规则 3: 禁止 SELECT 星号 ─────────────────────────────────────────────────

    def test_rule_3_select_star_violation(self) -> None:
        """检测 SELECT *。"""
        code = """sql = "SELECT * FROM users"\n"""
        self._assert_violations(RED_LINE_RULES[2], code)

    def test_rule_3_select_star_compliant(self) -> None:
        """SELECT 具体字段不误报。"""
        code = """sql = "SELECT id, name FROM users"\n"""
        self._assert_no_violations(RED_LINE_RULES[2], code)

    # ── 规则 4: app 内禁止依赖 miniapp service 兼容层 ───────────────────────────

    def test_rule_4_import_miniapp_service_violation(self) -> None:
        """检测内部代码依赖 miniapp service 兼容层。"""
        code = """from app.service.miniapp_payment import MiniappPaymentService\n"""
        self._assert_violations(RED_LINE_RULES[3], code)

    def test_rule_4_import_miniapp_service_compliant(self) -> None:
        """内部代码应直接依赖 canonical 域服务。"""
        code = """from app.service.order.payment_runtime import OrderPaymentRuntimeService\n"""
        self._assert_no_violations(RED_LINE_RULES[3], code)

    # ── 规则 5: 根 API 兼容文件仅作为兼容入口 ─────────────────────────────────

    def test_rule_5_root_api_real_router_violation(self) -> None:
        """检测根 API 兼容文件重新承载真实路由实现。"""
        code = """from fastapi import APIRouter\nrouter = APIRouter()\n"""
        self._assert_violations(RED_LINE_RULES[4], code, expected_line_count=2)

    def test_rule_5_root_api_wrapper_compliant(self) -> None:
        """根 API 兼容文件只指向 canonical 模块。"""
        code = (
            "import sys\n"
            "from app.api.admin import products as _module\n"
            "sys.modules[__name__] = _module\n"
        )
        self._assert_no_violations(RED_LINE_RULES[4], code)

    # ── 规则 6: api 层禁止直接导入 repository ───────────────────────────────────

    def test_rule_6_api_import_repo_violation(self) -> None:
        """检测 api 层直接导入 repository。"""
        code = """from app.repository.message_repo import MessageRepo\n"""
        self._assert_violations(RED_LINE_RULES[5], code)

    def test_rule_6_api_import_repo_compliant(self) -> None:
        """api 层导入 service 不误报。"""
        code = """from app.service.chat import ChatService\n"""
        self._assert_no_violations(RED_LINE_RULES[5], code)

    # ── 规则 7: service 层禁止直连 aiosqlite ────────────────────────────────────

    def test_rule_7_service_aiosqlite_violation(self) -> None:
        """检测 service 层直接导入 aiosqlite。"""
        code = """import aiosqlite\nconn = aiosqlite.connect(":memory:")\n"""
        self._assert_violations(RED_LINE_RULES[6], code)

    def test_rule_7_service_aiosqlite_compliant(self) -> None:
        """service 层通过 repository 访问数据库不误报。"""
        code = """from app.repository.database import db_session_scope\n"""
        self._assert_no_violations(RED_LINE_RULES[6], code)

    # ── 规则 8: models 层禁止引用上层模块 ────────────────────────────────────────

    def test_rule_8_models_upper_violation(self) -> None:
        """检测 models 层引用 service/repository/api。"""
        code = """from app.service.wecom.client import send_message\n"""
        self._assert_violations(RED_LINE_RULES[7], code)

    def test_rule_8_models_upper_compliant(self) -> None:
        """models 层只使用标准库和 pydantic 不误报。"""
        code = """from pydantic import BaseModel\nfrom datetime import datetime\n"""
        self._assert_no_violations(RED_LINE_RULES[7], code)

    # ── 规则 9: 禁止 SQL f-string 拼接 ──────────────────────────────────────────

    def test_rule_9_sql_fstring_violation(self) -> None:
        """检测 SQL f-string 拼接。"""
        code = 'sql = f"SELECT * FROM users WHERE id = {uid}"\n'
        self._assert_violations(RED_LINE_RULES[8], code)

    def test_rule_9_sql_fstring_compliant(self) -> None:
        """参数化查询不误报。"""
        code = 'sql = "SELECT id, name FROM users WHERE id = ?"\n'
        self._assert_no_violations(RED_LINE_RULES[8], code)

    # ── 规则 10: 禁止静默吞异常 ───────────────────────────────────────────────────

    def test_rule_10_silent_except_violation(self) -> None:
        """检测 except: pass（单行）。"""
        code = "try:\n    risky()\nexcept: pass\n"
        self._assert_violations(RED_LINE_RULES[9], code)

    def test_rule_10_silent_except_compliant(self) -> None:
        """有日志记录的异常处理不误报。"""
        code = "try:\n    risky()\nexcept Exception:\n    logger.error('失败')\n"
        self._assert_no_violations(RED_LINE_RULES[9], code)

    # ── 规则 11: 禁止硬编码密钥 ─────────────────────────────────────────────────

    def test_rule_11_hardcoded_key_violation(self) -> None:
        """检测硬编码 api_key。"""
        code = 'api_key = "sk-xxxxxxxxxxxxxxx"\n'
        self._assert_violations(RED_LINE_RULES[10], code)

    def test_rule_11_hardcoded_key_compliant(self) -> None:
        """通过 config 获取密钥不误报。"""
        code = "from app.config import settings\napi_key = settings.DEEPSEEK_API_KEY\n"
        self._assert_no_violations(RED_LINE_RULES[10], code)

    # ── 规则 12: app 内禁止裸 print ─────────────────────────────────────────────

    def test_rule_12_bare_print_violation(self) -> None:
        """检测函数体内裸 print 调用。"""
        code = """
def debug() -> None:
    print("hello world")
"""
        self._assert_violations(RED_LINE_RULES[11], code)

    def test_rule_12_bare_print_compliant(self) -> None:
        """使用 logger 不误报。"""
        code = """
def debug() -> None:
    logger.debug("hello world")
"""
        self._assert_no_violations(RED_LINE_RULES[11], code)

    # ── 规则 13: 禁止英文注释 ───────────────────────────────────────────────────

    def test_rule_13_english_comment_violation(self) -> None:
        """检测英文注释。"""
        code = """
# This is an English comment
# Get user by ID
def get_user() -> None:
    pass
"""
        self._assert_violations(RED_LINE_RULES[12], code, expected_line_count=2)

    def test_rule_13_english_comment_compliant(self) -> None:
        """中文注释不误报。"""
        code = """
# 这是中文注释
# 根据 ID 查询用户
def get_user() -> None:
    pass
"""
        self._assert_no_violations(RED_LINE_RULES[12], code)


class TestRedLineRuleCoverage:
    """验证全部 13 条红线规则均已定义且各有自测。"""

    def test_all_rules_defined(self) -> None:
        """确保 RED_LINE_RULES 包含全部 13 条规则。"""
        rule_names = [r.name for r in RED_LINE_RULES]
        expected = [
            "禁止 Optional/Union",
            "禁止 TODO 占位",
            "禁止 SELECT 星号",
            "app 内禁止依赖 miniapp service 兼容层",
            "根 API 兼容文件仅作为兼容入口",
            "api 层禁止直接导入 repository",
            "service 层禁止直连 aiosqlite",
            "models 层禁止引用上层模块",
            "禁止 SQL f-string 拼接",
            "禁止静默吞异常",
            "禁止硬编码密钥",
            "app 内禁止裸 print",
            "禁止英文注释",
        ]
        for name in expected:
            assert name in rule_names, f"缺失规则: {name}"
        assert len(RED_LINE_RULES) == 13, (
            f"预期 13 条规则，实际 {len(RED_LINE_RULES)} 条"
        )

    def test_each_rule_has_violation_test(self) -> None:
        """确保每条规则都有对应的违规样本测试。"""
        violation_tests = {
            "禁止 Optional/Union": "test_rule_1_optional_union_violation",
            "禁止 TODO 占位": "test_rule_2_todo_violation",
            "禁止 SELECT 星号": "test_rule_3_select_star_violation",
            "app 内禁止依赖 miniapp service 兼容层": "test_rule_4_import_miniapp_service_violation",
            "根 API 兼容文件仅作为兼容入口": "test_rule_5_root_api_real_router_violation",
            "api 层禁止直接导入 repository": "test_rule_6_api_import_repo_violation",
            "service 层禁止直连 aiosqlite": "test_rule_7_service_aiosqlite_violation",
            "models 层禁止引用上层模块": "test_rule_8_models_upper_violation",
            "禁止 SQL f-string 拼接": "test_rule_9_sql_fstring_violation",
            "禁止静默吞异常": "test_rule_10_silent_except_violation",
            "禁止硬编码密钥": "test_rule_11_hardcoded_key_violation",
            "app 内禁止裸 print": "test_rule_12_bare_print_violation",
            "禁止英文注释": "test_rule_13_english_comment_violation",
        }
        for rule_name, test_name in violation_tests.items():
            assert hasattr(TestRedLineRuleViolations, test_name), (
                f"规则[{rule_name}]缺少违规样本测试: {test_name}"
            )

    def test_each_rule_has_compliance_test(self) -> None:
        """确保每条规则都有对应的合规样本测试（防止误报）。"""
        compliance_tests = {
            "禁止 Optional/Union": "test_rule_1_optional_union_compliant",
            "禁止 TODO 占位": "test_rule_2_todo_compliant",
            "禁止 SELECT 星号": "test_rule_3_select_star_compliant",
            "app 内禁止依赖 miniapp service 兼容层": "test_rule_4_import_miniapp_service_compliant",
            "根 API 兼容文件仅作为兼容入口": "test_rule_5_root_api_wrapper_compliant",
            "api 层禁止直接导入 repository": "test_rule_6_api_import_repo_compliant",
            "service 层禁止直连 aiosqlite": "test_rule_7_service_aiosqlite_compliant",
            "models 层禁止引用上层模块": "test_rule_8_models_upper_compliant",
            "禁止 SQL f-string 拼接": "test_rule_9_sql_fstring_compliant",
            "禁止静默吞异常": "test_rule_10_silent_except_compliant",
            "禁止硬编码密钥": "test_rule_11_hardcoded_key_compliant",
            "app 内禁止裸 print": "test_rule_12_bare_print_compliant",
            "禁止英文注释": "test_rule_13_english_comment_compliant",
        }
        for rule_name, test_name in compliance_tests.items():
            assert hasattr(TestRedLineRuleViolations, test_name), (
                f"规则[{rule_name}]缺少合规样本测试: {test_name}"
            )
