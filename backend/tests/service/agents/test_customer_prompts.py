"""客户机器人 Prompt 组件测试。"""

from pathlib import Path
import subprocess
import sys

from app.models.customer_profile import CustomerProfile
from app.models.knowledge import KnowledgeEntry
from app.service.agents.customer.prompts import (
    SESSION_SUMMARY_SECTION_TITLE,
    build_customer_context_messages,
    build_customer_system_prompt,
    build_guard_source_text,
    extract_product_titles,
)


def test_customer_system_prompt_injects_summary_as_read_only_context() -> None:
    prompt = build_customer_system_prompt(
        [
            KnowledgeEntry(
                category="policy",
                title="配送规则",
                content="三公里内可配送",
            )
        ],
        conversation_summary_text="客户早前说想要低糖生日蛋糕。",
    )

    assert SESSION_SUMMARY_SECTION_TITLE in prompt
    assert "低糖生日蛋糕" in prompt
    assert "订单、库存、配送、价格仍以工具和知识库为准" in prompt
    assert "三公里内可配送" in prompt


def test_customer_system_prompt_skips_empty_summary() -> None:
    prompt = build_customer_system_prompt([], conversation_summary_text="   ")

    assert SESSION_SUMMARY_SECTION_TITLE not in prompt
    assert "查不到该商品" in prompt


def test_customer_system_prompt_keeps_profile_hints() -> None:
    prompt = build_customer_system_prompt(
        [],
        CustomerProfile(
            id="profile-1",
            channel="youzan",
            user_id="buyer-1",
            display_name="小云",
        ),
    )

    assert "顾客档案" in prompt
    assert "小云" in prompt
    assert "查不到该商品" in prompt


def test_customer_context_messages_keeps_system_first_and_history_order() -> None:
    history = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "您好"},
    ]

    messages = build_customer_context_messages("system prompt", history)

    assert messages[0] == {"role": "system", "content": "system prompt"}
    assert messages[1:] == history


def test_prompt_helpers_extract_guard_sources() -> None:
    entries = [
        KnowledgeEntry(category="product", title="草莓蛋糕", content="48元"),
        KnowledgeEntry(category="faq", title="配送", content="三公里"),
    ]

    assert extract_product_titles(entries) == ("草莓蛋糕",)
    assert build_guard_source_text(entries) == "草莓蛋糕\n48元\n配送\n三公里"


def test_customer_prompt_import_does_not_import_langchain_runtime() -> None:
    project_root = Path(__file__).resolve().parents[3]
    command = (
        "import sys; "
        "import app.service.agents.customer.prompts; "
        "raise SystemExit(1 if 'langchain_openai' in sys.modules "
        "or 'langgraph' in sys.modules else 0)"
    )

    result = subprocess.run(
        [sys.executable, "-c", command],
        cwd=project_root,
        check=False,
    )

    assert result.returncode == 0
