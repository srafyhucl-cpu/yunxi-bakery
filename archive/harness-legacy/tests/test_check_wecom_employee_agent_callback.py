import json

from app.service.wecom.crypto import decrypt, encrypt, generate_signature
from scripts import check_wecom_employee_agent_callback as callback_check
from scripts.wecom_employee_agent_probe_cases import default_probe_cases


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self) -> dict[str, object]:
        return self._payload


class _FakeAsyncClient:
    requested_payloads: list[dict[str, object] | None] = []
    requested_params: list[dict[str, str] | None] = []

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
        params: dict[str, str] | None = None,
        json: dict[str, object] | None = None,
    ) -> _FakeResponse:
        self.requested_params.append(params)
        self.requested_payloads.append(json)
        assert url.endswith("/api/v1/wecom/intelligent-bot/callback")
        msg_encrypt = str((json or {}).get("encrypt") or "")
        plaintext = decrypt(callback_check.TEST_AES_KEY, msg_encrypt)
        message = __import__("json").loads(plaintext)
        content = message["text"]["content"]
        reply_text = _fake_reply_text(content)
        reply_encrypt = encrypt(
            callback_check.TEST_AES_KEY,
            __import__("json").dumps(
                {
                    "msgtype": "stream",
                    "stream": {
                        "id": message["msgid"],
                        "finish": True,
                        "content": reply_text,
                    },
                },
                ensure_ascii=False,
            ),
            "",
        )
        timestamp = "1783000001"
        nonce = "reply-nonce"
        return _FakeResponse(
            200,
            {
                "encrypt": reply_encrypt,
                "msgsignature": generate_signature(
                    callback_check.TEST_TOKEN,
                    timestamp,
                    nonce,
                    reply_encrypt,
                ),
                "timestamp": timestamp,
                "nonce": nonce,
            },
        )


def test_callback_probe_uses_configured_employee_actor(monkeypatch) -> None:
    monkeypatch.setattr(
        callback_check.settings,
        "WECOM_EMPLOYEE_ALLOWED_USERS",
        "allowed-user,other-user",
    )
    monkeypatch.setattr(
        callback_check.settings,
        "WECOM_EMPLOYEE_ALLOWED_CHATS",
        "allowed-chat",
    )
    monkeypatch.setattr(callback_check.settings, "WECOM_STAFF_ID", "")
    monkeypatch.setattr(
        callback_check.settings,
        "WECOM_KF_SERVICER_USERID",
        "service-user",
    )
    monkeypatch.setattr(callback_check.settings, "WECOM_EMPLOYEE_CORP_ID", "")
    monkeypatch.setattr(callback_check.settings, "WECOM_CORP_ID", "corp-id")

    message = callback_check.build_callback_message(
        default_probe_cases(__import__("datetime").date.today())[0],
        1,
    )

    assert message["from"] == {"userid": "allowed-user"}
    assert message["chattype"] == "group"
    assert message["chatid"] == "allowed-chat"
    assert message["corpid"] == "corp-id"


def test_callback_probe_uses_single_chat_without_chat_allowlist(monkeypatch) -> None:
    monkeypatch.setattr(
        callback_check.settings, "WECOM_EMPLOYEE_ALLOWED_USERS", "allowed-user"
    )
    monkeypatch.setattr(callback_check.settings, "WECOM_EMPLOYEE_ALLOWED_CHATS", "")

    message = callback_check.build_callback_message(
        default_probe_cases(__import__("datetime").date.today())[0],
        1,
    )

    assert message["chattype"] == "single"
    assert "chatid" not in message


def test_parse_base_url_rejects_path() -> None:
    try:
        callback_check.parse_base_url("https://yunxifood.cn/ready")
    except ValueError as exc:
        assert "根地址" in str(exc)
    else:
        raise AssertionError("base url with path should be rejected")


