import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const miniappRoot = path.join(root, "miniprogram");
const reportsRoot = path.join(root, "reports", "button-audit");
const appJsonPath = path.join(miniappRoot, "app.json");
const eventAttributes = ["bindtap", "catchtap", "bind:tap", "catch:tap"];

function readText(filePath) {
  return fs.readFileSync(filePath, "utf8");
}

function getLine(source, index) {
  return source.slice(0, index).split(/\r?\n/).length;
}

function getAttribute(tag, name) {
  const pattern = new RegExp(`${name}="([^"]*)"`);
  return tag.match(pattern)?.[1] || "";
}

function getEventHandler(tag) {
  for (const attribute of eventAttributes) {
    const handler = getAttribute(tag, attribute);
    if (handler) {
      return { attribute, handler };
    }
  }
  return { attribute: "", handler: "" };
}

function getDataAttributes(tag) {
  return Object.fromEntries(
    Array.from(tag.matchAll(/\s(data-[\w-]+)="([^"]*)"/g)).map((match) => [match[1], match[2]]),
  );
}

function normalizeText(value) {
  return value.replace(/\s+/g, " ").trim();
}

function stripWxmlToLabel(source) {
  return normalizeText(
    source
      .replace(/<[^>]+>/g, " ")
      .replace(/\{\{([^}]+)\}\}/g, "{$1}")
      .replace(/&nbsp;/g, " "),
  ).slice(0, 120);
}

function getControlLabel(elementSource, tag) {
  const visibleLabel = stripWxmlToLabel(elementSource);
  if (visibleLabel) {
    return {
      label: visibleLabel,
      labelSource: "visible",
    };
  }
  const ariaLabel = getAttribute(tag, "aria-label");
  if (ariaLabel) {
    return {
      label: ariaLabel,
      labelSource: "aria-label",
    };
  }
  return {
    label: "",
    labelSource: "missing",
  };
}

function findElementEnd(source, tagName, startIndex, openTagEndIndex) {
  const singleTags = new Set(["input", "image"]);
  if (source[openTagEndIndex - 1] === "/" || singleTags.has(tagName)) {
    return openTagEndIndex;
  }
  const tagPattern = new RegExp(`<\\s*(/?)${tagName}\\b[^>]*>`, "g");
  tagPattern.lastIndex = openTagEndIndex;
  let depth = 1;
  for (const match of source.matchAll(tagPattern)) {
    const isClosing = Boolean(match[1]);
    depth += isClosing ? -1 : 1;
    if (depth === 0) {
      return match.index + match[0].length;
    }
  }
  return Math.min(source.length, startIndex + 500);
}

