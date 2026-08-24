import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const contractPath = path.join(root, "docs", "observability-contract.md");
const pageApiCoveragePath = path.join(root, "docs", "page-api-coverage.md");

const requiredMetrics = [
  "page_api_failure_rate",
  "product_detail_open_success_rate",
  "cart_checkout_start_success_rate",
  "order_create_success_rate",
  "payment_prepare_success_rate",
  "payment_invoke_success_rate",
  "chat_entry_click_rate",
  "manual_handoff_click_rate",
  "session_gate_block_rate",
  "group_registration_submit_success_rate",
];

const requiredEventFields = [
  "trace_id",
  "event_name",
  "page_path",
  "route_source",
  "api_path",
  "api_result",
  "error_code",
  "payment_mode",
  "session_state",
  "duration_ms",
  "network_type",
  "platform",
];

const requiredPrivacyBoundaries = [
  "完整手机号",
  "完整收货地址",
  "完整订单号",
  "完整微信 openid / unionid / session key",
  "完整支付交易号",
  "订单备注全文",
  "真实 AppID、密钥、Token、Cookie、证书或商户私钥",
];

const requiredFallbackTerms = [
  "观测失败不得阻断页面加载",
  "下单",
  "支付唤起",
  "客服发送",
  "客户群登记",
  "不得上传完整用户标识",
  "不能记录支付签名参数",
];

const requiredPlatformBoundaries = [
  "商品、库存、价格、分类、规格真相来自 Platform",
  "订单状态、支付状态、履约状态来自 Platform",
  "客服会话、转人工队列和 AI 回复来自 Platform",
  "会员权益、积分、储值余额、优惠券、配送费、满减和活动价需要先由 Platform 定义 API 契约",
];

function readText(filePath) {
  return fs.readFileSync(filePath, "utf8");
}

function expectIncludes(source, terms, label, failures) {
  for (const term of terms) {
    if (!source.includes(term)) {
      failures.push(`${label} missing required term: ${term}`);
    }
  }
}

const failures = [];
const contract = readText(contractPath);
const pageApiCoverage = readText(pageApiCoveragePath);

expectIncludes(contract, requiredMetrics, "docs/observability-contract.md", failures);
expectIncludes(contract, requiredEventFields, "docs/observability-contract.md", failures);
expectIncludes(contract, requiredPrivacyBoundaries, "docs/observability-contract.md", failures);
expectIncludes(contract, requiredFallbackTerms, "docs/observability-contract.md", failures);
expectIncludes(contract, requiredPlatformBoundaries, "docs/observability-contract.md", failures);

if (!pageApiCoverage.includes("接口缺口先回 Platform 定义 API 契约")) {
  failures.push("docs/page-api-coverage.md must keep Platform-first API gap boundary");
}

if (/发送生产日志|新增埋点 SDK|改变页面运行时代码/.test(contract) && !contract.includes("不新增埋点 SDK")) {
  failures.push("docs/observability-contract.md must keep the first slice as a non-runtime contract");
}

if (failures.length) {
  console.error(failures.map((failure) => `- ${failure}`).join("\n"));
  process.exit(1);
}

console.log(
  `Miniapp observability contract passed: ${requiredMetrics.length} metrics, ${requiredEventFields.length} fields, ${requiredPrivacyBoundaries.length} privacy boundaries.`,
);
