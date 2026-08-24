"""微信客服 sync_msg 消息分类模型与纯函数。"""

from dataclasses import dataclass

from app.service.wecom.kf_handoff_sync import SyncedCustomerMessage
from app.service.wecom.kf_servicer_sync import SyncedServicerMessage

CUSTOMER_ORIGIN = 3
SYSTEM_ORIGIN = 4
SERVICER_ORIGIN = 5
SESSION_STATUS_EVENT = "session_status_change"
SESSION_END_CHANGE_TYPE = 3
HANDOFF_EVENT_TYPES = {1, 2, 4}


@dataclass(frozen=True)
class QueuedNontextMessage:
    """等待入队的非文本客服消息。"""

    external_userid: str
    open_kfid: str
    msgtype: str
    media_id: str
    msg_id: str


@dataclass(frozen=True)
class SyncEvent:
    """微信客服系统状态事件。"""

    external_userid: str
    change_type: int
    staff_id: str
    event_code: str = ""


@dataclass(frozen=True)
class CollectedMessages:
    """一次或多次 sync_msg 拉取后的分类结果。"""

    user_messages: dict[str, dict[str, dict]]
    nontext_messages: list[QueuedNontextMessage]
    handoff_customer_messages: list[SyncedCustomerMessage]
    servicer_messages: list[SyncedServicerMessage]
    start_events: list[SyncEvent]
    end_events: list[SyncEvent]
    active_handoff_users: set[str]
    ended_handoff_users: set[str]
    total_count: int


def empty_collected() -> CollectedMessages:
    return CollectedMessages({}, [], [], [], [], [], set(), set(), 0)


def merge_collected_messages(
    left: CollectedMessages,
    right: CollectedMessages,
) -> CollectedMessages:
    user_messages = {key: value.copy() for key, value in left.user_messages.items()}
    for external_userid, messages in right.user_messages.items():
        user_messages.setdefault(external_userid, {}).update(messages)

    return CollectedMessages(
        user_messages=user_messages,
        nontext_messages=[*left.nontext_messages, *right.nontext_messages],
        handoff_customer_messages=[
            *left.handoff_customer_messages,
            *right.handoff_customer_messages,
        ],
        servicer_messages=[*left.servicer_messages, *right.servicer_messages],
        start_events=[*left.start_events, *right.start_events],
        end_events=[*left.end_events, *right.end_events],
        active_handoff_users=right.active_handoff_users,
        ended_handoff_users=right.ended_handoff_users,
        total_count=left.total_count + right.total_count,
    )


def append_sync_event(
    event: SyncEvent,
    start_events: list[SyncEvent],
    end_events: list[SyncEvent],
) -> None:
    if event.change_type == SESSION_END_CHANGE_TYPE:
        end_events.append(event)
    else:
        start_events.append(event)


def extract_event_type(item: dict) -> str:
    event = item.get("event", {})
    if isinstance(event, dict):
        return str(event.get("event_type") or item.get("event_type", ""))
    return str(item.get("event_type", ""))


def build_sync_event(item: dict) -> SyncEvent | None:
    if item.get("origin", 0) != SYSTEM_ORIGIN:
        return None
    event = item.get("event", {})
    if not isinstance(event, dict):
        return None
    if event.get("event_type") != SESSION_STATUS_EVENT:
        return None
    change_type = int(event.get("change_type", 0) or 0)
    if (
        change_type not in HANDOFF_EVENT_TYPES
        and change_type != SESSION_END_CHANGE_TYPE
    ):
        return None
    return SyncEvent(
        external_userid=item.get("external_userid", ""),
        change_type=change_type,
        staff_id=str(event.get("servicer_userid") or ""),
        event_code=str(event.get("welcome_code") or event.get("code") or ""),
    )


def extract_message_content(item: dict) -> str:
    msgtype = item.get("msgtype", "")
    if msgtype == "text":
        return item.get("text", {}).get("content", "").strip()
    return f"[{msgtype}消息]" if msgtype else ""


def extract_media_id(item: dict) -> str:
    msgtype = item.get("msgtype", "")
    if msgtype in ("image", "voice", "video", "file"):
        return item.get(msgtype, {}).get("media_id", "")
    return ""
