"""项目质量门禁统一入口。"""

import argparse
import ast
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
APP_DIR = ROOT_DIR / "app"
PYTHON_EXT = ".py"
TEXT_ENCODING = "utf-8"

ROOT_API_COMPAT_FILES: tuple[Path, ...] = (
    APP_DIR / "api" / "admin_addresses.py",
    APP_DIR / "api" / "admin_assets.py",
    APP_DIR / "api" / "admin_config.py",
    APP_DIR / "api" / "admin_dialog.py",
    APP_DIR / "api" / "admin_frontend.py",
    APP_DIR / "api" / "admin_knowledge.py",
    APP_DIR / "api" / "admin_observability.py",
    APP_DIR / "api" / "admin_orders.py",
    APP_DIR / "api" / "admin_products.py",
    APP_DIR / "api" / "admin_shop_pages.py",
    APP_DIR / "api" / "admin_transfer.py",
    APP_DIR / "api" / "channel_router.py",
    APP_DIR / "api" / "miniapp_auth.py",
    APP_DIR / "api" / "miniapp_addresses.py",
    APP_DIR / "api" / "miniapp_catalog.py",
    APP_DIR / "api" / "miniapp_chat.py",
    APP_DIR / "api" / "miniapp_orders.py",
    APP_DIR / "api" / "miniapp_payments.py",
    APP_DIR / "api" / "webhook.py",
    APP_DIR / "api" / "webhook_helpers.py",
    APP_DIR / "api" / "wecom.py",
)


@dataclass(frozen=True)
class ScanRule:
    name: str
    pattern: str
    paths: tuple[Path, ...]
    should_block: bool = True


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    details: list[str]


RED_LINE_RULES: tuple[ScanRule, ...] = (
    ScanRule("禁止 Optional/Union", r"Optional\[|Union\[", (APP_DIR,)),
    ScanRule("禁止 TODO 占位", r"# TODO", (APP_DIR,)),
    ScanRule("禁止 SELECT 星号", r"SELECT\s+\*", (APP_DIR,)),
    ScanRule(
        "app 内禁止依赖 miniapp service 兼容层",
        r"from app\.service\.miniapp_|import app\.service\.miniapp_",
        (APP_DIR,),
    ),
    ScanRule(
        "根 API 兼容文件仅作为兼容入口",
        r"from fastapi import|APIRouter\(|@router\.",
        ROOT_API_COMPAT_FILES,
    ),
    ScanRule(
        "api 层禁止直接导入 repository", r"from app\.repository", (APP_DIR / "api",)
    ),
    ScanRule(
        "service 层禁止直连 aiosqlite",
        r"import aiosqlite|aiosqlite\.",
        (APP_DIR / "service",),
    ),
    ScanRule(
        "models 层禁止引用上层模块",
        r"from app\.(service|repository|api)",
        (APP_DIR / "models",),
    ),
    ScanRule("禁止 SQL f-string 拼接", r"f\"(SELECT|INSERT|UPDATE|DELETE)", (APP_DIR,)),
    ScanRule("禁止静默吞异常", r"except.*:\s*pass", (APP_DIR,)),
    ScanRule(
        "禁止硬编码密钥", r"api_key\s*=\s*[\"']sk-|secret\s*=\s*[\"']", (APP_DIR,)
    ),
    ScanRule("app 内禁止裸 print", r"^\s+print\(", (APP_DIR,)),
    ScanRule("禁止英文注释", r"^\s*#\s+(?!.*[\u4e00-\u9fff])[A-Za-z]", (APP_DIR,)),
)

TEST_COMMANDS: tuple[tuple[str, ...], ...] = (
    (sys.executable, "-m", "pytest", "-q", "--tb=short"),
)

