"""模型外发文本的隐私脱敏合同测试。"""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.service.privacy_redaction import (
    redact_external_langchain_messages,
    redact_external_messages,
    redact_external_text,
)


def test_redaction_removes_phone_open_id_order_and_address() -> None:
    source = (
        "联系电话 13812345678，open_id=oAbcdefghijk123，订单号: ORD-20260711，"
        "地址：北京市朝阳区幸福路88号。"
    )

    redacted = redact_external_text(source)

    assert "13812345678" not in redacted
    assert "oAbcdefghijk123" not in redacted
    assert "ORD-20260711" not in redacted
    assert "北京市朝阳区幸福路88号" not in redacted
    assert "<手机号>" in redacted
    assert "<open_id>" in redacted
    assert "<订单号>" in redacted
    assert "<地址>" in redacted


def test_redaction_covers_nested_model_message_payloads() -> None:
    messages = redact_external_messages(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "手机号 13812345678"},
                    {"type": "text", "text": "订单号 ORD-20260711"},
                ],
            }
        ]
    )

    payload_text = str(messages)
    assert "13812345678" not in payload_text
    assert "ORD-20260711" not in payload_text


def test_redaction_preserves_langchain_message_contract() -> None:
    messages = redact_external_langchain_messages(
        [
            HumanMessage(content="订单号 ORD-20260711，手机号 13812345678"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "tool-1",
                        "name": "get_order_info",
                        "args": {"order_no": "ORD-20260711"},
                        "type": "tool_call",
                    }
                ],
            ),
            ToolMessage(content="订单号 ORD-20260711", tool_call_id="tool-1"),
        ]
    )

    assert isinstance(messages[0], HumanMessage)
    assert isinstance(messages[1], AIMessage)
    assert isinstance(messages[2], ToolMessage)
    assert "13812345678" not in str(messages)
    assert "ORD-20260711" not in str(messages)


def test_redaction_removes_structured_sensitive_fields_by_key() -> None:
    messages = redact_external_messages(
        [
            {
                "role": "tool",
                "content": {
                    "receiver_phone": "not-a-phone-format",
                    "delivery_address": "望京SOHO T3 1201",
                    "open_id": "short-id",
                    "order_no": "short-order",
                    "history_text": "没有格式特征的原始消息",
                    "status": "paid",
                },
            }
        ]
    )

    content = messages[0]["content"]
    assert content == {
        "receiver_phone": "<手机号>",
        "delivery_address": "<地址>",
        "open_id": "<open_id>",
        "order_no": "<订单号>",
        "history_text": "<原始消息>",
        "status": "paid",
    }


def test_redaction_removes_unstructured_region_address() -> None:
    redacted = redact_external_text("请送到北京市朝阳区望京SOHO三号楼")

    assert "北京市朝阳区望京SOHO三号楼" not in redacted
    assert "<地址>" in redacted
