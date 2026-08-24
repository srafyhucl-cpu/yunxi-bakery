"""Agent Eval 通用模型测试。"""

from app.service.agents.evaluation import (
    AgentEvalAssertion,
    AgentEvalCase,
    AgentEvalResult,
    apply_fail_fast,
    combine_agent_eval_results,
    filter_agent_eval_result,
)


def test_agent_eval_result_calculates_status_and_pass_rate() -> None:
    result = AgentEvalResult(
        agent="sample",
        cases=(
            AgentEvalCase(
                case_id="ok",
                agent="sample",
                query="ok",
                metadata={"sensitive_scenarios": ["order", "refund"]},
                assertions=(AgentEvalAssertion("shape", True),),
            ),
            AgentEvalCase(
                case_id="fail",
                agent="sample",
                query="fail",
                metadata={"sensitive_scenarios": ["order"]},
                assertions=(AgentEvalAssertion("shape", False, "bad"),),
            ),
        ),
    )

    payload = result.to_dict()

    assert result.status == "failed"
    assert result.failed == 1
    assert result.pass_rate == 0.5
    assert payload["failed_ids"] == ["fail"]
    assert payload["case_groups"] == [
        {
            "group": "ungrouped",
            "total": 2,
            "failed": 1,
            "passed": 1,
            "pass_rate": 0.5,
        }
    ]
    assert payload["sensitive_scenarios"] == [
        {
            "scenario": "order",
            "total": 2,
            "failed": 1,
            "passed": 1,
            "pass_rate": 0.5,
        },
        {
            "scenario": "refund",
            "total": 1,
            "failed": 0,
            "passed": 1,
            "pass_rate": 1.0,
        },
    ]


def test_combine_agent_eval_results() -> None:
    customer = AgentEvalResult(
        agent="customer",
        cases=(
            AgentEvalCase(
                case_id="customer-ok",
                agent="customer",
                query="ok",
                group="product",
                metadata={"sensitive_scenarios": ["price"]},
                assertions=(AgentEvalAssertion("shape", True),),
            ),
        ),
    )
    employee = AgentEvalResult(
        agent="employee",
        cases=(
            AgentEvalCase(
                case_id="employee-ok",
                agent="employee",
                query="ok",
                group="planner",
                assertions=(AgentEvalAssertion("shape", True),),
            ),
        ),
    )

    payload = combine_agent_eval_results((customer, employee))

    assert payload["status"] == "passed"
    assert payload["total"] == 2
    assert payload["pass_rate"] == 1.0
    assert payload["agent_totals"] == [
        {
            "agent": "customer",
            "status": "passed",
            "total": 1,
            "failed": 0,
            "pass_rate": 1.0,
        },
        {
            "agent": "employee",
            "status": "passed",
            "total": 1,
            "failed": 0,
            "pass_rate": 1.0,
        },
    ]
    assert payload["case_groups"] == [
        {
            "group": "planner",
            "total": 1,
            "failed": 0,
            "passed": 1,
            "pass_rate": 1.0,
        },
        {
            "group": "product",
            "total": 1,
            "failed": 0,
            "passed": 1,
            "pass_rate": 1.0,
        },
    ]
    assert payload["sensitive_scenarios"] == [
        {
            "scenario": "price",
            "total": 1,
            "failed": 0,
            "passed": 1,
            "pass_rate": 1.0,
        }
    ]


def test_filter_agent_eval_result_by_case_id() -> None:
    result = AgentEvalResult(
        agent="sample",
        cases=(
            AgentEvalCase(
                case_id="keep",
                agent="sample",
                query="keep",
                assertions=(AgentEvalAssertion("shape", True),),
            ),
            AgentEvalCase(
                case_id="drop",
                agent="sample",
                query="drop",
                assertions=(AgentEvalAssertion("shape", True),),
            ),
        ),
    )

    filtered = filter_agent_eval_result(result, ("keep",))

    assert [case.case_id for case in filtered.cases] == ["keep"]
    assert filtered.metadata["case_filter"] == ["keep"]


def test_apply_fail_fast_keeps_cases_until_first_failure() -> None:
    result = AgentEvalResult(
        agent="sample",
        cases=(
            AgentEvalCase(
                case_id="ok",
                agent="sample",
                query="ok",
                assertions=(AgentEvalAssertion("shape", True),),
            ),
            AgentEvalCase(
                case_id="fail",
                agent="sample",
                query="fail",
                assertions=(AgentEvalAssertion("shape", False),),
            ),
            AgentEvalCase(
                case_id="later",
                agent="sample",
                query="later",
                assertions=(AgentEvalAssertion("shape", True),),
            ),
        ),
    )

    filtered = apply_fail_fast(result)

    assert [case.case_id for case in filtered.cases] == ["ok", "fail"]
    assert filtered.metadata["fail_fast"] is True
