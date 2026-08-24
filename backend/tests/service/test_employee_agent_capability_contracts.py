from __future__ import annotations

from datetime import date

from app.service.wecom.employee_agent_capability_contracts import (
    CAPABILITY_CONTRACTS,
    capability_card_names,
    capability_contracts_by_name,
)
from scripts.wecom_employee_agent_probe_cases import default_probe_cases


def test_capability_contracts_cover_all_cards() -> None:
    contracts = capability_contracts_by_name()

    assert set(contracts) == capability_card_names()


def test_capability_contracts_have_probe_evidence() -> None:
    probe_names = {case.name for case in default_probe_cases(date(2026, 7, 3))}

    for contract in CAPABILITY_CONTRACTS:
        assert contract.parameter_rules
        assert contract.missing_parameter_reply
        assert contract.empty_result_reply
        assert contract.error_reply
        assert set(contract.probe_names).issubset(probe_names)
