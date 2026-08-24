"""知识检索命中日志报表服务。"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from app.repository.knowledge_repo import KnowledgeRepo

DEFAULT_RETRIEVAL_REPORT_LIMIT = 100
MAX_RETRIEVAL_REPORT_LIMIT = 500


class KnowledgeRetrievalReportService:
    """提供知识检索命中日志的只读聚合报表。"""

    def __init__(
        self,
        knowledge_repo: KnowledgeRepo,
        *,
        project_root: str = "",
        database_path: str = "",
    ) -> None:
        self._knowledge_repo = knowledge_repo
        self._project_root = project_root
        self._database_path = database_path

    async def build_recent_report(self, limit: int) -> dict[str, object]:
        safe_limit = normalize_report_limit(limit)
        logs = await self._knowledge_repo.list_recent_retrieval_logs(limit=safe_limit)
        return build_retrieval_log_report(
            logs,
            project_root=self._project_root,
            database_path=self._database_path,
            limit=safe_limit,
        )


def normalize_report_limit(limit: int) -> int:
    if limit < 1:
        return 1
    if limit > MAX_RETRIEVAL_REPORT_LIMIT:
        return MAX_RETRIEVAL_REPORT_LIMIT
    return limit


def build_retrieval_log_report(
    logs: list[object],
    *,
    project_root: str = "",
    database_path: str = "",
    limit: int = DEFAULT_RETRIEVAL_REPORT_LIMIT,
) -> dict[str, object]:
    safe_limit = normalize_report_limit(limit)
    no_match_logs = [log for log in logs if getattr(log, "fallback_reason", "")]
    return {
        "status": "ok",
        "metadata": {
            "generated_at": _utc_now(),
            "project_root": str(Path(project_root)) if project_root else "",
            "db": database_path,
            "limit": safe_limit,
            "loaded": len(logs),
        },
        "summary": {
            "total": len(logs),
            "hit_count": len(logs) - len(no_match_logs),
            "no_match_count": len(no_match_logs),
            "no_match_rate": _safe_rate(len(no_match_logs), len(logs)),
        },
        "breakdown": {
            "by_bot_type": _counter_dict(logs, "bot_type"),
            "by_audience": _counter_dict(logs, "audience"),
            "by_retrieval_mode": _counter_dict(logs, "retrieval_mode"),
            "by_fallback_reason": _counter_dict(no_match_logs, "fallback_reason"),
        },
        "trend": {
            "by_date": _build_daily_trend(logs),
        },
        "top_no_match_queries": _top_queries(no_match_logs),
        "recent_logs": [_serialize_log(log) for log in logs],
    }


def _serialize_log(log: object) -> dict[str, object]:
    return {
        "id": getattr(log, "id", 0),
        "created_at": getattr(log, "created_at", ""),
        "bot_type": getattr(log, "bot_type", ""),
        "audience": getattr(log, "audience", ""),
        "query": "",
        "query_hash": getattr(log, "query_hash", ""),
        "query_category": getattr(log, "query_category", ""),
        "retrieval_mode": getattr(log, "retrieval_mode", ""),
        "result_count": getattr(log, "result_count", 0),
        "fallback_reason": getattr(log, "fallback_reason", ""),
        "matched_entry_ids": _loads_json_list(
            getattr(log, "matched_entry_ids_json", "[]")
        ),
        "matched_titles": _loads_json_list(getattr(log, "matched_titles_json", "[]")),
    }


def _loads_json_list(raw: str) -> list[object]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def _counter_dict(logs: list[object], field: str) -> dict[str, int]:
    counter = Counter(str(getattr(log, field, "") or "unknown") for log in logs)
    return dict(sorted(counter.items()))


def _top_queries(logs: list[object]) -> list[dict[str, object]]:
    counter = Counter(
        str(
            getattr(log, "query_category", "") or getattr(log, "query", "") or "unknown"
        )
        for log in logs
    )
    return [
        {"query_category": query, "count": count}
        for query, count in counter.most_common(10)
        if query and query != "unknown"
    ]


def _build_daily_trend(logs: list[object]) -> list[dict[str, object]]:
    daily: dict[str, dict[str, int | str]] = {}
    for log in logs:
        date_key = _extract_created_date(str(getattr(log, "created_at", "")))
        bucket = daily.setdefault(
            date_key,
            {"date": date_key, "total": 0, "hit_count": 0, "no_match_count": 0},
        )
        bucket["total"] = int(bucket["total"]) + 1
        if getattr(log, "fallback_reason", ""):
            bucket["no_match_count"] = int(bucket["no_match_count"]) + 1
        else:
            bucket["hit_count"] = int(bucket["hit_count"]) + 1
    return [
        {
            **bucket,
            "no_match_rate": _safe_rate(
                int(bucket["no_match_count"]),
                int(bucket["total"]),
            ),
        }
        for _, bucket in sorted(daily.items(), reverse=True)
    ]


def _extract_created_date(created_at: str) -> str:
    if len(created_at) >= 10:
        return created_at[:10]
    return "unknown"


def _safe_rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