async def test_run_callback_checks_covers_employee_queries(monkeypatch) -> None:
    _FakeAsyncClient.requested_payloads = []
    _FakeAsyncClient.requested_params = []
    monkeypatch.setattr(callback_check.httpx, "AsyncClient", _FakeAsyncClient)

    results = await callback_check.run_callback_checks(
        "https://yunxifood.cn",
        callback_check.CallbackCredentials(
            token=callback_check.TEST_TOKEN,
            encoding_aes_key=callback_check.TEST_AES_KEY,
        ),
    )
    report = callback_check.build_json_report("https://yunxifood.cn", results)
    serialized = json.dumps(report, ensure_ascii=False)
    expected_cases = default_probe_cases(__import__("datetime").date.today())

    assert report["status"] == "passed"
    assert report["total"] == len(expected_cases)
    assert report["failed"] == 0
    assert {result.name for result in results} == {case.name for case in expected_cases}
    assert callback_check.TEST_TOKEN not in serialized
    assert callback_check.TEST_AES_KEY not in serialized
    assert "encrypt" not in serialized
    assert all(result.reply_valid for result in results)
    assert all(result.privacy_safe for result in results)


def test_evaluate_reply_rejects_privacy_leak() -> None:
    result = callback_check.evaluate_reply(
        callback_check.CallbackProbe("privacy", "查订单"),
        200,
        {
            "msgtype": "stream",
            "stream": {
                "id": "msg",
                "finish": True,
                "content": "手机号 13812345678，完整订单号 E202607031234567890",
            },
        },
        5,
    )

    assert result.passed is False
    assert result.reply_valid is True
    assert result.privacy_safe is False
    assert "privacy" in result.detail


def test_evaluate_reply_rejects_buyer_id_hint() -> None:
    result = callback_check.evaluate_reply(
        callback_check.CallbackProbe("privacy", "现在有哪些待人工"),
        200,
        {
            "msgtype": "stream",
            "stream": {
                "id": "msg",
                "finish": True,
                "content": "当前有5笔待人工订单，来自同一买家（ID: wmLg...ismA）。",
            },
        },
        5,
    )

    assert result.passed is False
    assert result.privacy_safe is False


def test_evaluate_reply_rejects_full_uuid() -> None:
    result = callback_check.evaluate_reply(
        callback_check.CallbackProbe("privacy", "现在有哪些待人工"),
        200,
        {
            "msgtype": "stream",
            "stream": {
                "id": "msg",
                "finish": True,
                "content": "da8f723e-d755-4868-8c48-bf9813a77f40｜转人工",
            },
        },
        5,
    )

    assert result.passed is False
    assert result.privacy_safe is False


def test_evaluate_reply_rejects_delivery_order_tail_detour() -> None:
    result = callback_check.evaluate_reply(
        callback_check.CallbackProbe(
            "delivery-knowledge",
            "明天能配送吗",
            required_any_terms=("配送",),
            forbidden_terms=("订单尾号", "订单状态"),
        ),
        200,
        {
            "msgtype": "stream",
            "stream": {
                "id": "msg",
                "finish": True,
                "content": "请提供订单尾号，我帮您查一下配送安排。如需确认，也可登录后台查看订单状态。",
            },
        },
        5,
    )

    assert result.passed is False
    assert result.semantic_safe is False
    assert "semantic" in result.detail


def test_evaluate_reply_requires_all_semantic_terms() -> None:
    probe = callback_check.CallbackProbe(
        "stock",
        "帮我看看伯牙绝弦库存",
        required_all_terms=("库存", "72"),
    )

    missing_number = callback_check.evaluate_reply(
        probe,
        200,
        {
            "msgtype": "stream",
            "stream": {
                "id": "msg",
                "finish": True,
                "content": "伯牙绝弦库存请以小程序为准。",
            },
        },
        5,
    )
    matched = callback_check.evaluate_reply(
        probe,
        200,
        {
            "msgtype": "stream",
            "stream": {
                "id": "msg",
                "finish": True,
                "content": "伯牙绝弦库存显示72份。",
            },
        },
        5,
    )

    assert missing_number.passed is False
    assert matched.passed is True