CONTRACT_COMMANDS: tuple[tuple[str, ...], ...] = (
    (sys.executable, "scripts/check_admin_auth_surface.py", "--summary"),
    (sys.executable, "scripts/check_reverse_proxy_contract.py", "--summary"),
    (
        sys.executable,
        "scripts/check_order_repository_transactions.py",
        "--summary",
    ),
    (
        sys.executable,
        "scripts/check_customer_order_access_contract.py",
        "--summary",
    ),
    (
        sys.executable,
        "scripts/check_product_vector_sync_contract.py",
        "--summary",
    ),
    (
        sys.executable,
        "scripts/check_employee_agent_capability_contracts.py",
        "--summary",
    ),
    (sys.executable, "scripts/check_customer_rag_golden_cases.py", "--summary"),
    (sys.executable, "scripts/check_knowledge_governance_plan.py", "--summary"),
    (
        sys.executable,
        "scripts/check_customer_memory_governance_plan.py",
        "--summary",
    ),
    (
        sys.executable,
        "scripts/check_customer_observability_contract.py",
        "--summary",
    ),
    (
        sys.executable,
        "scripts/check_miniapp_page_api_contract.py",
        "--summary",
    ),
    (
        sys.executable,
        "scripts/check_github_reference_implementation_plan.py",
        "--summary",
    ),
    (
        sys.executable,
        "scripts/check_langchain_ai_layer_production_plan.py",
        "--summary",
    ),
    (
        sys.executable,
        "scripts/check_real_conversation_replay_pool.py",
        "--summary",
    ),
    (
        sys.executable,
        "scripts/check_real_conversation_replay_intake_readiness.py",
        "--summary",
    ),
    (
        sys.executable,
        "scripts/build_real_conversation_replay_intake_packet.py",
        "--summary",
    ),
    (
        sys.executable,
        "scripts/audit_real_conversation_replay_candidate.py",
        "--summary",
    ),
    (
        sys.executable,
        "scripts/check_langsmith_runtime_config.py",
        "--summary",
    ),
    (
        sys.executable,
        "scripts/check_privacy_outbound_contract.py",
        "--summary",
    ),
    (
        sys.executable,
        "scripts/check_security_outbound_contract.py",
        "--summary",
    ),
    (
        sys.executable,
        "scripts/check_langsmith_production_rollout.py",
        "--summary",
    ),
    (
        sys.executable,
        "scripts/build_langsmith_production_enablement_packet.py",
        "--summary",
    ),
    (
        sys.executable,
        "scripts/check_langchain_ai_layer_capacity.py",
        "--summary",
    ),
    (
        sys.executable,
        "scripts/report_rag_shadow_observability.py",
        "--summary",
    ),
    (
        sys.executable,
        "scripts/report_rag_shadow_log_observability.py",
        "--summary",
    ),
    (
        sys.executable,
        "scripts/build_rag_shadow_log_intake_packet.py",
        "--summary",
    ),
    (
        sys.executable,
        "scripts/report_langchain_observability_evidence.py",
        "--summary",
    ),
    (
        sys.executable,
        "scripts/build_langchain_release_evidence_packet.py",
        "--summary",
    ),
    (
        sys.executable,
        "scripts/build_langchain_portfolio_evidence_packet.py",
        "--summary",
    ),
)

# ── 洁净代码检查常量 ────────────────────────────────────────────────────────
# 函数体行数上限（超出此值记录警告，暂不阻断；待存量修复后升级为 BLOCK）
FUNC_MAX_LINES = 50

# 禁止在函数体内直接硬编码的平台域名（必须通过模块级常量引用）
HARDCODED_DOMAINS: tuple[str, ...] = (
    "h5.youzan.com",
    "qyapi.weixin.qq.com",
    "open.youzanyun.com",
)

# 必须命名为常量的已知业务魔法整数
KNOWN_MAGIC_INTEGERS: frozenset[int] = frozenset(
    {
        172800,
        86400,
        43200,
        604800,  # 秒级时间常量
    }
)

# ── 合同文档守卫常量（B3.3）───────────────────────────────────────────────
# 活动合同文档目录（M4 归档资料位于 docs/superpowers/specs，不在扫描范围）
CONTRACT_DOC_DIRS: tuple[Path, ...] = (
    ROOT_DIR / "docs" / "specs",
    ROOT_DIR / "docs" / "harness-engineering" / "adr",
)

# 已被 ADR 0008 定稿废弃的旧因果排序表述（禁止性语句不判违规）
CAUSAL_ORDERING_PATTERNS: tuple[str, ...] = (
    r"`?\(occurred_at,\s*id\)`?\s*(单调)?排序",
    r"`?\(occurred_at,\s*id\)`?\s*承担因果",
)

