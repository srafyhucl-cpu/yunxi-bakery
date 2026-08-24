import subprocess
import sys

from scripts import check_project


def test_business_contract_checks_are_registered() -> None:
    commands = [" ".join(command) for command in check_project.CONTRACT_COMMANDS]

    assert any(
        "check_employee_agent_capability_contracts.py" in command
        for command in commands
    )
    assert any("check_customer_rag_golden_cases.py" in command for command in commands)
    assert any("check_knowledge_governance_plan.py" in command for command in commands)
    assert any(
        "check_customer_memory_governance_plan.py" in command for command in commands
    )
    assert any(
        "check_customer_observability_contract.py" in command for command in commands
    )
    assert any("check_miniapp_page_api_contract.py" in command for command in commands)
    assert any(
        "check_github_reference_implementation_plan.py" in command
        for command in commands
    )


def test_project_contract_checks_pass() -> None:
    results = check_project.run_contract_checks()

    assert results
    assert all(result.passed for result in results)


def test_run_command_sets_fake_embedding_for_quality_commands(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_run(*args, **kwargs):
        captured.update(kwargs["env"])
        return subprocess.CompletedProcess(args[0], 0, stdout="ok", stderr="")

    monkeypatch.setattr(check_project.subprocess, "run", fake_run)

    result = check_project.run_command(
        (sys.executable, "scripts/report_rag_shadow_observability.py", "--summary")
    )

    assert result.passed is True
    assert captured["PYTHONUTF8"] == "1"
    assert captured["YUNXI_USE_FAKE_EMBEDDING"] == "1"


def test_contract_checks_cache_read_only_results(monkeypatch) -> None:
    calls = 0

    def fake_run_command(_command):
        nonlocal calls
        calls += 1
        return check_project.CheckResult("contract", True, [])

    monkeypatch.setattr(check_project, "run_command", fake_run_command)
    check_project.run_contract_checks.cache_clear()

    first = check_project.run_contract_checks()
    second = check_project.run_contract_checks()

    assert first == second
    assert calls == len(check_project.CONTRACT_COMMANDS)
    check_project.run_contract_checks.cache_clear()


def test_doc_guard_flags_stale_causal_ordering(tmp_path) -> None:
    doc = tmp_path / "spec.md"
    doc.write_text(
        "# 测试\n\n新模型按 `(occurred_at, id)` 单调排序。\n", encoding="utf-8"
    )
    result = check_project.check_contract_doc_legacy_terms((tmp_path,))
    assert not result.passed
    assert "旧因果排序口径" in result.details[0]


def test_doc_guard_allows_prohibition_statements(tmp_path) -> None:
    doc = tmp_path / "spec.md"
    doc.write_text(
        "# 测试\n\n禁止以 `(occurred_at, id)` 承担因果语义。\n", encoding="utf-8"
    )
    result = check_project.check_contract_doc_legacy_terms((tmp_path,))
    assert result.passed


def test_doc_guard_flags_stale_terms(tmp_path) -> None:
    doc = tmp_path / "spec.md"
    doc.write_text(
        "# 测试\n\n收回不足为 manual_review + 冻结额度。\n"
        "币种 fee_type=CNY。\n"
        "| 其他绕过统一入口的写路径 | — |\n",
        encoding="utf-8",
    )
    result = check_project.check_contract_doc_legacy_terms((tmp_path,))
    assert not result.passed
    assert len(result.details) == 3


def test_doc_guard_passes_on_active_contract_docs() -> None:
    result = check_project.check_contract_doc_legacy_terms()
    assert result.passed, result.details


def test_migration_guard_flags_unlisted_direct_writer(tmp_path) -> None:
    """D1-0 迁移守卫：矩阵外模块直接写支付状态即失败（B3.4，评审问题 4）。"""
    module = tmp_path / "rogue_writer.py"
    module.write_text(
        "# 未列入迁移矩阵的直写模块\n"
        "await order_repo.update_payment(order_id, payment, now)\n"
        "INSERT INTO member_balance (mobile, points) VALUES ('1', 0)\n",
        encoding="utf-8",
    )
    result = check_project.check_d1_migration_guard((tmp_path,))
    assert not result.passed
    assert any("绕过统一支付应用服务直接写状态" in detail for detail in result.details)


def test_migration_guard_flags_direct_sql_write(tmp_path) -> None:
    """D1-0 迁移守卫：矩阵外模块直接 SQL 写券状态即失败。"""
    module = tmp_path / "rogue_coupon.py"
    module.write_text(
        "# 未列入迁移矩阵的直写模块\n"
        "UPDATE coupon_inventory SET status = 'CONSUME' WHERE id = ?\n",
        encoding="utf-8",
    )
    result = check_project.check_d1_migration_guard((tmp_path,))
    assert not result.passed


def test_migration_guard_passes_clean_module(tmp_path) -> None:
    """D1-0 迁移守卫：只读模块不误报。"""
    module = tmp_path / "clean_reader.py"
    module.write_text(
        "# 只读模块\n"
        "payment = loads_payment(order.payment)\n"
        "balance = await balance_repo.get_points(mobile)\n",
        encoding="utf-8",
    )
    result = check_project.check_d1_migration_guard((tmp_path,))
    assert result.passed


def test_migration_guard_passes_real_repo() -> None:
    """D1-0 迁移守卫：当前仓库全部直接写路径均在矩阵白名单内。"""
    result = check_project.check_d1_migration_guard()
    assert result.passed, result.details


def test_migration_guard_flags_bare_repo_consume_refund(tmp_path) -> None:
    """D1-0 迁移守卫（B3.5，评审问题 10）：`_repo.consume / _repo.refund` 不再漏检。

    正则时代 REPO_WRITE_CALL_RE 缺 consume / refund 属性，白名单外模块
    `self._repo.consume(...)` 直写券状态可绕过守卫；AST 方法级守卫必须拦截。
    """
    module = tmp_path / "rogue_coupon_consume.py"
    module.write_text(
        "# 未列入迁移矩阵的直写模块\n"
        "async def rogue() -> None:\n"
        "    await self._repo.consume('c1', '13900000000', order_no='o1')\n"
        "    await self._repo.refund('c1', '13900000000', order_no='o1')\n",
        encoding="utf-8",
    )
    result = check_project.check_d1_migration_guard((tmp_path,))
    assert not result.passed
    assert any("绕过统一支付应用服务直接写状态" in detail for detail in result.details)


def test_migration_guard_is_method_level_allowlist(tmp_path, monkeypatch) -> None:
    """D1-0 迁移守卫（B3.5，评审问题 10）：白名单模块内仅 allowlist 函数可直写。

    白名单模块不再是整文件放行——非 allowlist 函数新增直写即失败。
    """
    module = tmp_path / "matrix_writer.py"
    module.write_text(
        "# 模拟矩阵白名单模块\n"
        "async def allowed_fn() -> None:\n"
        "    await self._inventory_repo.insert(coupon)\n"
        "async def rogue_fn() -> None:\n"
        "    await self._inventory_repo.insert(coupon)\n",
        encoding="utf-8",
    )
    rel = str(check_project._rel_doc_path(module)).replace("\\", "/")
    monkeypatch.setattr(check_project, "D1_MATRIX_LEGACY_WRITE_MODULES", (rel,))
    monkeypatch.setattr(
        check_project,
        "D1_MATRIX_ALLOWED_WRITE_FUNCTIONS",
        {rel: frozenset({"allowed_fn"})},
    )
    result = check_project.check_d1_migration_guard((tmp_path,))
    assert not result.passed
    assert any("rogue_fn" in detail for detail in result.details)
    assert not any("allowed_fn" in detail for detail in result.details)


def test_payment_notify_migration_chain_present() -> None:
    """D1-0 迁移表支付通知行按真实调用链命名（B3.4，评审问题 4）。"""
    import app.api.channels.storefront.payments as api_mod
    import app.service.order.application as app_mod
    import app.service.order.payment_notification as notif_mod
    import app.service.order.payment_runtime as runtime_mod

    assert hasattr(api_mod, "create_storefront_payments_router")
    assert hasattr(app_mod.OrderApplicationService, "handle_wechat_payment_notify")
    assert hasattr(
        runtime_mod.OrderPaymentRuntimeService, "handle_wechat_payment_notify"
    )
    assert hasattr(notif_mod.WechatPaymentNotificationService, "mark_paid")
