import json

from scripts import wecom_intelligent_bot_smoke as smoke


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self) -> dict[str, object]:
        return self._payload


class _FakeAsyncClient:
    requested_headers: list[dict[str, str] | None] = []
    requested_urls: list[str] = []

    def __init__(self, timeout: int) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, object] | None = None,
    ) -> _FakeResponse:
        self.requested_urls.append(url)
        self.requested_headers.append(headers)
        if headers != {"X-Yunxi-Bot-Key": "expected-secret"}:
            return _FakeResponse(401, {"detail": "invalid"})
        if url.endswith("/tools/group-campaign-summary"):
            return _FakeResponse(
                200,
                {
                    "ok": False,
                    "tool": "group_campaign_summary",
                    "summary": "活动批次不存在",
                    "result": "活动批次不存在",
                    "resultText": "活动批次不存在",
                },
            )
        tool = url.rsplit("/", 1)[-1].replace("-", "_")
        return _FakeResponse(
            200,
            {
                "ok": True,
                "tool": tool,
                "summary": "ready",
                "result": "ready",
                "resultText": "ready",
            },
        )


def test_parse_base_url_rejects_path() -> None:
    try:
        smoke.parse_base_url("https://yunxifood.cn/ready")
    except ValueError as exc:
        assert "根地址" in str(exc)
    else:
        raise AssertionError("base url with path should be rejected")


async def test_run_smoke_checks_tools_and_auth_without_leaking_key(
    monkeypatch,
) -> None:
    _FakeAsyncClient.requested_headers = []
    _FakeAsyncClient.requested_urls = []
    monkeypatch.setattr(smoke.httpx, "AsyncClient", _FakeAsyncClient)

    results = await smoke.run_smoke("https://yunxifood.cn", "expected-secret")
    report = smoke.build_json_report("https://yunxifood.cn", results)
    serialized = json.dumps(report, ensure_ascii=False)

    assert all(result.passed for result in results)
    assert report["status"] == "passed"
    assert all(
        result.result_present
        for result in results
        if not result.name.endswith("-rejected")
    )
    assert "expected-secret" not in serialized
    assert "X-Yunxi-Bot-Key" not in serialized
    assert any(result.name == "query-key-rejected" for result in results)
    query_urls = [url for url in _FakeAsyncClient.requested_urls if "api_key=" in url]
    assert query_urls == [
        "https://yunxifood.cn/api/v1/wecom/intelligent-bot/tools/order-lookup?api_key=wrong-secret"
    ]


async def test_main_requires_plugin_key(monkeypatch, capsys) -> None:
    monkeypatch.setattr(smoke, "resolve_plugin_key", lambda: "")

    exit_code = await smoke.main(["--json"])

    assert exit_code == 2
    assert "WECOM_BOT_PLUGIN_API_KEY" in capsys.readouterr().err


async def test_request_probe_fails_when_readable_result_is_missing() -> None:
    class MissingResultClient:
        async def post(
            self,
            url: str,
            *,
            headers: dict[str, str] | None = None,
            json: dict[str, object] | None = None,
        ) -> _FakeResponse:
            return _FakeResponse(200, {"ok": True, "tool": "product_lookup"})

    result = await smoke.request_probe(
        MissingResultClient(),
        "https://yunxifood.cn",
        smoke.ToolProbe(
            "product-lookup",
            "/api/v1/wecom/intelligent-bot/tools/product-lookup",
            {"query": "蛋糕"},
        ),
        "expected-secret",
    )

    assert result.passed is False
    assert result.result_present is False
    assert result.detail == "missing result/resultText"


async def test_main_json_output_can_be_written_to_file(
    monkeypatch,
    tmp_path,
) -> None:
    async def fake_run_smoke(base_url: str, plugin_key: str):
        return [
            smoke.ProbeResult(
                "ok",
                "/ok",
                200,
                True,
                True,
                "ok",
                "ready",
                1,
                True,
            )
        ]

    monkeypatch.setattr(smoke, "resolve_plugin_key", lambda: "expected-secret")
    monkeypatch.setattr(smoke, "run_smoke", fake_run_smoke)
    report_path = tmp_path / "reports" / "wecom-smoke.json"

    exit_code = await smoke.main(["--json", "--output", str(report_path)])

    assert exit_code == 0
    assert report_path.read_bytes().startswith(smoke.UTF8_BOM)
    payload = json.loads(report_path.read_text(encoding="utf-8-sig"))
    assert payload["status"] == "passed"
    assert payload["results"][0]["name"] == "ok"
    assert payload["results"][0]["result_present"] is True