def test_evaluate_reply_accepts_handoff_when_business_fact_is_uncertain() -> None:
    result = callback_check.evaluate_reply(
        callback_check.CallbackProbe(
            "uncertain-business-fact",
            "退款怎么处理",
            required_all_terms=("退款", "订单状态"),
            allow_handoff=True,
        ),
        200,
        {
            "msgtype": "stream",
            "stream": {
                "id": "msg",
                "finish": True,
                "content": "当前信息无法可靠确认，我先为您转人工核对，请稍候。",
            },
        },
        5,
    )

    assert result.passed is True
    assert result.semantic_safe is True


def test_evaluate_reply_accepts_handoff_for_callback_error_fallback() -> None:
    result = callback_check.evaluate_reply(
        callback_check.CallbackProbe("callback-error", "查询商品库存"),
        200,
        {
            "msgtype": "stream",
            "stream": {
                "id": "msg",
                "finish": True,
                "content": "当前信息无法可靠确认，我先为您转人工核对，请稍候。",
            },
        },
        5,
    )

    assert result.passed is True


def test_evaluate_reply_accepts_alternative_required_all_groups() -> None:
    probe = callback_check.CallbackProbe(
        "no-stock-product",
        "招牌牛奶吐司还有吗",
        required_all_term_groups=(
            ("库存", "0", "暂无可售库存", "不要承诺有货", "替代款"),
            ("未找到匹配商品", "未命中结果", "缺货结论"),
        ),
    )

    zero_stock = callback_check.evaluate_reply(
        probe,
        200,
        {
            "msgtype": "stream",
            "stream": {
                "id": "msg",
                "finish": True,
                "content": "招牌牛奶吐司库存 0，暂无可售库存，先不要承诺有货；可推荐替代款。",
            },
        },
        5,
    )
    missing_product = callback_check.evaluate_reply(
        probe,
        200,
        {
            "msgtype": "stream",
            "stream": {
                "id": "msg",
                "finish": True,
                "content": "未找到匹配商品。请换商品名再查，不要把未命中结果当作缺货结论。",
            },
        },
        5,
    )
    unsafe_reply = callback_check.evaluate_reply(
        probe,
        200,
        {
            "msgtype": "stream",
            "stream": {
                "id": "msg",
                "finish": True,
                "content": "暂时无货，可以推荐替代款。",
            },
        },
        5,
    )

    assert zero_stock.passed is True
    assert missing_product.passed is True
    assert unsafe_reply.passed is False


def test_evaluate_reply_rejects_revenue_empty_detour() -> None:
    probe = callback_check.CallbackProbe(
        "today-revenue-summary",
        "今天营业额多少",
        required_any_terms=("元", "营业额", "销售额"),
        forbidden_terms=("未找到", "暂无数据", "后台订单页核对"),
    )

    result = callback_check.evaluate_reply(
        probe,
        200,
        {
            "msgtype": "stream",
            "stream": {
                "id": "msg",
                "finish": True,
                "content": "未找到今日营业额数据，请进入后台订单页核对日期范围。",
            },
        },
        5,
    )

    assert result.passed is False
    assert result.semantic_safe is False


def test_evaluate_reply_rejects_wrong_fulfillment_pressure() -> None:
    probe = callback_check.CallbackProbe(
        "casual-fulfillment-pressure",
        "今天发货压力大不大",
        required_all_terms=("发货压力",),
        required_any_terms=("偏高", "中等", "低"),
        forbidden_terms=("压力不大",),
    )

    result = callback_check.evaluate_reply(
        probe,
        200,
        {
            "msgtype": "stream",
            "stream": {
                "id": "msg",
                "finish": True,
                "content": "今天发货压力不大，目前仅5单待处理。",
            },
        },
        5,
    )

    assert result.passed is False
    assert result.semantic_safe is False


