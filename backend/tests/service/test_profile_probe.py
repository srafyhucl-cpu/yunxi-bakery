import json

from app.service.profile_probe import can_offer_profile_probe, mark_profile_probe_used


def test_profile_probe_allows_service_related_question_once() -> None:
    assert can_offer_profile_probe("{}", "想看看生日蛋糕") is True


def test_profile_probe_stops_after_budget_used() -> None:
    extra_info = mark_profile_probe_used("{}")

    assert can_offer_profile_probe(extra_info, "想看看生日蛋糕") is False
    assert json.loads(extra_info)["profile_probe_count"] == 1


def test_profile_probe_stops_for_order_and_handoff_signals() -> None:
    assert can_offer_profile_probe("{}", "我就要这个，下单吧") is False
    assert can_offer_profile_probe("{}", "帮我转人工客服") is False


def test_profile_probe_stops_for_low_patience_signal() -> None:
    assert can_offer_profile_probe("{}", "怎么还没说清楚，算了") is False
