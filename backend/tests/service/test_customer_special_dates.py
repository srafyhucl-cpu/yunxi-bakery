from app.models.customer_profile import CustomerProfile
from app.service.llm.profile_prompt import render_customer_profile
from app.service.offline.agent_memory import _parse_memory_json
from app.service.offline.memory_merge import merge_json_lists


def test_memory_parser_keeps_multiple_special_dates() -> None:
    parsed = _parse_memory_json(
        """
        {
          "display_name": "",
          "preferences": {},
          "order_summary": {},
          "special_dates": [
            {
              "type": "birthday",
              "person": "妈妈",
              "date": "05-20",
              "date_known": true,
              "usage": "生日蛋糕",
              "evidence": "妈妈5月20日生日"
            },
            {
              "type": "anniversary",
              "person": "夫妻",
              "date": "",
              "date_known": false,
              "usage": "结婚纪念日",
              "evidence": "下个月结婚纪念日"
            }
          ],
          "allergens": [],
          "consent_status": "unknown"
        }
        """
    )

    assert "妈妈" in parsed.special_dates_json
    assert "anniversary" in parsed.special_dates_json


def test_special_dates_merge_without_dropping_existing_records() -> None:
    existing = (
        '[{"type":"birthday","person":"妈妈","date":"05-20",'
        '"date_known":true,"usage":"生日蛋糕","evidence":"妈妈5月20日生日"}]'
    )
    new = (
        '[{"type":"birthday","person":"孩子","date":"",'
        '"date_known":false,"usage":"儿童生日","evidence":"给孩子过生日"},'
        '{"type":"birthday","person":"妈妈","date":"05-20",'
        '"date_known":true,"usage":"生日蛋糕","evidence":"妈妈5月20日生日"}]'
    )

    merged = merge_json_lists(new, existing)

    assert merged.count("birthday") == 2
    assert "妈妈" in merged
    assert "孩子" in merged


def test_render_customer_profile_includes_special_dates_as_careful_hint() -> None:
    profile = CustomerProfile(
        id="p-1",
        channel="wecom_kf",
        user_id="u-1",
        special_dates_json=(
            '[{"type":"birthday","person":"妈妈","date":"05-20",'
            '"date_known":true,"usage":"生日蛋糕","evidence":"妈妈5月20日生日"}]'
        ),
    )

    rendered = render_customer_profile(profile)

    assert "特殊日期提醒" in rendered
    assert "妈妈" in rendered
    assert "先自然核对" in rendered