def test_evaluate_reply_rejects_compressed_fulfillment_list() -> None:
    probe = callback_check.CallbackProbe(
        "casual-fulfillment-pressure",
        "今天发货压力大不大",
        required_all_terms=("发货压力", "尾号", "约送", "物流"),
        required_any_terms=("偏高", "中等", "低"),
    )

    result = callback_check.evaluate_reply(
        probe,
        200,
        {
            "msgtype": "stream",
            "stream": {
                "id": "msg",
                "finish": True,
                "content": "发货压力偏高，履约风险已汇总。",
            },
        },
        5,
    )

    assert result.passed is False
    assert result.semantic_safe is False


def test_evaluate_reply_rejects_compressed_pending_list() -> None:
    probe = callback_check.CallbackProbe(
        "pending-shipment-list",
        "还有哪些没发货",
        required_all_terms=("尾号", "待发货", "物流"),
    )

    result = callback_check.evaluate_reply(
        probe,
        200,
        {
            "msgtype": "stream",
            "stream": {
                "id": "msg",
                "finish": True,
                "content": "当前待发货订单已汇总。",
            },
        },
        5,
    )

    assert result.passed is False
    assert result.semantic_safe is False


def test_evaluate_reply_rejects_product_knowledge_miss() -> None:
    probe = callback_check.CallbackProbe(
        "product-stock-recommend-replacement",
        "伯牙绝弦库存不够怎么推荐替代",
        required_all_terms=("库存", "72"),
        required_any_terms=("推荐", "替代", "客户", "回复"),
        forbidden_terms=("未找到匹配知识",),
    )

    result = callback_check.evaluate_reply(
        probe,
        200,
        {
            "msgtype": "stream",
            "stream": {
                "id": "msg",
                "finish": True,
                "content": "伯牙绝弦｜258.00元｜库存 72｜生日蛋糕\n未找到匹配知识。",
            },
        },
        5,
    )

    assert result.passed is False
    assert result.semantic_safe is False


def test_evaluate_reply_rejects_high_stock_low_stock_hint() -> None:
    probe = callback_check.CallbackProbe(
        "casual-inventory",
        "伯牙绝弦还有吗",
        required_all_terms=("库存", "72"),
        forbidden_terms=("低库存",),
    )

    result = callback_check.evaluate_reply(
        probe,
        200,
        {
            "msgtype": "stream",
            "stream": {
                "id": "msg",
                "finish": True,
                "content": "伯牙绝弦当前库存72，库存以小程序为准，低库存建议尽快确认。",
            },
        },
        5,
    )

    assert result.passed is False
    assert result.semantic_safe is False


def test_evaluate_reply_rejects_no_stock_replacement_hallucination() -> None:
    probe = callback_check.CallbackProbe(
        "no-stock-product",
        "招牌牛奶吐司还有吗",
        required_all_terms=("库存", "0", "暂无可售库存", "不要承诺有货"),
        forbidden_terms=(
            "比如",
            "北海道吐司",
            "北海道牛奶吐司",
            "经典白吐司",
            "原味手撕包",
        ),
    )

    result = callback_check.evaluate_reply(
        probe,
        200,
        {
            "msgtype": "stream",
            "stream": {
                "id": "msg",
                "finish": True,
                "content": (
                    "招牌牛奶吐司库存为0，暂时无货。"
                    "建议推荐同价位替代款，如北海道吐司或原味手撕包。"
                ),
            },
        },
        5,
    )

    assert result.passed is False
    assert result.semantic_safe is False


def test_evaluate_reply_rejects_missing_product_guardrail_loss() -> None:
    probe = callback_check.CallbackProbe(
        "missing-product",
        "不存在的月球蛋糕还有吗",
        required_all_terms=("未找到匹配商品", "未命中结果", "缺货结论"),
    )

    result = callback_check.evaluate_reply(
        probe,
        200,
        {
            "msgtype": "stream",
            "stream": {
                "id": "msg",
                "finish": True,
                "content": "未找到“月球蛋糕”商品。请换其他名称或关键词再查。",
            },
        },
        5,
    )

    assert result.passed is False
    assert result.semantic_safe is False


