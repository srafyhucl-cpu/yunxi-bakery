from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EMPLOYEE_AGENT_FILES = (
    PROJECT_ROOT / "app/service/wecom/employee_agent_order_constants.py",
    PROJECT_ROOT / "app/service/wecom/employee_agent_order_date.py",
    PROJECT_ROOT / "app/service/wecom/employee_agent_order_date_calendar.py",
    PROJECT_ROOT / "app/service/wecom/employee_agent_order_delivery_time.py",
    PROJECT_ROOT / "app/service/wecom/employee_agent_order_keywords.py",
    PROJECT_ROOT / "app/service/wecom/employee_agent_order_plan.py",
    PROJECT_ROOT / "app/service/wecom/employee_agent_order_predicates.py",
    PROJECT_ROOT / "app/service/wecom/employee_agent_order_query.py",
    PROJECT_ROOT / "app/service/wecom/employee_agent_order_stop_words.py",
)
WECOM_SERVICE_WARNING_LIMIT = 150


def test_employee_agent_order_planning_files_stay_small() -> None:
    oversized_files = [
        f"{path.name}:{_line_count(path)}"
        for path in EMPLOYEE_AGENT_FILES
        if _line_count(path) > WECOM_SERVICE_WARNING_LIMIT
    ]

    assert oversized_files == []


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())
