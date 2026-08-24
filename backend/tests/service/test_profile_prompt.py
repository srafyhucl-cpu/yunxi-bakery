"""顾客画像 Prompt 渲染测试。"""

from app.models.customer_profile import CustomerProfile
from app.models.knowledge import KnowledgeEntry
from app.service.llm.profile_prompt import render_customer_profile
from app.service.llm.prompt import build_system_prompt


def test_render_customer_profile_injects_allergy_as_instruction() -> None:
    profile = CustomerProfile(
        id="p-1",
        channel="youzan",
        user_id="buyer-1",
        display_name="小林",
        preferences_json='{"甜度":"少糖","尺寸":"6寸"}',
        allergens_json='["坚果"]',
    )

    rendered = render_customer_profile(profile)

    assert "## 顾客档案" in rendered
    assert "顾客称呼：小林" in rendered
    assert "顾客偏好：甜度: 少糖、尺寸: 6寸" in rendered
    assert "该顾客登记过敏原：坚果" in rendered
    assert "不要替顾客判断能否食用" in rendered
    assert "不能吃" not in rendered


def test_build_system_prompt_omits_empty_profile_section() -> None:
    prompt = build_system_prompt([])

    assert "## 顾客档案" not in prompt


def test_build_system_prompt_includes_customer_profile() -> None:
    profile = CustomerProfile(
        id="p-1",
        channel="youzan",
        user_id="buyer-1",
        display_name="小林",
    )
    entries = [
        KnowledgeEntry(category="product", title="草莓蛋糕", content="48元"),
    ]

    prompt = build_system_prompt(entries, customer_profile=profile)

    assert "## 顾客档案" in prompt
    assert "顾客称呼：小林" in prompt
    assert "草莓蛋糕" in prompt