def test_evaluate_reply_rejects_empty_order_generic_detour() -> None:
    probe = callback_check.CallbackProbe(
        "evening-pending-orders",
        "晚上还有哪些待处理订单",
        required_any_terms=("待处理", "约送", "晚上", "待发货", "待收货"),
        forbidden_terms=("换商品名", "时间范围再查"),
    )

    result = callback_check.evaluate_reply(
        probe,
        200,
        {
            "msgtype": "stream",
            "stream": {
                "id": "msg",
                "finish": True,
                "content": "没有查到待处理订单。建议换商品名、状态或时间范围再查。",
            },
        },
        5,
    )

    assert result.passed is False
    assert result.semantic_safe is False


def test_evaluate_reply_accepts_explicit_controlled_empty_result() -> None:
    probe = callback_check.CallbackProbe(
        "p2c-today-wait-buyer-confirm-list",
        "今天待收货订单有哪些",
        required_all_terms=("尾号", "待收货"),
        forbidden_terms=("完整订单号", "手机号", "完整地址"),
        allow_empty_result=True,
    )

    result = callback_check.evaluate_reply(
        probe,
        200,
        {
            "msgtype": "stream",
            "stream": {
                "id": "msg",
                "finish": True,
                "content": "今天待收货订单有哪些：没有查到下单日期 2026-07-10、待收货的订单。",
            },
        },
        5,
    )

    assert result.passed is True
    assert result.semantic_safe is True


def test_evaluate_reply_accepts_wait_seller_send_empty_result() -> None:
    probe = callback_check.CallbackProbe(
        "p2c-today-wait-seller-send-list",
        "今天待发货订单有哪些",
        required_all_terms=("尾号", "待发货"),
        forbidden_terms=("完整订单号", "手机号", "完整地址"),
        allow_empty_result=True,
    )

    result = callback_check.evaluate_reply(
        probe,
        200,
        {
            "msgtype": "stream",
            "stream": {
                "id": "msg",
                "finish": True,
                "content": "今天待发货订单有哪些：没有查到下单日期 2026-07-10、待发货的订单。",
            },
        },
        5,
    )

    assert result.passed is True
    assert result.semantic_safe is True


def test_evaluate_reply_rejects_markdown_decorations() -> None:
    result = callback_check.evaluate_reply(
        callback_check.CallbackProbe("plain-text", "今天哪个商品卖得多"),
        200,
        {
            "msgtype": "stream",
            "stream": {
                "id": "msg",
                "finish": True,
                "content": "今日销量第一：**巧克力樱桃炸弹**。",
            },
        },
        5,
    )

    assert result.passed is False
    assert result.semantic_safe is False
    assert "semantic" in result.detail


def test_evaluate_reply_rejects_markdown_blockquote() -> None:
    result = callback_check.evaluate_reply(
        callback_check.CallbackProbe("markdown-blockquote", "今天有退款订单吗"),
        200,
        {
            "msgtype": "stream",
            "stream": {
                "id": "msg",
                "finish": True,
                "content": "可复制回复：\n> 亲，已收到。",
            },
        },
        1,
    )

    assert result.passed is False
    assert result.semantic_safe is False
    assert "semantic" in result.detail


def test_evaluate_reply_rejects_ump_marker_in_handoff_summary() -> None:
    result = callback_check.evaluate_reply(
        callback_check.CallbackProbe(
            "handoff-pending",
            "现在有哪些待人工",
            required_any_terms=("待人工", "转人工"),
            forbidden_terms=("UMP", "type=card", "%E5%"),
        ),
        200,
        {
            "msgtype": "stream",
            "stream": {
                "id": "msg",
                "finish": True,
                "content": (
                    "工单尾号 77f40｜转人工｜摘要：AI：好的 "
                    "[UMP: type=card&id=1&title=%E5%B0%8F]"
                ),
            },
        },
        5,
    )

    assert result.passed is False
    assert result.semantic_safe is False
    assert "semantic" in result.detail


