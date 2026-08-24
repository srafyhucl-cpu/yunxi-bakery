import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const miniappRoot = path.join(root, "miniprogram");
const buttonAuditLatestPath = path.join(root, "reports", "button-audit", "latest.json");
const reportsRoot = path.join(root, "reports", "button-style-audit");

function readText(filePath) {
  return fs.readFileSync(filePath, "utf8");
}

function nowStamp() {
  return new Date()
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\..+$/, "")
    .replace("T", "-");
}

function stripCssComments(source) {
  return source.replace(/\/\*[\s\S]*?\*\//g, "");
}

function getClassTokens(className) {
  return String(className || "")
    .split(/\s+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .filter((item) => !item.includes("{{") && !item.includes("}}"))
    .filter((item) => !["bakery-panel"].includes(item));
}

function getCssForControl(control) {
  const pageWxss = path.join(miniappRoot, `${control.page}.wxss`);
  const appWxss = path.join(miniappRoot, "app.wxss");
  return [appWxss, pageWxss]
    .filter((filePath) => fs.existsSync(filePath))
    .map((filePath) => stripCssComments(readText(filePath)))
    .join("\n");
}

function selectorMentionsToken(selector, token) {
  return new RegExp(`\\.${token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![\\w-])`).test(selector);
}

function getDeclarationsForToken(cssSource, token) {
  const declarations = [];
  const rulePattern = /([^{}]+)\{([^{}]+)\}/g;
  for (const match of cssSource.matchAll(rulePattern)) {
    const selector = match[1];
    if (selector.split(",").some((part) => selectorMentionsToken(part, token))) {
      declarations.push(match[2]);
    }
  }
  return declarations.join("\n");
}

function hasAnyDeclaration(declarations, patterns) {
  return patterns.some((pattern) => pattern.test(declarations));
}

function hasSelector(cssSource, token, selectorPattern) {
  const rulePattern = /([^{}]+)\{([^{}]+)\}/g;
  for (const match of cssSource.matchAll(rulePattern)) {
    const selector = match[1];
    if (selector.split(",").some((part) => selectorMentionsToken(part, token) && selectorPattern.test(part))) {
      return true;
    }
  }
  return false;
}

function inspectControl(control) {
  const cssSource = getCssForControl(control);
  const classTokens = getClassTokens(control.className);
  const declarations = classTokens.map((token) => getDeclarationsForToken(cssSource, token)).join("\n");
  const hasClassRule = classTokens.length > 0 && declarations.trim().length > 0;
  const touchStyleOk = hasAnyDeclaration(declarations, [
    /\bmin-height\s*:/,
    /\bheight\s*:/,
    /\bpadding\s*:/,
    /\bpadding-(top|bottom|left|right)\s*:/,
  ]);
  const textProtectionOk =
    control.label.length <= 8 ||
    hasAnyDeclaration(declarations, [
      /\bmin-width\s*:\s*0\b/,
      /\boverflow\s*:\s*hidden\b/,
      /\btext-overflow\s*:\s*ellipsis\b/,
      /\bwhite-space\s*:\s*nowrap\b/,
      /\bline-height\s*:/,
      /\bflex-wrap\s*:/,
    ]);
  const needsDisabledStyle = Boolean(control.disabled || control.loading);
  const disabledStyleOk =
    !needsDisabledStyle ||
    classTokens.some((token) => hasSelector(cssSource, token, /\[disabled\]|\.is-disabled|\.disabled/));
  const pressFeedbackOk =
    control.tag === "button" ||
    classTokens.some((token) => hasSelector(cssSource, token, /:active|\.is-active|\[data-active=/));

  const failures = [];
  const warnings = [];
  if (!hasClassRule) {
    failures.push("missing-css-class-rule");
  }
  if (!touchStyleOk) {
    failures.push("missing-touch-size-style");
  }
  if (!disabledStyleOk) {
    failures.push("missing-disabled-style");
  }
  if (!textProtectionOk) {
    warnings.push("text-overflow-protection-not-obvious");
  }
  if (!pressFeedbackOk) {
    warnings.push("press-feedback-not-obvious");
  }

  return {
    page: control.page,
    line: control.line,
    kind: control.kind,
    tag: control.tag,
    className: control.className,
    label: control.label,
    handler: control.handler,
    classTokens,
    checks: {
      hasClassRule,
      touchStyleOk,
      textProtectionOk,
      disabledStyleOk,
      pressFeedbackOk,
    },
    failures,
    warnings,
  };
}

function writeReport(report) {
  fs.mkdirSync(reportsRoot, { recursive: true });
  const reportPath = path.join(reportsRoot, `button-style-audit-${nowStamp()}.json`);
  const payload = `${JSON.stringify(report, null, 2)}\n`;
  fs.writeFileSync(reportPath, payload, "utf8");
  fs.writeFileSync(path.join(reportsRoot, "latest.json"), payload, "utf8");
  return reportPath;
}

function main() {
  if (!fs.existsSync(buttonAuditLatestPath)) {
    console.error("Button action audit latest report is missing; run npm run audit:buttons first.");
    process.exit(1);
  }
  const buttonAudit = JSON.parse(readText(buttonAuditLatestPath));
  const controls = buttonAudit.controls || [];
  const inspected = controls.map(inspectControl);
  const failedControls = inspected.filter((item) => item.failures.length > 0);
  const warningControls = inspected.filter((item) => item.warnings.length > 0);
  const report = {
    traceId: "20260621-button-style-static-audit",
    generatedAt: new Date().toISOString(),
    sourceButtonAudit: buttonAuditLatestPath,
    status: failedControls.length ? "fail" : "pass",
    summary: {
      totalControls: inspected.length,
      failedControls: failedControls.length,
      warningControls: warningControls.length,
      failureReasons: failedControls.reduce((acc, item) => {
        for (const reason of item.failures) {
          acc[reason] = (acc[reason] || 0) + 1;
        }
        return acc;
      }, {}),
      warningReasons: warningControls.reduce((acc, item) => {
        for (const reason of item.warnings) {
          acc[reason] = (acc[reason] || 0) + 1;
        }
        return acc;
      }, {}),
    },
    failedControls,
    warningControls,
    controls: inspected,
    notes: [
      "Static style audit checks class coverage, touch-size styling, disabled-state styling, and obvious text/press feedback signals.",
      "It complements but does not replace DevTools/runtime touch target scans or real-device screenshots.",
    ],
  };
  const reportPath = writeReport(report);
  console.log(
    `Miniapp button style audit ${report.status}: ${report.summary.totalControls} controls, ${report.summary.failedControls} failures, ${report.summary.warningControls} warnings.`,
  );
  console.log(`Report: ${reportPath}`);
  if (report.status !== "pass") {
    for (const item of failedControls.slice(0, 20)) {
      console.error(`- ${item.page}:${item.line} ${item.className} ${item.failures.join(",")}`);
    }
    process.exit(1);
  }
}

main();
