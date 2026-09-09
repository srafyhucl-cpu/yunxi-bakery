const automator = require("miniprogram-automator");
const fs = require("node:fs");

const WS_ENDPOINT = process.env.MINIAPP_AUTOMATOR_WS || "ws://127.0.0.1:9420";
const REPORT_PATH = "reports/devtools/same-day-scheduling-audit.json";
const ROUTE = "pages/group-registration/index";
const CUTOFF_HOUR = 17;
const TIME_ZONE = "Asia/Shanghai";

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function getBeijingParts(now = new Date()) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23"
  }).formatToParts(now);
  const values = Object.fromEntries(
    parts
      .filter((part) => ["year", "month", "day", "hour", "minute"].includes(part.type))
      .map((part) => [part.type, Number(part.value)])
  );
  return values;
}

function pad(value) {
  return String(value).padStart(2, "0");
}

function expectedStartDate(now = new Date()) {
  const current = getBeijingParts(now);
  const date = new Date(Date.UTC(current.year, current.month - 1, current.day + (current.hour < CUTOFF_HOUR ? 0 : 1)));
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}`;
}

async function waitForPage(miniProgram) {
  await miniProgram.reLaunch(`/${ROUTE}?campaignId=devtools-scheduling-audit&groupName=审计样本&productName=审计商品`);
  for (let index = 0; index < 10; index += 1) {
    await sleep(300);
    const page = await miniProgram.currentPage();
    if (page.path === ROUTE) {
      return page;
    }
  }
  return miniProgram.currentPage();
}

async function main() {
  const now = new Date();
  const beijing = getBeijingParts(now);
  const beforeCutoff = beijing.hour < CUTOFF_HOUR;
  const report = {
    generatedAt: now.toISOString(),
    businessTimeZone: TIME_ZONE,
    cutoff: "17:00",
    beijingHour: beijing.hour,
    status: "FAIL",
    checks: [],
    errors: []
  };
  let miniProgram;

  try {
    miniProgram = await automator.connect({ wsEndpoint: WS_ENDPOINT });
    const page = await waitForPage(miniProgram);
    if (page.path !== ROUTE) {
      throw new Error(`群内登记页路由错误：${page.path}`);
    }
    const data = await page.data();
    const timePreviews = await page.$$(".time-preview");
    const previewTexts = [];
    for (const preview of timePreviews) {
      previewTexts.push((await preview.text()).trim());
    }
    const expectedDate = expectedStartDate(now);
    const dateStartMatchesRule = data.dateStartValue === expectedDate;
    const sameDayMatchesRule = data.isSameDayRegistration === beforeCutoff;
    const promptVisible = previewTexts.some((text) => text.includes("当天登记由门店客服确认制作与履约安排"));

    report.checks.push({
      page: page.path,
      state: beforeCutoff ? "before-cutoff" : "after-cutoff",
      dateStartValue: data.dateStartValue,
      selectedDateValue: data.selectedDateValue,
      expectedDate,
      isSameDayRegistration: data.isSameDayRegistration,
      expectedSameDayRegistration: beforeCutoff,
      timePreviewTexts: previewTexts,
      promptVisible
    });

    if (!dateStartMatchesRule) {
      report.errors.push(`日期起点不符合北京时间 17:00 截止规则：实际 ${data.dateStartValue}，预期 ${expectedDate}`);
    }
    if (!sameDayMatchesRule) {
      report.errors.push(`当天登记状态不符合当前北京时间：实际 ${data.isSameDayRegistration}，预期 ${beforeCutoff}`);
    }
    if (beforeCutoff && !promptVisible) {
      report.errors.push("17:00 前当天登记没有展示客服确认提示");
    }
    if (!beforeCutoff && promptVisible) {
      report.errors.push("17:00 后仍展示当天登记提示，日期边界未收敛");
    }
    report.status = report.errors.length === 0 ? "PASS" : "FAIL";
  } catch (error) {
    report.errors.push(error instanceof Error ? error.message : String(error));
  } finally {
    if (miniProgram) {
      await miniProgram.disconnect();
    }
    fs.mkdirSync("reports/devtools", { recursive: true });
    fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2), "utf8");
  }

  console.log(`Same-day scheduling audit: ${report.status}`);
  console.log(`Report written to: ${REPORT_PATH}`);
  for (const error of report.errors) {
    console.error(`  x ${error}`);
  }
  if (report.status !== "PASS") {
    process.exit(1);
  }
}

main();