def test_evaluate_reply_rejects_raw_offline_review_skip_marker() -> None:
    result = callback_check.evaluate_reply(
        callback_check.CallbackProbe(
            "offline-review-summary",
            "昨晚离线复盘结果",
            required_any_terms=("离线复盘", "复盘"),
            forbidden_terms=("outside_night_window", "skippedReason"),
        ),
        200,
        {
            "msgtype": "stream",
            "stream": {
                "id": "msg",
                "finish": True,
                "content": (
                    "最近一轮离线复盘未执行：outside_night_window。\n"
                    "下一步：如果 skippedReason 不为空，先确认夜间窗口。"
                ),
            },
        },
        5,
    )

    assert result.passed is False
    assert result.semantic_safe is False
    assert "semantic" in result.detail


def test_evaluate_reply_rejects_generic_customer_lookup_empty_text() -> None:
    result = callback_check.evaluate_reply(
        callback_check.CallbackProbe(
            "customer-lookup",
            "查一下张三地址线索",
            required_any_terms=("客户", "地址", "线索"),
            forbidden_terms=("未找到匹配客户地址",),
        ),
        200,
        {
            "msgtype": "stream",
            "stream": {
                "id": "msg",
                "finish": True,
                "content": "未找到匹配客户地址。",
            },
        },
        5,
    )

    assert result.passed is False
    assert result.semantic_safe is False
    assert "semantic" in result.detail


def test_evaluate_reply_rejects_group_campaign_retry_detour() -> None:
    result = callback_check.evaluate_reply(
        callback_check.CallbackProbe(
            "group-campaign-summary",
            "汇总 campaignId:abc123",
            required_any_terms=("客户群", "campaignId", "活动批次"),
            forbidden_terms=("请稍后重试", "活动批次不存在"),
        ),
        200,
        {
            "msgtype": "stream",
            "stream": {
                "id": "msg",
                "finish": True,
                "content": "活动批次不存在\n下一步：请稍后重试，或进入后台人工查询。",
            },
        },
        5,
    )

    assert result.passed is False
    assert result.semantic_safe is False
    assert "semantic" in result.detail


async def test_main_requires_callback_credentials(monkeypatch, capsys) -> None:
    monkeypatch.setattr(callback_check, "resolve_callback_credentials", lambda: None)

    exit_code = await callback_check.main(["--json"])

    assert exit_code == 2
    assert "WECOM_INTELLIGENT_BOT_TOKEN" in capsys.readouterr().err


async def test_main_json_output_can_be_written_to_file(monkeypatch, tmp_path) -> None:
    async def fake_run_callback_checks(base_url, credentials):
        return [
            callback_check.CallbackProbeResult(
                name="ok",
                query="今天一共多少订单",
                status_code=200,
                passed=True,
                reply_valid=True,
                privacy_safe=True,
                semantic_safe=True,
                elapsed_ms=1,
                content_preview="员工回复",
            )
        ]

    monkeypatch.setattr(
        callback_check,
        "resolve_callback_credentials",
        lambda: callback_check.CallbackCredentials("token", "aes"),
    )
    monkeypatch.setattr(callback_check, "run_callback_checks", fake_run_callback_checks)
    report_path = tmp_path / "reports" / "employee-agent-callback.json"

    exit_code = await callback_check.main(["--json", "--output", str(report_path)])

    assert exit_code == 0
    assert report_path.read_bytes().startswith(callback_check.UTF8_BOM)
    payload = json.loads(report_path.read_text(encoding="utf-8-sig"))
    assert payload["status"] == "passed"
    assert payload["results"][0]["content_preview"] == "员工回复"


