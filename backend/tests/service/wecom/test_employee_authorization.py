"""企微员工 actor 白名单授权合同测试。"""

import pytest

from app.service.wecom.employee_authorization import (
    EmployeeActorAuthorizer,
    EmployeeAuthorizationError,
)


def test_employee_authorizer_accepts_configured_user_chat_and_corp(monkeypatch) -> None:
    from app.service.wecom import employee_authorization

    monkeypatch.setattr(
        employee_authorization.settings, "WECOM_EMPLOYEE_AUTH_REQUIRED", True
    )
    monkeypatch.setattr(
        employee_authorization.settings, "WECOM_EMPLOYEE_ALLOWED_USERS", "staff-1"
    )
    monkeypatch.setattr(
        employee_authorization.settings, "WECOM_EMPLOYEE_ALLOWED_CHATS", "chat-1"
    )
    monkeypatch.setattr(
        employee_authorization.settings, "WECOM_EMPLOYEE_CORP_ID", "corp-1"
    )

    actor = EmployeeActorAuthorizer().authorize(
        {"from": {"userid": "staff-1"}, "chatid": "chat-1", "corpid": "corp-1"}
    )

    assert actor.user_id == "staff-1"


def test_employee_authorizer_restricts_ops_tools_by_server_side_user(
    monkeypatch,
) -> None:
    from app.service.wecom import employee_authorization

    monkeypatch.setattr(
        employee_authorization.settings, "WECOM_EMPLOYEE_AUTH_REQUIRED", True
    )
    monkeypatch.setattr(
        employee_authorization.settings, "WECOM_EMPLOYEE_ALLOWED_USERS", "staff-1"
    )
    monkeypatch.setattr(
        employee_authorization.settings, "WECOM_EMPLOYEE_OPS_USERS", "staff-ops"
    )
    monkeypatch.setattr(
        employee_authorization.settings, "WECOM_EMPLOYEE_CORP_ID", "corp-1"
    )
    authorizer = EmployeeActorAuthorizer()
    actor = authorizer.authorize(
        {"from": {"userid": "staff-1"}, "role": "ops", "corpid": "corp-1"}
    )

    with pytest.raises(EmployeeAuthorizationError):
        authorizer.authorize_tool(actor, "customer_lookup")


def test_employee_authorizer_allows_ops_user_tools(monkeypatch) -> None:
    from app.service.wecom import employee_authorization

    monkeypatch.setattr(
        employee_authorization.settings, "WECOM_EMPLOYEE_ALLOWED_USERS", "staff-1"
    )
    monkeypatch.setattr(
        employee_authorization.settings, "WECOM_EMPLOYEE_OPS_USERS", "staff-1"
    )
    actor = EmployeeActorAuthorizer().authorize({"from": {"userid": "staff-1"}})

    EmployeeActorAuthorizer().authorize_tool(actor, "customer_lookup")
    assert "customer_lookup" in EmployeeActorAuthorizer().allowed_agent_tools(actor)


def test_employee_authorizer_requires_allowlisted_group_chat(monkeypatch) -> None:
    from app.service.wecom import employee_authorization

    monkeypatch.setattr(
        employee_authorization.settings, "WECOM_EMPLOYEE_ALLOWED_USERS", "staff-1"
    )
    monkeypatch.setattr(
        employee_authorization.settings, "WECOM_EMPLOYEE_ALLOWED_CHATS", ""
    )

    with pytest.raises(EmployeeAuthorizationError, match="群聊白名单"):
        EmployeeActorAuthorizer().authorize(
            {
                "from": {"userid": "staff-1"},
                "chattype": "group",
                "chatid": "chat-1",
            }
        )


@pytest.mark.parametrize(
    "message",
    [
        {"from": {"userid": "staff-2"}, "chatid": "chat-1", "corpid": "corp-1"},
        {
            "from": {"userid": "staff-1"},
            "chatid": "chat-2",
            "chattype": "group",
            "corpid": "corp-1",
        },
        {"from": {"userid": "staff-1"}, "chatid": "chat-1", "corpid": "corp-2"},
    ],
)
def test_employee_authorizer_rejects_actor_scope(monkeypatch, message) -> None:
    from app.service.wecom import employee_authorization

    monkeypatch.setattr(
        employee_authorization.settings, "WECOM_EMPLOYEE_AUTH_REQUIRED", True
    )
    monkeypatch.setattr(
        employee_authorization.settings, "WECOM_EMPLOYEE_ALLOWED_USERS", "staff-1"
    )
    monkeypatch.setattr(
        employee_authorization.settings, "WECOM_EMPLOYEE_ALLOWED_CHATS", "chat-1"
    )
    monkeypatch.setattr(
        employee_authorization.settings, "WECOM_EMPLOYEE_CORP_ID", "corp-1"
    )

    with pytest.raises(EmployeeAuthorizationError):
        EmployeeActorAuthorizer().authorize(message)
