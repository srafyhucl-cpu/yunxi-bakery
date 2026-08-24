"""企微智能机器人 API 插件服务。"""

from typing import Any

from app.config import APP_VERSION

PLUGIN_NAME = "yunxi_employee_assistant_ping"


class WeComBotPluginService:
    """构建企微智能机器人插件响应。"""

    def build_ping_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        """返回用于企微插件连通性验证的扁平结果。"""
        received_text = extract_text(payload)
        suggested_reply = "企微智能机器人插件已接通，可以继续配置业务工具。"
        if received_text:
            suggested_reply = f"已收到：{received_text}"
        return {
            "ok": True,
            "plugin": PLUGIN_NAME,
            "message": "芸熙员工助理插件已接通",
            "receivedText": received_text,
            "suggestedReply": suggested_reply,
            "result": suggested_reply,
            "resultText": suggested_reply,
            "nextAction": "下一步可接入查订单、查客户、知识库问答等业务 skill。",
            "version": APP_VERSION,
        }


def extract_text(payload: dict[str, Any]) -> str:
    """从常见企微插件入参名中提取员工输入文本。"""
    for key in ("text", "query", "question", "content", "message", "input"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""