def _fake_reply_text(content: str) -> str:
    if "招牌牛奶吐司" in content:
        return (
            "招牌牛奶吐司｜15.00元｜库存 0｜甜品和面包\n"
            "下一步：当前命中商品暂无可售库存，先不要承诺有货；"
            "可推荐同品类或相近价位替代款。"
        )
    if "月球蛋糕" in content:
        return (
            "未找到匹配商品\n"
            "下一步：请换商品名、品类或关键词再查；不要把未命中结果当作缺货结论。"
        )
    if "伯牙绝弦" in content and ("替代" in content or "怎么跟客户说" in content):
        return "伯牙绝弦当前库存72，建议给客户回复可推荐替代款。"
    if "怎么跟客户说" in content:
        return "当前待发货订单已汇总，并给出可复制给客户的回复。"
    if "怎么回复客户" in content and ("退款" in content or "售后" in content):
        return "退款订单已汇总，并给出售后回复客户的话术。"
    if "要盯" in content or "需要注意" in content or "待办" in content:
        return (
            "今日订单优先级和发货压力已汇总，包含待处理、履约风险、退款和无物流事项。"
        )
    if "快超时" in content or "发货压力" in content or "履约压力" in content:
        return (
            "发货压力：偏高。\n1. 尾号 000001｜待发货｜约送 2026-07-04 16:00｜暂无物流"
        )
    if "明天" in content and "预定" in content:
        return "明天待处理预定订单已汇总，包含约送时间和待发货状态。"
    if "待收货订单" in content:
        return "今天待收货订单有哪些：没有查到下单日期 2026-07-10、待收货的订单。"
    if "待发货订单" in content:
        return "1. 尾号 000001｜待发货｜约送 2026-07-04 16:00｜暂无物流"
    if "上午" in content and "待处理" in content:
        return "上午待处理订单已汇总，包含约送时间和待发货状态。"
    if "下午" in content and "待处理" in content:
        return "下午待处理订单已汇总，包含约送时间和待收货状态。"
    if "晚上" in content and "待处理" in content:
        return "晚上待处理订单已汇总，包含约送时间和待发货状态。"
    if "明天" in content and "待处理" in content:
        return "明天待处理订单已汇总，包含约送时间和待发货状态。"
    if "后天" in content and "待处理" in content:
        return "后天待处理订单已汇总，包含约送时间和待发货状态。"
    if "周末" in content and "待处理" in content:
        return "周末待处理订单已汇总，包含约送时间和待发货状态。"
    if "下周一" in content and "待处理" in content:
        return "下周一待处理订单已汇总，包含约送时间和待发货状态。"
    if "没发货" in content or "没处理" in content:
        return "1. 尾号 000001｜待发货｜约送 2026-07-04 16:00｜暂无物流"
    if "物流" in content:
        return "1. 尾号 000001｜待发货｜约送 2026-07-04 16:00｜暂无物流"
    if "哪个商品" in content or "卖爆" in content:
        return "今日销量排行已汇总。"
    if "营业额" in content or "销售额" in content:
        return "销售额已汇总，共206.50元。"
    if "退款" in content or "退单" in content or "售后订单" in content:
        return "退款订单已汇总，共1单，合计88.00元。"
    if "伯牙绝弦" in content and ("库存" in content or "还有吗" in content):
        return "伯牙绝弦当前库存72，售价258元。"
    if "库存" in content or "还有吗" in content:
        return "商品库存已汇总。"
    if "配送" in content:
        return "配送规则请按后台知识库确认。"
    if "同步失败" in content:
        return "Webhook 同步失败已汇总，请先看观察台失败明细。"
    if "异常" in content or "稳不稳" in content:
        return "系统状态已汇总。"
    if "待人工" in content or "人接" in content:
        return "当前待人工事项已汇总。"
    if "地址线索" in content:
        return "客户地址线索已汇总。"
    if "客户线索" in content:
        return "客户线索已汇总。"
    if "还买过什么" in content:
        return "该客户历史订单已汇总，展示买过的商品。"
    if "campaign" in content:
        return "群活动 campaign 已汇总。"
    if "离线复盘" in content:
        return "昨晚离线复盘结果已汇总。"
    return "今日订单共1单。"
