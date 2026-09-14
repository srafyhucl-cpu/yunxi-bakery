// DevTools 审计状态口径：截图属于证据，不是页面断言。
// 环境波动（桌面锁屏、自动化响应超时等）导致截图失败时记为环境阻塞（BLOCKED），
// 既不中断同页其余断言，也不能把缺证据的一轮汇总成 PASS。
const BLOCKED_REASON =
  "DevTools 截图证据不可用（环境或自动化波动）；页面断言已执行，但没有本轮截图证据";

const DEFAULT_SCREENSHOT_ATTEMPTS = 3;
const DEFAULT_SCREENSHOT_RETRY_DELAY_MS = 700;

function resolvePositiveInt(rawValue, fallback) {
  const parsed = Number.parseInt(String(rawValue ?? ""), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function ensureScreenshotRecords(report) {
  if (!Array.isArray(report.screenshots)) {
    report.screenshots = [];
  }
  return report.screenshots;
}

// 截图失败多因自动化响应抖动：先重试，仍失败才判定本轮缺证据。
async function captureScreenshotWithRetry(miniProgram, screenshotPath, options = {}) {
  const attempts = resolvePositiveInt(
    options.attempts ?? process.env.MINIAPP_SCREENSHOT_ATTEMPTS,
    DEFAULT_SCREENSHOT_ATTEMPTS
  );
  const retryDelayMs = resolvePositiveInt(
    options.retryDelayMs ?? process.env.MINIAPP_SCREENSHOT_RETRY_DELAY_MS,
    DEFAULT_SCREENSHOT_RETRY_DELAY_MS
  );
  let lastError;

  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      await miniProgram.screenshot({ path: screenshotPath });
      return { ok: true, attempts: attempt };
    } catch (error) {
      lastError = error;
      if (attempt < attempts) {
        await wait(retryDelayMs);
      }
    }
  }

  return {
    ok: false,
    attempts,
    message: lastError instanceof Error ? lastError.message : String(lastError),
  };
}

async function captureEvidenceScreenshot(miniProgram, report, screenshotPath, options = {}) {
  const shot = await captureScreenshotWithRetry(miniProgram, screenshotPath, options);
  if (shot.ok) {
    ensureScreenshotRecords(report).push({
      path: screenshotPath,
      status: "ok",
      attempts: shot.attempts,
    });
    return true;
  }

  report.screenshotBlocked = true;
  report.blockedReason = report.blockedReason || BLOCKED_REASON;
  ensureScreenshotRecords(report).push({
    path: screenshotPath,
    status: "blocked",
    attempts: shot.attempts,
    message: shot.message,
  });
  return false;
}

// 兼容既有脚本的截图记录格式：screenshots[].status 或 checks[].state 含 screenshot 且 ok=false。
function hasBlockedScreenshot(report) {
  if (report.screenshotBlocked) {
    return true;
  }
  const screenshotRecords = Array.isArray(report.screenshots) ? report.screenshots : [];
  if (
    screenshotRecords.some(
      (item) => item && (item.status === "blocked" || item.status === "failed")
    )
  ) {
    return true;
  }
  const checks = Array.isArray(report.checks) ? report.checks : [];
  return checks.some(
    (item) =>
      item &&
      item.ok === false &&
      /screenshot/i.test(String(item.state || item.name || ""))
  );
}

function finalizeAuditStatus(report) {
  if (Array.isArray(report.errors) && report.errors.length > 0) {
    return "FAIL";
  }
  if (hasBlockedScreenshot(report)) {
    report.screenshotBlocked = true;
    report.blockedReason = report.blockedReason || BLOCKED_REASON;
    return "BLOCKED";
  }
  return "PASS";
}

function exitForAuditStatus(status) {
  if (status === "FAIL") {
    process.exit(1);
  }
  if (status === "BLOCKED") {
    process.exit(2);
  }
}

module.exports = {
  BLOCKED_REASON,
  captureEvidenceScreenshot,
  captureScreenshotWithRetry,
  finalizeAuditStatus,
  exitForAuditStatus,
};
