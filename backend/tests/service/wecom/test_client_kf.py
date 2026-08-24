from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.service.wecom.client_kf import KfClientMixin


@dataclass
class FakeResponse:
    payload: dict[str, Any]
    status_code: int = 200
    content: bytes = b""

    def json(self) -> dict[str, Any]:
        return self.payload

    async def aread(self) -> bytes:
        return self.content


class FakeHttpClient:
    def __init__(self) -> None:
        self.post_responses: list[FakeResponse] = []
        self.get_responses: list[FakeResponse] = []
        self.posts: list[dict[str, Any]] = []
        self.gets: list[dict[str, Any]] = []

    async def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.posts.append({"url": url, **kwargs})
        return self.post_responses.pop(0)

    async def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.gets.append({"url": url, **kwargs})
        return self.get_responses.pop(0)


class FakeKfClient(KfClientMixin):
    def __init__(self, http_client: FakeHttpClient) -> None:
        self._client = http_client

    async def get_token(self) -> str:
        return "access-token"


async def test_send_kf_text_builds_wecom_payload(monkeypatch) -> None:
    http_client = FakeHttpClient()
    http_client.post_responses.append(FakeResponse({"errcode": 0}))
    client = FakeKfClient(http_client)
    monkeypatch.setattr("app.service.wecom.client_kf.settings.WECOM_KF_ID", "wk_test")

    result = await client.send_kf_text("external-user", "您好", msgid="msg-1")

    assert result == {"errcode": 0}
    request = http_client.posts[0]
    assert request["params"] == {"access_token": "access-token"}
    assert request["json"] == {
        "touser": "external-user",
        "open_kfid": "wk_test",
        "msgtype": "text",
        "text": {"content": "您好"},
        "msgid": "msg-1",
    }


async def test_send_kf_link_and_event_text_use_expected_endpoints(monkeypatch) -> None:
    http_client = FakeHttpClient()
    http_client.post_responses.extend(
        [FakeResponse({"errcode": 0}), FakeResponse({"errcode": 0})]
    )
    client = FakeKfClient(http_client)
    monkeypatch.setattr("app.service.wecom.client_kf.settings.WECOM_KF_ID", "wk_test")

    link_result = await client.send_kf_link(
        "external-user",
        "蛋糕",
        "https://example.invalid/item",
        desc="介绍",
        thumb_media_id="media-1",
    )
    event_result = await client.send_kf_event_text("event-code", "已收到")

    assert link_result == {"errcode": 0}
    assert event_result == {"errcode": 0}
    assert http_client.posts[0]["url"].endswith("/kf/send_msg")
    assert http_client.posts[0]["json"]["msgtype"] == "link"
    assert http_client.posts[1]["url"].endswith("/kf/send_msg_on_event")
    assert http_client.posts[1]["json"] == {
        "code": "event-code",
        "msgtype": "text",
        "text": {"content": "已收到"},
    }


async def test_customer_display_name_prefers_nickname() -> None:
    http_client = FakeHttpClient()
    http_client.post_responses.append(
        FakeResponse(
            {
                "errcode": 0,
                "customer_list": [{"nickname": " 芸熙顾客 ", "name": "备用名"}],
            }
        )
    )
    client = FakeKfClient(http_client)

    display_name = await client.get_kf_customer_display_name("external-user")

    assert display_name == "芸熙顾客"
    assert http_client.posts[0]["json"] == {"external_userid_list": ["external-user"]}


async def test_upload_and_download_kf_media(monkeypatch) -> None:
    http_client = FakeHttpClient()
    http_client.post_responses.append(FakeResponse({"errcode": 0, "media_id": "m-1"}))
    http_client.get_responses.append(FakeResponse({}, content=b"image-bytes"))
    client = FakeKfClient(http_client)

    media_id = await client.upload_kf_temp_media(
        b"image-bytes", file_type="image", file_name="cake.jpg"
    )
    downloaded = await client.download_kf_temp_media("m-1")

    assert media_id == "m-1"
    assert downloaded == b"image-bytes"
    assert http_client.posts[0]["files"]["media"] == (
        "cake.jpg",
        b"image-bytes",
        "image/jpeg",
    )
    assert http_client.gets[0]["timeout"] == 30


async def test_sync_kf_messages_includes_cursor_and_limit(monkeypatch) -> None:
    http_client = FakeHttpClient()
    http_client.post_responses.append(FakeResponse({"errcode": 0, "msg_list": []}))
    client = FakeKfClient(http_client)
    monkeypatch.setattr("app.service.wecom.client_kf.settings.WECOM_KF_ID", "wk_test")

    result = await client.sync_kf_messages("kf-token", cursor="next", limit=20)

    assert result == {"errcode": 0, "msg_list": []}
    assert http_client.posts[0]["json"] == {
        "token": "kf-token",
        "open_kfid": "wk_test",
        "limit": 20,
        "cursor": "next",
    }


async def test_ensure_kf_session_active_respects_manual_state() -> None:
    http_client = FakeHttpClient()
    http_client.post_responses.append(FakeResponse({"errcode": 0, "service_state": 3}))
    client = FakeKfClient(http_client)

    can_send = await client.ensure_kf_session_active("external-user")

    assert can_send is False
    assert len(http_client.posts) == 1
    assert http_client.posts[0]["url"].endswith("/kf/service_state/get")


async def test_ensure_kf_session_active_switches_waiting_state(monkeypatch) -> None:
    http_client = FakeHttpClient()
    http_client.post_responses.extend(
        [
            FakeResponse({"errcode": 0, "service_state": 0}),
            FakeResponse({"errcode": 0}),
        ]
    )
    client = FakeKfClient(http_client)
    monkeypatch.setattr("app.service.wecom.client_kf.settings.WECOM_KF_ID", "wk_test")

    can_send = await client.ensure_kf_session_active("external-user")

    assert can_send is True
    assert http_client.posts[1]["url"].endswith("/kf/service_state/trans")
    assert http_client.posts[1]["json"] == {
        "open_kfid": "wk_test",
        "external_userid": "external-user",
        "service_state": 1,
    }


async def test_trans_service_state_adds_servicer_for_manual_transfer(
    monkeypatch,
) -> None:
    http_client = FakeHttpClient()
    http_client.post_responses.append(FakeResponse({"errcode": 0}))
    client = FakeKfClient(http_client)
    monkeypatch.setattr("app.service.wecom.client_kf.settings.WECOM_KF_ID", "wk_test")

    switched = await client._trans_service_state(  # noqa: SLF001
        "external-user",
        3,
        servicer_userid="staff-1",
    )

    assert switched is True
    assert http_client.posts[0]["json"] == {
        "open_kfid": "wk_test",
        "external_userid": "external-user",
        "service_state": 3,
        "servicer_userid": "staff-1",
    }


async def test_get_first_servicer_falls_back_to_post(monkeypatch) -> None:
    http_client = FakeHttpClient()
    http_client.get_responses.append(FakeResponse({"errcode": 40003}))
    http_client.post_responses.append(
        FakeResponse({"errcode": 0, "servicer_list": [{"userid": "staff-1"}]})
    )
    client = FakeKfClient(http_client)
    monkeypatch.setattr("app.service.wecom.client_kf.settings.WECOM_KF_ID", "wk_test")

    servicer_userid = await client._get_first_servicer()  # noqa: SLF001

    assert servicer_userid == "staff-1"
    assert http_client.gets[0]["params"] == {
        "access_token": "access-token",
        "open_kfid": "wk_test",
    }
    assert http_client.posts[0]["params"] == {
        "access_token": "access-token",
        "open_kfid": "wk_test",
    }