function extractPageMethodBodies(source) {
  const pageBody = source.match(/Page(?:<[^>]+>)?\s*\(\s*\{([\s\S]*)\}\s*\)\s*;?\s*$/);
  const target = pageBody ? pageBody[1] : source;
  const bodies = new Map();
  const methodPattern = /^\s*(?:async\s+)?([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{/gm;
  for (const match of target.matchAll(methodPattern)) {
    const name = match[1];
    if (["if", "for", "while", "switch", "catch", "function"].includes(name)) {
      continue;
    }
    const openBraceIndex = match.index + match[0].lastIndexOf("{");
    let depth = 0;
    let endIndex = -1;
    for (let index = openBraceIndex; index < target.length; index += 1) {
      const char = target[index];
      if (char === "{") {
        depth += 1;
      } else if (char === "}") {
        depth -= 1;
        if (depth === 0) {
          endIndex = index;
          break;
        }
      }
    }
    if (endIndex !== -1) {
      bodies.set(name, target.slice(openBraceIndex + 1, endIndex));
    }
  }
  return bodies;
}

function getMethodBody(methodBodies, handler, visited = new Set()) {
  if (!handler || visited.has(handler)) {
    return "";
  }
  visited.add(handler);
  const body = methodBodies.get(handler) || "";
  const localCalls = Array.from(body.matchAll(/\b(?:this\.)?([A-Za-z_$][\w$]*)\s*\(/g))
    .map((match) => match[1])
    .filter((name) => methodBodies.has(name));
  return [body, ...localCalls.map((name) => getMethodBody(methodBodies, name, visited))].join("\n");
}

function classifyEffects(body) {
  const effects = new Set();
  if (
    /\bwx\.(navigateTo|redirectTo|switchTab|reLaunch|navigateBack)\s*\(/.test(body) ||
    /\b(goBackOrHome|navigateByLink)\s*\(/.test(body)
  ) {
    effects.add("navigation");
  }
  if (/\bwx\.(showToast|showModal|showLoading|hideLoading|makePhoneCall|setClipboardData)\s*\(/.test(body)) {
    effects.add("feedback");
  }
  if (/\b(this\.)?setData\s*\(/.test(body)) {
    effects.add("state");
  }
  if (/\b(createOrder|listOrders|getOrder|cancelOrder|payOrderById|sendChatMessage|requestHumanTransfer|saveAddress|deleteAddress|setDefaultAddress|ensureMiniappSession|getChatPayload)\s*\(/.test(body)) {
    effects.add("api-or-service");
  }
  if (/\b(addCartItem|clearCartItems|setSelectedAddress|wx\.setStorageSync|wx\.removeStorageSync)\s*\(/.test(body)) {
    effects.add("local-state");
  }
  return Array.from(effects);
}

function getRouteReferences(body) {
  const routeKeys = Array.from(body.matchAll(/ROUTES\.([A-Za-z_$][\w$]*)/g)).map((match) => match[1]);
  const literalPages = Array.from(body.matchAll(/["'`]\/?pages\/[^"'`?]+/g)).map((match) => match[0].replace(/^["'`]/, ""));
  return Array.from(new Set([...routeKeys.map((key) => `ROUTES.${key}`), ...literalPages]));
}

function extractActionTargets(wxmlSource, methodBodies, pagePath) {
  const controls = [];
  const tagPattern = /<\s*([A-Za-z][\w-]*)([^>]*)>/g;
  for (const match of wxmlSource.matchAll(tagPattern)) {
    const tagName = match[1];
    const tag = match[0];
    const { attribute, handler } = getEventHandler(tag);
    const openType = getAttribute(tag, "open-type");
    const formType = getAttribute(tag, "form-type");
    if (tagName !== "button" && !handler) {
      continue;
    }
    const openTagEndIndex = match.index + tag.length;
    const elementEndIndex = findElementEnd(wxmlSource, tagName, match.index, openTagEndIndex);
    const elementSource = wxmlSource.slice(match.index, elementEndIndex);
    const body = getMethodBody(methodBodies, handler);
    const { label, labelSource } = getControlLabel(elementSource, tag);
    controls.push({
      page: pagePath,
      line: getLine(wxmlSource, match.index),
      tag: tagName,
      kind: tagName === "button" ? "button" : "tap-target",
      className: getAttribute(tag, "class"),
      label,
      labelSource,
      eventAttribute: attribute,
      handler,
      openType,
      formType,
      disabled: getAttribute(tag, "disabled"),
      loading: getAttribute(tag, "loading"),
      data: getDataAttributes(tag),
      wxIf: getAttribute(tag, "wx:if") || getAttribute(tag, "wx:elif"),
      wxFor: getAttribute(tag, "wx:for"),
      effects: classifyEffects(body),
      routeReferences: getRouteReferences(body),
    });
  }
  return controls;
}

function countBy(items, getKey) {
  const counts = {};
  for (const item of items) {
    const key = getKey(item);
    counts[key] = (counts[key] || 0) + 1;
  }
  return counts;
}

function escapeMarkdown(value) {
  return String(value || "")
    .replaceAll("|", "\\|")
    .replace(/\r?\n/g, " ")
    .trim();
}

function buildExpectedResult(control) {
  if (control.routeReferences.length) {
    return `跳转/打开 ${control.routeReferences.join(", ")}`;
  }
  if (control.effects.includes("navigation")) {
    return "返回上一页或回到首页";
  }
  if (control.effects.includes("api-or-service")) {
    return "触发接口/服务并更新页面反馈";
  }
  if (control.effects.includes("state")) {
    return "页面状态发生变化";
  }
  if (control.effects.includes("local-state")) {
    return "本地状态发生变化";
  }
  if (control.effects.includes("feedback")) {
    return "展示 Toast/弹窗/系统反馈";
  }
  return "待人工确认";
}

function buildMarkdownReport(report) {
  const lines = [
    "# Miniapp Button Action Audit",
    "",
    `- trace_id: ${report.traceId}`,
    `- generated_at: ${report.generatedAt}`,
    `- status: ${report.status}`,
    `- total_controls: ${report.summary.totalControls}`,
    `- buttons: ${report.summary.buttons}`,
    `- tap_targets: ${report.summary.tapTargets}`,
    `- pages: ${report.summary.pages}`,
    `- controls_missing_label: ${report.controlsMissingLabel.length}`,
    "",
    "本清单用于微信开发者工具或真机逐项点击验收。自动生成字段来自 WXML/TS 静态分析；`人工结果`、`设备/环境`、`证据` 由实测时填写。",
    "",
  ];

  for (const page of Object.keys(report.summary.byPage)) {
    const controls = report.controls.filter((control) => control.page === page);
    lines.push(`## ${page}`);
    lines.push("");
    lines.push("| ID | 行 | 类型 | 文案/入口 | 文案来源 | Handler | 预期效果 | 状态保护 | 人工结果 | 设备/环境 | 证据 |");
    lines.push("|---|---:|---|---|---|---|---|---|---|---|---|");
    controls.forEach((control, index) => {
      const id = `${page.replaceAll("/", "-")}-${String(index + 1).padStart(2, "0")}`;
      const stateGuard = [control.disabled ? `disabled=${control.disabled}` : "", control.loading ? `loading=${control.loading}` : ""]
        .filter(Boolean)
        .join("<br>");
      lines.push(
        [
          id,
          control.line,
          control.kind,
          escapeMarkdown(control.label),
          control.labelSource,
          control.handler || control.openType || control.formType,
          escapeMarkdown(buildExpectedResult(control)),
          escapeMarkdown(stateGuard || "无"),
          "待验收",
          "",
          "",
        ].join(" | ").replace(/^/, "| ").replace(/$/, " |"),
      );
    });
    lines.push("");
  }

  return `${lines.join("\n")}\n`;
}

function writeReport(report) {
  fs.mkdirSync(reportsRoot, { recursive: true });
  const stamp = new Date()
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\..+$/, "")
    .replace("T", "-");
  const reportPath = path.join(reportsRoot, `miniapp-buttons-${stamp}.json`);
  const markdownPath = path.join(reportsRoot, `miniapp-buttons-${stamp}.md`);
  fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  fs.writeFileSync(markdownPath, buildMarkdownReport(report), "utf8");
  fs.writeFileSync(path.join(reportsRoot, "latest.json"), `${JSON.stringify(report, null, 2)}\n`, "utf8");
  fs.writeFileSync(path.join(reportsRoot, "latest.md"), buildMarkdownReport(report), "utf8");
  return { reportPath, markdownPath };
}

const appConfig = JSON.parse(readText(appJsonPath));
const controls = [];

for (const pagePath of appConfig.pages ?? []) {
  const wxmlPath = path.join(miniappRoot, `${pagePath}.wxml`);
  const tsPath = path.join(miniappRoot, `${pagePath}.ts`);
  if (!fs.existsSync(wxmlPath) || !fs.existsSync(tsPath)) {
    continue;
  }
  controls.push(
    ...extractActionTargets(readText(wxmlPath), extractPageMethodBodies(readText(tsPath)), pagePath),
  );
}

const controlsMissingEffect = controls.filter((control) => control.handler && control.effects.length === 0);
const controlsMissingLabel = controls.filter((control) => !control.label);
const report = {
  traceId: "20260621-button-action-inventory",
  generatedAt: new Date().toISOString(),
  status: controls.length > 0 && controlsMissingEffect.length === 0 && controlsMissingLabel.length === 0 ? "pass" : "fail",
  summary: {
    totalControls: controls.length,
    buttons: controls.filter((control) => control.kind === "button").length,
    tapTargets: controls.filter((control) => control.kind === "tap-target").length,
    pages: Object.keys(countBy(controls, (control) => control.page)).length,
    byPage: countBy(controls, (control) => control.page),
    byEffect: countBy(controls.flatMap((control) => control.effects), (effect) => effect),
  },
  controlsMissingEffect,
  controlsMissingLabel,
  controls,
};

const { reportPath, markdownPath } = writeReport(report);
console.log(`Miniapp button/action audit ${report.status}: ${controls.length} controls across ${report.summary.pages} pages.`);
console.log(`Report: ${reportPath}`);
console.log(`Checklist: ${markdownPath}`);

if (report.status !== "pass") {
  process.exit(1);
}
