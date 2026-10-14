"""LangChain AI 应用层发布门禁测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from scripts import check_langchain_ai_layer_release_gate as release_gate


def test_build_gate_steps_keeps_rag_matrix_optional() -> None:
    steps = release_gate.build_gate_steps(include_rag_matrix=False)

    assert [step.name for step in steps] == [
        "agent_eval_default",
        "customer_reply_replay_probe",
        "agent_eval_with_reply_replay",
    ]


def test_build_gate_steps_can_include_rag_matrix() -> None:
    steps = release_gate.build_gate_steps(include_rag_matrix=True)

    assert steps[-1].name == "rag_eval_matrix"
    assert "scripts/report_retrieval_eval_matrix.py" in steps[-1].command


def test_build_gate_steps_keeps_real_replay_optional() -> None:
    steps = release_gate.build_gate_steps(include_real_replay=False)

    assert "real_conversation_replay" not in [step.name for step in steps]
    assert "agent_eval_with_real_replay" not in [step.name for step in steps]


def test_build_gate_steps_can_include_real_replay(tmp_path: Path) -> None:
    fixture_path = tmp_path / "real-replay.json"
    steps = release_gate.build_gate_steps(
        include_real_replay=True,
        real_replay_fixture_path=fixture_path,
    )
    step_by_name = {step.name: step for step in steps}

    replay_step = step_by_name["real_conversation_replay"]
    agent_eval_step = step_by_name["agent_eval_with_real_replay"]

    assert "scripts/check_real_conversation_replay.py" in replay_step.command
    assert "--replies-json-out" in replay_step.command
    assert str(fixture_path) in replay_step.command
    assert "scripts/report_agent_eval.py" in agent_eval_step.command
    assert "--include-real-replay" in agent_eval_step.command
    assert str(fixture_path) in agent_eval_step.command


def test_build_gate_steps_can_include_real_replay_coverage(tmp_path: Path) -> None:
    fixture_path = tmp_path / "real-replay.json"
    steps = release_gate.build_gate_steps(
        include_real_replay=True,
        include_real_replay_coverage=True,
        real_replay_fixture_path=fixture_path,
        real_replay_min_per_scenario=5,
    )
    coverage_step = [
        step for step in steps if step.name == "real_conversation_replay_coverage"
    ][0]

    assert "scripts/check_real_conversation_replay_coverage.py" in coverage_step.command
    assert "--min-per-scenario" in coverage_step.command
    assert "5" in coverage_step.command
    assert str(fixture_path) in coverage_step.command


def test_build_gate_steps_can_include_real_replay_pool(tmp_path: Path) -> None:
    manifest_path = tmp_path / "pool.json"
    steps = release_gate.build_gate_steps(
        include_real_replay_pool=True,
        require_real_replay_pool=True,
        real_pool_manifest_path=manifest_path,
    )
    pool_step = [
        step for step in steps if step.name == "real_conversation_replay_pool"
    ][0]

    assert "scripts/check_real_conversation_replay_pool.py" in pool_step.command
    assert "--manifest" in pool_step.command
    assert str(manifest_path) in pool_step.command
    assert "--require-real" in pool_step.command


def test_build_gate_steps_can_include_real_replay_intake_readiness(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "pool.json"
    output_path = tmp_path / "intake.json"
    steps = release_gate.build_gate_steps(
        include_real_replay_intake_readiness=True,
        real_pool_manifest_path=manifest_path,
        real_intake_readiness_path=output_path,
    )
    intake_step = [
        step
        for step in steps
        if step.name == "real_conversation_replay_intake_readiness"
    ][0]

    assert (
        "scripts/check_real_conversation_replay_intake_readiness.py"
        in intake_step.command
    )
    assert "--manifest" in intake_step.command
    assert str(manifest_path) in intake_step.command
    assert "--json-out" in intake_step.command
    assert str(output_path) in intake_step.command


def test_build_gate_steps_can_include_observability_evidence(tmp_path: Path) -> None:
    output_path = tmp_path / "observability.json"
    langsmith_path = tmp_path / "langsmith.json"
    steps = release_gate.build_gate_steps(
        include_observability_evidence=True,
        observability_evidence_path=output_path,
        langsmith_runtime_config_path=langsmith_path,
    )
    langsmith_step = [
        step for step in steps if step.name == "langsmith_runtime_config"
    ][0]
    observability_step = [
        step for step in steps if step.name == "langchain_observability_evidence"
    ][0]

    assert "scripts/check_langsmith_runtime_config.py" in langsmith_step.command
    assert "--json-out" in langsmith_step.command
    assert str(langsmith_path) in langsmith_step.command
    assert (
        "scripts/report_langchain_observability_evidence.py"
        in observability_step.command
    )
    assert "--json-out" in observability_step.command
    assert str(output_path) in observability_step.command


def test_build_gate_steps_can_include_production_runtime_capacity(
    tmp_path: Path,
) -> None:
    capacity_path = tmp_path / "capacity.json"
    steps = release_gate.build_gate_steps(
        include_production_runtime_capacity=True,
        capacity_path=capacity_path,
    )
    capacity_step = [
        step for step in steps if step.name == "production_runtime_capacity"
    ][0]

    assert "scripts/check_langchain_ai_layer_capacity.py" in capacity_step.command
    assert "--include-production-runtime" in capacity_step.command
    assert "--json-out" in capacity_step.command
    assert str(capacity_path) in capacity_step.command


def test_build_gate_steps_keeps_production_smoke_optional() -> None:
    steps = release_gate.build_gate_steps(include_production_smoke=False)

    assert "production_smoke" not in [step.name for step in steps]
    assert "production_employee_callback_probe" not in [step.name for step in steps]


def test_build_gate_steps_can_include_production_smoke() -> None:
    steps = release_gate.build_gate_steps(
        include_production_smoke=True,
        production_base_url="https://example.com",
    )

    step_by_name = {step.name: step for step in steps}
    smoke_step = step_by_name["production_smoke"]
    callback_step = step_by_name["production_employee_callback_probe"]

    assert "scripts/smoke_test.py" in smoke_step.command
    assert "scripts/check_wecom_employee_agent_callback.py" in callback_step.command
    assert "https://example.com" in smoke_step.command
    assert "https://example.com" in callback_step.command
    assert "--http-only" in smoke_step.command
    assert "--json" in smoke_step.command
    assert "--output" in callback_step.command


def test_run_gate_steps_stops_on_failure(monkeypatch) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run(command, **_kwargs):
        calls.append(tuple(command))
        return SimpleNamespace(
            returncode=1 if len(calls) == 2 else 0,
            stdout="ok",
            stderr="failed",
        )

    monkeypatch.setattr(release_gate.subprocess, "run", fake_run)

    results = release_gate.run_gate_steps(
        (
            release_gate.GateStep("first", ("python", "first.py")),
            release_gate.GateStep("second", ("python", "second.py")),
            release_gate.GateStep("third", ("python", "third.py")),
        )
    )

    assert [result.name for result in results] == ["first", "second"]
    assert results[-1].passed is False


def test_gate_step_result_tolerates_missing_streams() -> None:
    result = release_gate.GateStepResult(
        name="encoding-noise",
        command=("python", "noisy.py"),
        returncode=0,
        stdout=None,
        stderr=None,
    )

    payload = result.to_dict()

    assert payload["stdout"] == ""
    assert payload["stderr"] == ""


def test_build_release_summary_extracts_default_agent_eval(tmp_path: Path) -> None:
    agent_eval_path = tmp_path / "latest.json"
    reply_eval_path = tmp_path / "latest-with-reply-replay.json"
    agent_eval_path.write_text(
        release_gate.json.dumps(
            {
                "status": "passed",
                "total": 133,
                "failed": 0,
                "pass_rate": 1.0,
                "metadata": {"app_version": "0.90.0"},
                "agent_totals": [{"agent": "customer", "total": 71}],
                "sensitive_scenarios": [{"scenario": "refund", "total": 6}],
            }
        ),
        encoding="utf-8",
    )
    reply_eval_path.write_text(
        release_gate.json.dumps(
            {
                "status": "passed",
                "total": 163,
                "failed": 0,
                "pass_rate": 1.0,
                "metadata": {"app_version": "0.90.0"},
                "agent_totals": [{"agent": "customer_reply_replay", "total": 30}],
            }
        ),
        encoding="utf-8",
    )

    summary = release_gate.build_release_summary(
        include_rag_matrix=False,
        include_real_replay=False,
        include_real_replay_coverage=False,
        include_production_smoke=False,
        agent_eval_path=agent_eval_path,
        reply_eval_path=reply_eval_path,
    )

    assert summary["agent_eval_default"]["total"] == 133
    assert summary["agent_eval_default"]["app_version"] == "0.90.0"
    assert summary["agent_eval_with_reply_replay"]["total"] == 163
    assert summary["real_conversation_replay"] is None
    assert summary["agent_eval_with_real_replay"] is None
    assert summary["real_conversation_replay_coverage"] is None
    assert summary["rag_eval_matrix"] is None
    assert summary["production_smoke"] is None


def test_build_release_summary_extracts_real_replay_reports(
    tmp_path: Path,
) -> None:
    agent_eval_path = tmp_path / "agent.json"
    reply_eval_path = tmp_path / "reply.json"
    real_replay_path = tmp_path / "real-replay.json"
    real_agent_eval_path = tmp_path / "real-agent.json"
    agent_eval_path.write_text("{}", encoding="utf-8")
    reply_eval_path.write_text("{}", encoding="utf-8")
    real_replay_path.write_text(
        release_gate.json.dumps(
            {
                "status": "passed",
                "total": 2,
                "failed": 0,
                "pass_rate": 1.0,
                "metadata": {"app_version": "0.92.0"},
                "agent_totals": [{"agent": "real_conversation_replay", "total": 2}],
            }
        ),
        encoding="utf-8",
    )
    real_agent_eval_path.write_text(
        release_gate.json.dumps(
            {
                "status": "passed",
                "total": 135,
                "failed": 0,
                "pass_rate": 1.0,
                "metadata": {"app_version": "0.92.0"},
                "agent_totals": [
                    {"agent": "customer", "total": 71},
                    {"agent": "real_conversation_replay", "total": 2},
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = release_gate.build_release_summary(
        include_rag_matrix=False,
        include_real_replay=True,
        include_real_replay_coverage=False,
        include_production_smoke=False,
        agent_eval_path=agent_eval_path,
        reply_eval_path=reply_eval_path,
        real_replay_path=real_replay_path,
        real_agent_eval_path=real_agent_eval_path,
    )

    assert summary["real_conversation_replay"]["total"] == 2
    assert summary["agent_eval_with_real_replay"]["total"] == 135
    assert summary["agent_eval_with_real_replay"]["agent_totals"][-1] == {
        "agent": "real_conversation_replay",
        "total": 2,
    }


def test_build_release_summary_extracts_real_replay_coverage(
    tmp_path: Path,
) -> None:
    agent_eval_path = tmp_path / "agent.json"
    reply_eval_path = tmp_path / "reply.json"
    real_replay_path = tmp_path / "real-replay.json"
    real_agent_eval_path = tmp_path / "real-agent.json"
    real_coverage_path = tmp_path / "real-coverage.json"
    agent_eval_path.write_text("{}", encoding="utf-8")
    reply_eval_path.write_text("{}", encoding="utf-8")
    real_replay_path.write_text("{}", encoding="utf-8")
    real_agent_eval_path.write_text("{}", encoding="utf-8")
    real_coverage_path.write_text(
        release_gate.json.dumps(
            {
                "status": "passed",
                "total": 6,
                "failed": 0,
                "min_per_scenario": 5,
                "replay_total": 30,
                "replay_failed": 0,
                "scenario_coverage": [
                    {"scenario": "order", "total": 5, "required": 5, "passed": True}
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = release_gate.build_release_summary(
        include_rag_matrix=False,
        include_real_replay=True,
        include_real_replay_coverage=True,
        include_production_smoke=False,
        agent_eval_path=agent_eval_path,
        reply_eval_path=reply_eval_path,
        real_replay_path=real_replay_path,
        real_agent_eval_path=real_agent_eval_path,
        real_coverage_path=real_coverage_path,
    )

    coverage = summary["real_conversation_replay_coverage"]

    assert coverage["status"] == "passed"
    assert coverage["min_per_scenario"] == 5
    assert coverage["replay_total"] == 30
    assert coverage["scenario_coverage"][0]["scenario"] == "order"


def test_build_release_summary_extracts_real_replay_pool(tmp_path: Path) -> None:
    agent_eval_path = tmp_path / "agent.json"
    reply_eval_path = tmp_path / "reply.json"
    pool_path = tmp_path / "pool-report.json"
    agent_eval_path.write_text("{}", encoding="utf-8")
    reply_eval_path.write_text("{}", encoding="utf-8")
    pool_path.write_text(
        release_gate.json.dumps(
            {
                "status": "passed",
                "total": 1,
                "failed": 0,
                "real_entries": 0,
                "synthetic_entries": 1,
                "real_pool_ready": False,
                "manifest": "tests/fixtures/customer_real_replay_pool_manifest_sample.json",
            }
        ),
        encoding="utf-8",
    )

    summary = release_gate.build_release_summary(
        include_rag_matrix=False,
        include_real_replay=False,
        include_real_replay_coverage=False,
        include_real_replay_pool=True,
        include_production_smoke=False,
        agent_eval_path=agent_eval_path,
        reply_eval_path=reply_eval_path,
        real_pool_report_path=pool_path,
    )

    pool = summary["real_conversation_replay_pool"]

    assert pool["status"] == "passed"
    assert pool["real_entries"] == 0
    assert pool["synthetic_entries"] == 1
    assert pool["real_pool_ready"] is False


def test_build_release_summary_extracts_real_replay_intake_readiness(
    tmp_path: Path,
) -> None:
    agent_eval_path = tmp_path / "agent.json"
    reply_eval_path = tmp_path / "reply.json"
    intake_path = tmp_path / "intake.json"
    agent_eval_path.write_text("{}", encoding="utf-8")
    reply_eval_path.write_text("{}", encoding="utf-8")
    intake_path.write_text(
        release_gate.json.dumps(
            {
                "status": "passed",
                "failed": 0,
                "real_sample_ready": False,
                "missing_actions": ["collect_real_customer_conversations_outside_repo"],
                "pool": {
                    "status": "passed",
                    "real_entries": 0,
                    "synthetic_entries": 1,
                },
            }
        ),
        encoding="utf-8",
    )

    summary = release_gate.build_release_summary(
        include_rag_matrix=False,
        include_real_replay=False,
        include_real_replay_coverage=False,
        include_real_replay_pool=False,
        include_real_replay_intake_readiness=True,
        include_production_smoke=False,
        agent_eval_path=agent_eval_path,
        reply_eval_path=reply_eval_path,
        real_intake_readiness_path=intake_path,
    )

    intake = summary["real_conversation_replay_intake_readiness"]

    assert intake["status"] == "passed"
    assert intake["real_sample_ready"] is False
    assert intake["pool_status"] == "passed"
    assert intake["synthetic_entries"] == 1


def test_build_release_summary_extracts_observability_evidence(
    tmp_path: Path,
) -> None:
    agent_eval_path = tmp_path / "agent.json"
    reply_eval_path = tmp_path / "reply.json"
    langsmith_path = tmp_path / "langsmith.json"
    observability_path = tmp_path / "observability.json"
    agent_eval_path.write_text("{}", encoding="utf-8")
    reply_eval_path.write_text("{}", encoding="utf-8")
    langsmith_path.write_text(
        release_gate.json.dumps(
            {
                "status": "passed",
                "runtime": {
                    "enabled": False,
                    "safe_to_enable": False,
                    "project": "yunxi-bakebot",
                    "api_key_configured": False,
                    "missing": [],
                },
                "metadata_redaction": {"status": "passed"},
            }
        ),
        encoding="utf-8",
    )
    observability_path.write_text(
        release_gate.json.dumps(
            {
                "status": "passed",
                "failed": 0,
                "trace": {"status": "ok", "total_runs": 2},
                "langsmith": {"enabled": False, "project": "yunxi-bakebot"},
                "cold_imports": [{"module": "app.config", "status": "passed"}],
            }
        ),
        encoding="utf-8",
    )

    summary = release_gate.build_release_summary(
        include_rag_matrix=False,
        include_real_replay=False,
        include_real_replay_coverage=False,
        include_real_replay_pool=False,
        include_observability_evidence=True,
        include_production_smoke=False,
        agent_eval_path=agent_eval_path,
        reply_eval_path=reply_eval_path,
        langsmith_runtime_config_path=langsmith_path,
        observability_evidence_path=observability_path,
    )

    langsmith = summary["langsmith_runtime_config"]
    observability = summary["langchain_observability_evidence"]

    assert langsmith["status"] == "passed"
    assert langsmith["project"] == "yunxi-bakebot"
    assert langsmith["metadata_redaction_status"] == "passed"
    assert observability["status"] == "passed"
    assert observability["trace_total_runs"] == 2
    assert observability["langsmith_enabled"] is False
    assert observability["cold_imports"][0]["module"] == "app.config"


def test_build_release_summary_extracts_production_runtime_capacity(
    tmp_path: Path,
) -> None:
    agent_eval_path = tmp_path / "agent.json"
    reply_eval_path = tmp_path / "reply.json"
    capacity_path = tmp_path / "capacity.json"
    agent_eval_path.write_text("{}", encoding="utf-8")
    reply_eval_path.write_text("{}", encoding="utf-8")
    capacity_path.write_text(
        release_gate.json.dumps(
            {
                "status": "passed",
                "failed": 0,
                "trace_probe": {"latency_ms": 2500.0, "payload_bytes": 2227},
                "production_runtime": {
                    "status": "ok",
                    "service_active": True,
                    "version": "0.105.8",
                    "health_version": "0.105.8",
                    "ready_version": "0.105.8",
                    "rss_mb": 80.0,
                    "mem_available_mb": 512.0,
                    "load1": 0.2,
                },
            }
        ),
        encoding="utf-8",
    )

    summary = release_gate.build_release_summary(
        include_rag_matrix=False,
        include_real_replay=False,
        include_real_replay_coverage=False,
        include_production_runtime_capacity=True,
        include_production_smoke=False,
        agent_eval_path=agent_eval_path,
        reply_eval_path=reply_eval_path,
        capacity_path=capacity_path,
    )

    capacity_summary = summary["langchain_ai_layer_capacity"]

    assert capacity_summary["status"] == "passed"
    assert capacity_summary["production_runtime_status"] == "ok"
    assert capacity_summary["version"] == "0.105.8"
    assert capacity_summary["rss_mb"] == 80.0


def test_build_release_summary_extracts_rag_and_production_reports(
    tmp_path: Path,
) -> None:
    agent_eval_path = tmp_path / "agent.json"
    reply_eval_path = tmp_path / "reply.json"
    rag_path = tmp_path / "rag.json"
    smoke_path = tmp_path / "smoke.json"
    callback_path = tmp_path / "callback.json"
    agent_eval_path.write_text("{}", encoding="utf-8")
    reply_eval_path.write_text("{}", encoding="utf-8")
    rag_path.write_text(
        release_gate.json.dumps(
            {
                "metadata": {"corpus_size": 400, "total_cases": 70, "k": 5},
                "best": {"name": "hybrid", "recall_at_k": 0.9857, "mrr": 0.8881},
                "results": [
                    {
                        "name": "hybrid",
                        "recall_at_k": 0.9857,
                        "mrr": 0.8881,
                        "evaluable": 70,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    smoke_path.write_text(
        release_gate.json.dumps(
            {
                "status": "passed",
                "total": 3,
                "failed": 0,
                "metadata": {
                    "server_base_url": "https://example.com:443",
                    "app_version": "0.90.0",
                },
                "failed_names": [],
                "results": [{"name": "健康检查接口", "passed": True, "detail": "ok"}],
            }
        ),
        encoding="utf-8",
    )
    callback_path.write_text(
        release_gate.json.dumps(
            {
                "status": "failed",
                "total": 61,
                "failed": 2,
                "metadata": {
                    "base_url": "https://example.com",
                    "app_version": "0.85.2",
                },
                "failed_names": ["case-a", "case-b"],
            }
        ),
        encoding="utf-8",
    )

    summary = release_gate.build_release_summary(
        include_rag_matrix=True,
        include_real_replay=False,
        include_real_replay_coverage=False,
        include_production_smoke=True,
        agent_eval_path=agent_eval_path,
        reply_eval_path=reply_eval_path,
        rag_matrix_path=rag_path,
        production_smoke_path=smoke_path,
        production_callback_path=callback_path,
    )

    assert summary["rag_eval_matrix"]["best"]["name"] == "hybrid"
    assert summary["rag_eval_matrix"]["corpus_size"] == 400
    assert summary["production_smoke"]["status"] == "passed"
    assert summary["production_smoke"]["checks"][0]["name"] == "健康检查接口"
    assert summary["production_employee_callback_probe"]["failed"] == 2
    assert summary["production_employee_callback_probe"]["failed_names"] == [
        "case-a",
        "case-b",
    ]


def test_read_json_report_resolves_latest_timestamp_report(tmp_path: Path) -> None:
    old_path = tmp_path / "smoke-20260710-010000.json"
    latest_path = tmp_path / "smoke-20260710-020000.json"
    old_path.write_text('{"status": "old"}', encoding="utf-8")
    latest_path.write_text('{"status": "latest"}', encoding="utf-8")

    payload = release_gate.read_json_report(tmp_path / "smoke-{timestamp}.json")

    assert payload["status"] == "latest"


def test_main_writes_json_summary(monkeypatch, tmp_path: Path, capsys) -> None:
    def fake_run_gate_steps(_steps):
        return (
            release_gate.GateStepResult(
                name="agent_eval_default",
                command=("python", "scripts/report_agent_eval.py"),
                returncode=0,
                stdout="agent_eval status=passed total=133 failed=0",
                stderr="",
            ),
        )

    monkeypatch.setattr(release_gate, "run_gate_steps", fake_run_gate_steps)
    output_path = tmp_path / "gate.json"

    exit_code = release_gate.main(["--json-out", str(output_path), "--summary"])

    assert exit_code == 0
    assert output_path.exists()
    payload = release_gate.json.loads(output_path.read_text(encoding="utf-8"))
    assert "release_summary" in payload
    assert "langchain_ai_layer_release_gate status=passed" in capsys.readouterr().out


def test_main_records_real_replay_options(monkeypatch, tmp_path: Path, capsys) -> None:
    captured_steps: list[release_gate.GateStep] = []

    def fake_run_gate_steps(steps):
        captured_steps.extend(steps)
        return (
            release_gate.GateStepResult(
                name="real_conversation_replay",
                command=("python", "scripts/check_real_conversation_replay.py"),
                returncode=0,
                stdout="real_conversation_replay status=passed total=2 failed=0",
                stderr="",
            ),
        )

    monkeypatch.setattr(release_gate, "run_gate_steps", fake_run_gate_steps)
    output_path = tmp_path / "gate.json"
    fixture_path = tmp_path / "fixture.json"

    exit_code = release_gate.main(
        [
            "--include-real-replay",
            "--real-replay-fixture",
            str(fixture_path),
            "--json-out",
            str(output_path),
            "--summary",
        ]
    )

    payload = release_gate.json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert any(step.name == "real_conversation_replay" for step in captured_steps)
    assert any(str(fixture_path) in step.command for step in captured_steps)
    assert payload["include_real_replay"] is True
    assert "langchain_ai_layer_release_gate status=passed" in capsys.readouterr().out


def test_main_records_real_replay_pool_options(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    captured_steps: list[release_gate.GateStep] = []

    def fake_run_gate_steps(steps):
        captured_steps.extend(steps)
        return (
            release_gate.GateStepResult(
                name="real_conversation_replay_pool",
                command=("python", "scripts/check_real_conversation_replay_pool.py"),
                returncode=0,
                stdout="real_conversation_replay_pool status=passed",
                stderr="",
            ),
        )

    monkeypatch.setattr(release_gate, "run_gate_steps", fake_run_gate_steps)
    output_path = tmp_path / "gate.json"
    manifest_path = tmp_path / "pool.json"

    exit_code = release_gate.main(
        [
            "--include-real-replay-pool",
            "--require-real-replay-pool",
            "--real-replay-pool-manifest",
            str(manifest_path),
            "--json-out",
            str(output_path),
            "--summary",
        ]
    )

    payload = release_gate.json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert any(step.name == "real_conversation_replay_pool" for step in captured_steps)
    assert any("--require-real" in step.command for step in captured_steps)
    assert payload["include_real_replay_pool"] is True
    assert payload["require_real_replay_pool"] is True
    assert "langchain_ai_layer_release_gate status=passed" in capsys.readouterr().out


def test_main_records_real_replay_intake_readiness_options(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    captured_steps: list[release_gate.GateStep] = []

    def fake_run_gate_steps(steps):
        captured_steps.extend(steps)
        return (
            release_gate.GateStepResult(
                name="real_conversation_replay_intake_readiness",
                command=(
                    "python",
                    "scripts/check_real_conversation_replay_intake_readiness.py",
                ),
                returncode=0,
                stdout="real_conversation_replay_intake status=passed",
                stderr="",
            ),
        )

    monkeypatch.setattr(release_gate, "run_gate_steps", fake_run_gate_steps)
    output_path = tmp_path / "gate.json"

    exit_code = release_gate.main(
        [
            "--include-real-replay-intake-readiness",
            "--json-out",
            str(output_path),
            "--summary",
        ]
    )

    payload = release_gate.json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert any(
        step.name == "real_conversation_replay_intake_readiness"
        for step in captured_steps
    )
    assert payload["include_real_replay_intake_readiness"] is True
    assert "langchain_ai_layer_release_gate status=passed" in capsys.readouterr().out


def test_main_records_observability_evidence_options(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    captured_steps: list[release_gate.GateStep] = []

    def fake_run_gate_steps(steps):
        captured_steps.extend(steps)
        return (
            release_gate.GateStepResult(
                name="langsmith_runtime_config",
                command=(
                    "python",
                    "scripts/check_langsmith_runtime_config.py",
                ),
                returncode=0,
                stdout="langsmith_runtime_config status=passed",
                stderr="",
            ),
        )

    monkeypatch.setattr(release_gate, "run_gate_steps", fake_run_gate_steps)
    output_path = tmp_path / "gate.json"

    exit_code = release_gate.main(
        [
            "--include-observability-evidence",
            "--json-out",
            str(output_path),
            "--summary",
        ]
    )

    payload = release_gate.json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert any(
        step.name == "langchain_observability_evidence" for step in captured_steps
    )
    assert any(step.name == "langsmith_runtime_config" for step in captured_steps)
    assert payload["include_observability_evidence"] is True
    assert "langchain_ai_layer_release_gate status=passed" in capsys.readouterr().out


def test_main_records_production_runtime_capacity_options(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    captured_steps: list[release_gate.GateStep] = []

    def fake_run_gate_steps(steps):
        captured_steps.extend(steps)
        return (
            release_gate.GateStepResult(
                name="production_runtime_capacity",
                command=("python", "scripts/check_langchain_ai_layer_capacity.py"),
                returncode=0,
                stdout="langchain_ai_layer_capacity status=passed",
                stderr="",
            ),
        )

    monkeypatch.setattr(release_gate, "run_gate_steps", fake_run_gate_steps)
    output_path = tmp_path / "gate.json"

    exit_code = release_gate.main(
        [
            "--include-production-runtime-capacity",
            "--json-out",
            str(output_path),
            "--summary",
        ]
    )

    payload = release_gate.json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert any(step.name == "production_runtime_capacity" for step in captured_steps)
    assert payload["include_production_runtime_capacity"] is True
    assert "langchain_ai_layer_release_gate status=passed" in capsys.readouterr().out


def test_main_records_production_smoke_options(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    captured_steps: list[release_gate.GateStep] = []

    def fake_run_gate_steps(steps):
        captured_steps.extend(steps)
        return (
            release_gate.GateStepResult(
                name="production_smoke",
                command=("python", "scripts/smoke_test.py"),
                returncode=0,
                stdout="{}",
                stderr="",
            ),
        )

    monkeypatch.setattr(release_gate, "run_gate_steps", fake_run_gate_steps)
    output_path = tmp_path / "gate.json"

    exit_code = release_gate.main(
        [
            "--include-production-smoke",
            "--production-base-url",
            "https://example.com",
            "--json-out",
            str(output_path),
            "--summary",
        ]
    )

    payload = release_gate.json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert any(step.name == "production_smoke" for step in captured_steps)
    assert payload["include_production_smoke"] is True
    assert payload["production_base_url"] == "https://example.com"
    assert "langchain_ai_layer_release_gate status=passed" in capsys.readouterr().out


def test_ensure_output_directories_creates_rag_parent(
    tmp_path: Path, monkeypatch
) -> None:
    rag_path = tmp_path / "rag-eval" / "latest.json"
    monkeypatch.setattr(release_gate, "DEFAULT_RAG_MATRIX_PATH", rag_path)
    monkeypatch.setattr(
        release_gate,
        "DEFAULT_AGENT_EVAL_PATH",
        tmp_path / "agent-eval" / "latest.json",
    )
    monkeypatch.setattr(
        release_gate,
        "DEFAULT_REPLY_PROBE_PATH",
        tmp_path / "agent-eval" / "reply-probe.json",
    )
    monkeypatch.setattr(
        release_gate,
        "DEFAULT_REPLY_EVAL_PATH",
        tmp_path / "agent-eval" / "reply-eval.json",
    )

    release_gate.ensure_output_directories(include_rag_matrix=True)

    assert rag_path.parent.exists()


def test_ensure_output_directories_creates_real_replay_parents(
    tmp_path: Path, monkeypatch
) -> None:
    real_replay_path = tmp_path / "agent-eval" / "real-replay.json"
    real_replies_path = tmp_path / "agent-eval" / "real-replies.json"
    real_agent_eval_path = tmp_path / "agent-eval" / "real-agent.json"
    monkeypatch.setattr(
        release_gate,
        "DEFAULT_AGENT_EVAL_PATH",
        tmp_path / "agent-eval" / "latest.json",
    )
    monkeypatch.setattr(
        release_gate,
        "DEFAULT_REPLY_PROBE_PATH",
        tmp_path / "agent-eval" / "reply-probe.json",
    )
    monkeypatch.setattr(
        release_gate,
        "DEFAULT_REPLY_EVAL_PATH",
        tmp_path / "agent-eval" / "reply-eval.json",
    )
    monkeypatch.setattr(release_gate, "DEFAULT_REAL_REPLAY_PATH", real_replay_path)
    monkeypatch.setattr(release_gate, "DEFAULT_REAL_REPLIES_PATH", real_replies_path)
    monkeypatch.setattr(
        release_gate,
        "DEFAULT_REAL_AGENT_EVAL_PATH",
        real_agent_eval_path,
    )

    release_gate.ensure_output_directories(
        include_rag_matrix=False,
        include_real_replay=True,
    )

    assert real_replay_path.parent.exists()
    assert real_replies_path.parent.exists()
    assert real_agent_eval_path.parent.exists()


def test_ensure_output_directories_creates_real_coverage_parent(
    tmp_path: Path, monkeypatch
) -> None:
    coverage_path = tmp_path / "agent-eval" / "coverage.json"
    monkeypatch.setattr(
        release_gate,
        "DEFAULT_AGENT_EVAL_PATH",
        tmp_path / "agent-eval" / "latest.json",
    )
    monkeypatch.setattr(
        release_gate,
        "DEFAULT_REPLY_PROBE_PATH",
        tmp_path / "agent-eval" / "reply-probe.json",
    )
    monkeypatch.setattr(
        release_gate,
        "DEFAULT_REPLY_EVAL_PATH",
        tmp_path / "agent-eval" / "reply-eval.json",
    )
    monkeypatch.setattr(release_gate, "DEFAULT_REAL_COVERAGE_PATH", coverage_path)

    release_gate.ensure_output_directories(
        include_rag_matrix=False,
        include_real_replay_coverage=True,
    )

    assert coverage_path.parent.exists()


def test_ensure_output_directories_creates_real_intake_parent(
    tmp_path: Path, monkeypatch
) -> None:
    intake_path = tmp_path / "agent-eval" / "intake.json"
    monkeypatch.setattr(
        release_gate,
        "DEFAULT_AGENT_EVAL_PATH",
        tmp_path / "agent-eval" / "latest.json",
    )
    monkeypatch.setattr(
        release_gate,
        "DEFAULT_REPLY_PROBE_PATH",
        tmp_path / "agent-eval" / "reply-probe.json",
    )
    monkeypatch.setattr(
        release_gate,
        "DEFAULT_REPLY_EVAL_PATH",
        tmp_path / "agent-eval" / "reply-eval.json",
    )
    monkeypatch.setattr(
        release_gate,
        "DEFAULT_REAL_INTAKE_READINESS_PATH",
        intake_path,
    )

    release_gate.ensure_output_directories(
        include_rag_matrix=False,
        include_real_replay_intake_readiness=True,
    )

    assert intake_path.parent.exists()


def test_ensure_output_directories_creates_observability_parent(
    tmp_path: Path, monkeypatch
) -> None:
    observability_path = tmp_path / "agent-traces" / "observability.json"
    langsmith_path = tmp_path / "agent-traces" / "langsmith.json"
    monkeypatch.setattr(
        release_gate,
        "DEFAULT_AGENT_EVAL_PATH",
        tmp_path / "agent-eval" / "latest.json",
    )
    monkeypatch.setattr(
        release_gate,
        "DEFAULT_REPLY_PROBE_PATH",
        tmp_path / "agent-eval" / "reply-probe.json",
    )
    monkeypatch.setattr(
        release_gate,
        "DEFAULT_REPLY_EVAL_PATH",
        tmp_path / "agent-eval" / "reply-eval.json",
    )
    monkeypatch.setattr(
        release_gate,
        "DEFAULT_OBSERVABILITY_EVIDENCE_PATH",
        observability_path,
    )
    monkeypatch.setattr(
        release_gate,
        "DEFAULT_LANGSMITH_RUNTIME_CONFIG_PATH",
        langsmith_path,
    )

    release_gate.ensure_output_directories(
        include_rag_matrix=False,
        include_observability_evidence=True,
    )

    assert observability_path.parent.exists()
    assert langsmith_path.parent.exists()


def test_ensure_output_directories_creates_capacity_parent(
    tmp_path: Path, monkeypatch
) -> None:
    capacity_path = tmp_path / "agent-traces" / "capacity.json"
    monkeypatch.setattr(
        release_gate,
        "DEFAULT_AGENT_EVAL_PATH",
        tmp_path / "agent-eval" / "latest.json",
    )
    monkeypatch.setattr(
        release_gate,
        "DEFAULT_REPLY_PROBE_PATH",
        tmp_path / "agent-eval" / "reply-probe.json",
    )
    monkeypatch.setattr(
        release_gate,
        "DEFAULT_REPLY_EVAL_PATH",
        tmp_path / "agent-eval" / "reply-eval.json",
    )
    monkeypatch.setattr(release_gate, "DEFAULT_CAPACITY_PATH", capacity_path)

    release_gate.ensure_output_directories(
        include_rag_matrix=False,
        include_production_runtime_capacity=True,
    )

    assert capacity_path.parent.exists()


def test_ensure_output_directories_creates_production_report_parents(
    tmp_path: Path, monkeypatch
) -> None:
    smoke_path = tmp_path / "smoke" / "prod.json"
    callback_path = tmp_path / "wecom-employee-agent" / "callback.json"
    monkeypatch.setattr(
        release_gate,
        "DEFAULT_AGENT_EVAL_PATH",
        tmp_path / "agent-eval" / "latest.json",
    )
    monkeypatch.setattr(
        release_gate,
        "DEFAULT_REPLY_PROBE_PATH",
        tmp_path / "agent-eval" / "reply-probe.json",
    )
    monkeypatch.setattr(
        release_gate,
        "DEFAULT_REPLY_EVAL_PATH",
        tmp_path / "agent-eval" / "reply-eval.json",
    )
    monkeypatch.setattr(release_gate, "DEFAULT_PRODUCTION_SMOKE_PATH", smoke_path)
    monkeypatch.setattr(
        release_gate,
        "DEFAULT_PRODUCTION_CALLBACK_PATH",
        callback_path,
    )

    release_gate.ensure_output_directories(
        include_rag_matrix=False,
        include_production_smoke=True,
    )

    assert smoke_path.parent.exists()
    assert callback_path.parent.exists()