# 已被 ADR 0008 定稿废弃的旧口径术语（出现即判违规，不允许任何残留）
LEGACY_TERM_PATTERNS: tuple[tuple[str, str], ...] = (
    ("旧退款短缺口径", r"冻结额度"),
    ("旧币种字段口径", r"fee_type"),
    ("D1-0 迁移兜底行", r"其他绕过统一入口的写路径"),
)


def _parse_ast(file_path: Path) -> ast.Module | None:
    """安全解析 Python 文件为 AST，语法错误时返回 None。"""
    try:
        return ast.parse(
            file_path.read_text(encoding=TEXT_ENCODING), filename=str(file_path)
        )
    except SyntaxError:
        return None


def check_hardcoded_urls_in_functions(app_dir: Path) -> CheckResult:
    """检查函数体内是否存在硬编码平台域名 URL（应通过模块级常量引用）。"""
    violations: list[str] = []
    for file_path in iter_python_files((app_dir,)):
        tree = _parse_ast(file_path)
        if tree is None:
            continue
        for func_node in ast.walk(tree):
            if not isinstance(func_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for child in ast.walk(func_node):
                if child is func_node:
                    continue
                if not (
                    isinstance(child, ast.Constant) and isinstance(child.value, str)
                ):
                    continue
                if any(domain in child.value for domain in HARDCODED_DOMAINS):
                    rel = file_path.relative_to(ROOT_DIR)
                    violations.append(f"{rel}:{child.lineno}: {child.value[:80]!r}")
    return CheckResult("函数体内禁止硬编码平台 URL", not violations, violations)


def check_known_magic_integers(app_dir: Path) -> CheckResult:
    """检查函数体内是否存在已知业务魔法整数（应提取为命名常量）。"""
    violations: list[str] = []
    for file_path in iter_python_files((app_dir,)):
        tree = _parse_ast(file_path)
        if tree is None:
            continue
        for func_node in ast.walk(tree):
            if not isinstance(func_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for child in ast.walk(func_node):
                if child is func_node:
                    continue
                if (
                    isinstance(child, ast.Constant)
                    and child.value in KNOWN_MAGIC_INTEGERS
                ):
                    rel = file_path.relative_to(ROOT_DIR)
                    violations.append(
                        f"{rel}:{child.lineno}: 魔法整数 {child.value!r}（请提取为命名常量）"
                    )
    return CheckResult("函数体内禁止已知业务魔法整数", not violations, violations)


def check_function_lengths(app_dir: Path) -> list[str]:
    """扫描超过职责评审线的函数，返回非阻断信号。"""
    warnings: list[str] = []
    for file_path in iter_python_files((app_dir,)):
        tree = _parse_ast(file_path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not (hasattr(node, "end_lineno") and node.end_lineno):
                continue
            func_lines = node.end_lineno - node.lineno
            if func_lines > FUNC_MAX_LINES:
                rel = file_path.relative_to(ROOT_DIR)
                warnings.append(
                    f"{rel}:{node.lineno}: `{node.name}()` {func_lines} 行"
                    f"（职责评审线 {FUNC_MAX_LINES}）"
                )
    return warnings


def iter_python_files(paths: tuple[Path, ...]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix == PYTHON_EXT:
            files.append(path)
            continue
        if path.exists():
            files.extend(sorted(path.rglob(f"*{PYTHON_EXT}")))
    return files


def iter_markdown_files(paths: tuple[Path, ...]) -> list[Path]:
    """按目录收集 Markdown 文件（单文件路径直接返回）。"""
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix == ".md":
            files.append(path)
            continue
        if path.exists():
            files.extend(sorted(path.rglob("*.md")))
    return files


def check_contract_doc_legacy_terms(
    dirs: tuple[Path, ...] | None = None,
) -> CheckResult:
    """合同文档守卫：拦截已被 ADR 0008 废弃的旧口径表述（B3.3）。

    扫描 docs/specs 与 docs/harness-engineering/adr 下的活动合同文档：
    - 旧因果排序（按 `(occurred_at, id)` 单调排序 / 承担因果）——禁止性语句不判违规；
    - 旧退款短缺口径（冻结额度）、旧币种字段口径（fee_type）、
      D1-0 迁移兜底行（其他绕过统一入口的写路径）——出现即失败。
    M4 归档资料（docs/superpowers/specs）不在扫描范围。
    """
    targets = dirs or CONTRACT_DOC_DIRS
    violations: list[str] = []
    for file_path in iter_markdown_files(targets):
        try:
            text = file_path.read_text(encoding=TEXT_ENCODING)
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if "禁止" not in line:
                for pattern in CAUSAL_ORDERING_PATTERNS:
                    if re.search(pattern, line):
                        violations.append(
                            f"{_rel_doc_path(file_path)}:{line_no}: "
                            f"旧因果排序口径: {line.strip()}"
                        )
            for name, pattern in LEGACY_TERM_PATTERNS:
                if re.search(pattern, line):
                    violations.append(
                        f"{_rel_doc_path(file_path)}:{line_no}: {name}: {line.strip()}"
                    )
    return CheckResult("合同文档旧口径守卫", not violations, violations)


def _rel_doc_path(file_path: Path) -> Path:
    """返回相对项目根的路径；越界（如测试临时目录）时回退为绝对路径。"""
    try:
        return file_path.relative_to(ROOT_DIR)
    except ValueError:
        return Path(str(file_path))


# ── D1-0 直接写状态守卫（B3.4 落地 + B3.5 升级为 AST 方法级，评审问题 4/10）────
# 与 ADR 0008 D1-0 迁移矩阵逐行封闭对应：仅矩阵列明的旧写路径模块允许
# 直接写账务状态（写 order.payment / 余额 / 积分 / 券等），且 B3.5 起按
# **方法级 allowlist** 收口——白名单模块内只有矩阵逐行对应的函数允许直写，
# 其他函数（含白名单模块新增写路径）一律检查失败；矩阵外模块任何函数
# 直写即失败。矩阵新增写路径必须同步本白名单与方法级 allowlist（封闭核对）。
D1_MATRIX_LEGACY_WRITE_MODULES: tuple[str, ...] = (
    "app/api/channels/storefront/payments.py",
    "app/api/channels/storefront/recharges.py",
    "app/service/coupon/admin.py",
    "app/service/coupon/inventory.py",
    "app/service/coupon/payment.py",
    "app/service/member_loyalty.py",
    "app/service/order/application.py",
    "app/service/order/cancellation.py",
    "app/service/order/expiration.py",
    "app/service/order/payment_notification.py",
    "app/service/order/payment_runtime.py",
    "app/service/order/status_flow.py",
    "app/service/points/ledger.py",
    "app/service/points/payment.py",
    "app/service/stored_value/member.py",
    "app/service/stored_value/payment.py",
    "app/service/stored_value/recharge.py",
    "app/service/youzan/event_member.py",
)

# B3.5（评审问题 10）：方法级 allowlist——各白名单模块内允许直写账务状态的
# 函数名（与 ADR 0008 D1-0 迁移矩阵逐行封闭对应；从真实写点枚举校准，
# 含 _repo.consume / _repo.refund 等正则时代漏检的仓储写方法）。
D1_MATRIX_ALLOWED_WRITE_FUNCTIONS: dict[str, frozenset[str]] = {
    "app/service/coupon/admin.py": frozenset({"grant_coupon"}),
    "app/service/coupon/inventory.py": frozenset({"consume_once", "refund_once"}),
    "app/service/coupon/payment.py": frozenset(
        {"apply_coupon_snapshot", "clear_coupon_snapshot", "consume_on_payment"}
    ),
    "app/service/member_loyalty.py": frozenset({"_upsert_coupon", "import_one"}),
    "app/service/order/cancellation.py": frozenset({"_cancel_order"}),
    "app/service/order/expiration.py": frozenset({"_close_unpaid_order"}),
    "app/service/order/payment_notification.py": frozenset(
        {"_claim_transaction", "mark_paid"}
    ),
    "app/service/order/payment_runtime.py": frozenset(
        {"_mark_wechat_payment_paid", "confirm_mock_payment"}
    ),
    "app/service/order/status_flow.py": frozenset({"_cancel_order"}),
    "app/service/points/ledger.py": frozenset({"credit", "deduct"}),
    "app/service/points/payment.py": frozenset(
        {
            "apply_points_snapshot",
            "refund_settled_points",
            "_record_awarded",
            "_clear_awarded",
            "award_on_payment",
        }
    ),
    "app/service/stored_value/member.py": frozenset({"credit", "deduct"}),
    "app/service/stored_value/payment.py": frozenset(
        {"pay_order_with_balance", "prepare_combined_payment"}
    ),
    "app/service/stored_value/recharge.py": frozenset(
        {
            "cancel_unpaid_recharge",
            "create_recharge",
            "confirm_mock_recharge_payment",
        }
    ),
    "app/service/youzan/event_member.py": frozenset(
        {
            "_handle_points_event",
            "_handle_coupon_event",
            "_handle_customer_event",
            "_handle_card_event",
        }
    ),
}

DIRECT_WRITE_SQL_RE = re.compile(
    r"(INSERT INTO|UPDATE|DELETE FROM)\s+"
    r"(orders|member_balance|points_ledger|coupon_inventory|coupon_events|"
    r"coupon_observation|coupon_current_state|stored_value|recharges|"
    r"payment_attempt|account_hold|ledger_operation|accounting_outbox|"
    r"payment_provider_event|refund_aggregate|coupon_reconcile_case|"
    r"points_refund_reconcile)\b",
    re.IGNORECASE,
)

# 仓储接收者形态：模块级属性 / 局部变量名形如 *_repo / *_service / db / handle
_D1_RECEIVER_RE = re.compile(
    r"(?:[a-z_]*repo|_db|db|handle|_service|_inventory_service|"
    r"_notification_service|_member_service)\Z"
)

# 账务仓储提示词：接收者名含以下任一提示时才把「通用写方法名」视为账务写
_D1_ACCOUNTING_HINT_RE = re.compile(
    r"(ledger|balance|points|coupon|recharge|refund|inventory|grant|hold|"
    r"quota|outbox|reconcile|shortfall|payment_attempt|account|dedup)"
)

# 显式账务写方法：任何 *_repo / *_service 接收者调用即视为直写（B3.5 补入
# consume / refund——正则时代漏检 _repo.consume / _repo.refund，评审问题 10）
_D1_EXPLICIT_WRITE_ATTRS: frozenset[str] = frozenset(
    {
        "update_payment",
        "update_payment_if_unpaid_active",
        "update_payment_to_partial_if_unpaid_active",
        "update_payment_to_partial_if_unpaid_or_partial_active",
        "update_payment_to_paid_if_unpaid_or_partial_active",
        "close_unpaid_order",
        "cancel_unpaid_order",
        "claim_payment_transaction",
        "upsert_identity",
        "credit_points",
        "deduct_points_if_sufficient",
        "credit_stored_value",
        "deduct_stored_value_if_sufficient",
        "mark_paid",
        "consume_once",
        "back_once",
        "consume",
        "refund",
        "mark_paid_if_unpaid",
        "cancel_if_unpaid",
        "expire_if_unpaid",
        "close_open",
        "open_case",
    }
)

# 通用写方法名：仅当接收者名含账务提示词时视为直写（避免误伤 session / config
# / transfer 等非账务仓储的 insert / create / append / set 调用）
_D1_GENERIC_WRITE_ATTRS: frozenset[str] = frozenset(
    {
        "insert",
        "create",
        "append",
        "grant",
        "revoke",
        "deduct",
        "credit",
        "add_points",
        "award_points",
        "refund_coupon",
        "clear_coupon_snapshot",
        "consume_coupon",
    }
)


def _d1_receiver_is_repo(node: ast.expr) -> bool:
    """接收者是否为仓储 / 服务实例形态（Name 或 Attribute 末段匹配）。"""
    if isinstance(node, ast.Name):
        return bool(_D1_RECEIVER_RE.match(node.id))
    if isinstance(node, ast.Attribute):
        return bool(_D1_RECEIVER_RE.match(node.attr))
    return False


def _d1_receiver_hint(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _d1_write_sites(tree: ast.Module) -> list[tuple[str, int]]:
    """收集模块内全部账务直写点（AST）：直接 SQL 常量 / execute(SQL) / 仓储写方法。

    B3.5（评审问题 10）：方法级归因——每个写点随后归属到最内层函数，
    守卫按「白名单模块 × 方法级 allowlist」裁决，不再整文件跳过白名单模块。
    """
    sites: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if DIRECT_WRITE_SQL_RE.search(node.value):
                sites.append(("SQL", getattr(node, "lineno", 0)))
            continue
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or not _d1_receiver_is_repo(func.value):
            continue
        attr = func.attr
        line = getattr(node, "lineno", 0)
        recv = _d1_receiver_hint(func.value)
        if attr in ("execute", "execute_fetchall", "executemany"):
            sql_args = list(node.args) + [
                kw.value for kw in node.keywords if kw.arg in ("sql", "query")
            ]
            for arg in sql_args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if DIRECT_WRITE_SQL_RE.search(arg.value):
                        sites.append((f"{attr}(SQL)", line))
        elif attr in _D1_EXPLICIT_WRITE_ATTRS:
            sites.append((attr, line))
        elif attr in _D1_GENERIC_WRITE_ATTRS and _D1_ACCOUNTING_HINT_RE.search(recv):
            sites.append((attr, line))
    return sites


def _d1_line_to_func(tree: ast.Module) -> dict[int, str]:
    """行号 → 最外层函数名（嵌套函数归到其所在方法，写点以方法为裁决单位）。"""
    result: dict[int, str] = {}

    def visit(node: ast.AST, stack: tuple[str, ...]) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            stack = stack + (node.name,)
        for child in ast.iter_child_nodes(node):
            visit(child, stack)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(ast.Module(body=node.body, type_ignores=[])):
                if hasattr(child, "lineno"):
                    result.setdefault(child.lineno, ".".join(stack))

    visit(tree, ())
    return result


def check_d1_migration_guard(
    scan_dirs: tuple[Path, ...] | None = None,
) -> CheckResult:
    """D1-0 直接写状态守卫（B3.4 + B3.5 升级为 AST 方法级 allowlist，评审问题 4/10）。

    扫描 service / api 层直接写账务状态（直接 SQL 写或仓储写方法调用：
    order.payment、member_balance、points_ledger、coupon_inventory、
    stored_value、recharges 及 D1 账务表），凡未在 ADR 0008 D1-0 迁移矩阵
    逐行列明（白名单 D1_MATRIX_LEGACY_WRITE_MODULES + 方法级
    D1_MATRIX_ALLOWED_WRITE_FUNCTIONS）的模块 / 函数一律检查失败；
    仓储层（app/repository）为受权存储层，不在此扫描范围。
    """
    violations: list[str] = []
    targets = scan_dirs or (APP_DIR / "service", APP_DIR / "api")
    for file_path in iter_python_files(targets):
        rel = str(_rel_doc_path(file_path)).replace("\\", "/")
        try:
            tree = ast.parse(
                file_path.read_text(encoding=TEXT_ENCODING), filename=str(file_path)
            )
        except SyntaxError:
            # 语法不完整（如测试夹具中的裸 SQL 行 / 模块级 await）：退回行级扫描
            text = file_path.read_text(encoding=TEXT_ENCODING)
            for line_no, line_text in enumerate(text.splitlines(), start=1):
                if DIRECT_WRITE_SQL_RE.search(line_text):
                    violations.append(
                        f"{rel}:{line_no}: 绕过统一支付应用服务直接写状态"
                        f"（SQL，非 AST 可解析模块）: {line_text.strip()}"
                    )
            continue
        except OSError:
            continue
        sites = _d1_write_sites(tree)
        if not sites:
            continue
        in_matrix = rel in D1_MATRIX_LEGACY_WRITE_MODULES
        allowed = D1_MATRIX_ALLOWED_WRITE_FUNCTIONS.get(rel, frozenset())
        line_to_func = _d1_line_to_func(tree)
        source_lines = file_path.read_text(encoding=TEXT_ENCODING).splitlines()
        for kind, line in sites:
            func_name = ""
            for ln in range(line, 0, -1):
                if ln in line_to_func:
                    func_name = line_to_func[ln]
                    break
            if not in_matrix or func_name not in allowed:
                raw = (
                    source_lines[line - 1].strip() if line <= len(source_lines) else ""
                )
                violations.append(
                    f"{rel}:{line}: 绕过统一支付应用服务直接写状态"
                    f"（{kind}@{func_name or '<模块级>'}）: {raw}"
                )
    return CheckResult("D1-0 直接写状态守卫", not violations, violations)


def scan_rule(rule: ScanRule) -> CheckResult:
    regex = re.compile(rule.pattern)
    matches: list[str] = []
    for file_path in iter_python_files(rule.paths):
        text = file_path.read_text(encoding=TEXT_ENCODING)
        for line_no, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                rel_path = file_path.relative_to(ROOT_DIR)
                detail = f"{rel_path}:{line_no}: {line.strip()}"
                matches.append(detail)
    return CheckResult(rule.name, not matches, matches)


def run_command(command: tuple[str, ...]) -> CheckResult:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    # 质量门禁必须使用轻量编码器，避免本地或 CI 触发真实模型加载。
    env.setdefault("YUNXI_USE_FAKE_EMBEDDING", "1")
    completed = subprocess.run(
        command,
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        env=env,
    )
    command_text = " ".join(command)
    details = []
    if completed.stdout.strip():
        details.append(completed.stdout.strip())
    if completed.stderr.strip():
        details.append(completed.stderr.strip())
    return CheckResult(command_text, completed.returncode == 0, details)


def run_red_line_checks() -> list[CheckResult]:
    return [scan_rule(rule) for rule in RED_LINE_RULES]


def run_clean_code_checks() -> list[CheckResult]:
    """运行洁净代码阻断检查（硬编码 URL、魔法整数）。"""
    return [
        check_hardcoded_urls_in_functions(APP_DIR),
        check_known_magic_integers(APP_DIR),
    ]


def run_doc_guard_checks() -> list[CheckResult]:
    """运行合同文档旧口径守卫（B3.3）。"""
    return [check_contract_doc_legacy_terms()]


def run_migration_guard_checks() -> list[CheckResult]:
    """运行 D1-0 直接写状态守卫（B3.4，评审问题 4）。"""
    return [check_d1_migration_guard()]


def run_tests() -> list[CheckResult]:
    return [run_command(command) for command in TEST_COMMANDS]


@lru_cache(maxsize=1)
def run_contract_checks() -> list[CheckResult]:
    """运行业务合约静态检查。"""
    return [run_command(command) for command in CONTRACT_COMMANDS]


def print_results(title: str, results: list[CheckResult]) -> None:
    print(f"\n[{title}]")
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"{status} {result.name}")
        for detail in result.details:
            print(detail)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="项目质量门禁统一入口")
    parser.add_argument("--skip-tests", action="store_true", help="跳过测试脚本")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    red_line_results = run_red_line_checks()
    print_results("红线检查", red_line_results)

    clean_code_results = run_clean_code_checks()
    print_results("洁净代码检查", clean_code_results)

    doc_guard_results = run_doc_guard_checks()
    print_results("合同文档守卫", doc_guard_results)

    migration_guard_results = run_migration_guard_checks()
    print_results("D1-0 迁移守卫", migration_guard_results)

    contract_results = run_contract_checks()
    print_results("业务合约检查", contract_results)

    func_length_warnings = check_function_lengths(APP_DIR)
    if func_length_warnings:
        print(
            f"\n[函数职责评审信号（{len(func_length_warnings)} 处，"
            "不因行数自动要求拆分）]"
        )
        for warning in func_length_warnings:
            print(f"WARN {warning}")

    test_results: list[CheckResult] = []
    if not args.skip_tests:
        test_results = run_tests()
        print_results("测试验证", test_results)

    all_results = (
        red_line_results
        + clean_code_results
        + doc_guard_results
        + migration_guard_results
        + contract_results
        + test_results
    )
    failed_results = [result for result in all_results if not result.passed]
    if failed_results:
        print(f"\n质量门禁失败: {len(failed_results)} 项")
        return 1
    print("\n质量门禁通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
