import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

const root = process.cwd();
const backendRoot = path.resolve(root, "..", "YunxiBakeBot");
const adminRoot = path.join(backendRoot, "web", "admin");
const reportsRoot = path.join(root, "reports", "release-readiness");
const backendUiReports = path.join(backendRoot, "reports", "ui");
const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";
const npmCliPath = process.platform === "win32"
  ? path.join(path.dirname(process.execPath), "node_modules", "npm", "bin", "npm-cli.js")
  : "";
const pythonCommand = "python";

const requiredMiniappPages = [
  "pages/home/index",
  "pages/products/index",
  "pages/product-detail/index",
  "pages/cart/index",
  "pages/checkout/index",
  "pages/policy/index",
  "pages/address/index",
  "pages/orders/index",
  "pages/order-detail/index",
  "pages/group-registration/index",
  "pages/chat/index",
  "pages/profile/index",
];

const requiredSmokeScreenshots = [
  "decoration-product-picker-smoke.png",
  "shop-settings-smoke.png",
  "addresses-editing-smoke.png",
  "orders-summary-smoke.png",
  "orders-confirmation-smoke.png",
  "products-active-toggle-smoke.png",
  "transfers-queue-smoke.png",
  "mobile-operations-smoke.png",
  "production-admin-browser-smoke.png",
];

const commandChecks = [
  {
    name: "miniapp static checks",
    cwd: root,
    command: npmCommand,
    args: ["run", "check:miniapp"],
  },
  {
    name: "miniapp page API coverage contract",
    cwd: root,
    command: npmCommand,
    args: ["run", "check:page-api-coverage"],
  },
  {
    name: "miniapp observability contract",
    cwd: root,
    command: npmCommand,
    args: ["run", "check:observability-contract"],
  },
  {
    name: "miniapp button/action audit",
    cwd: root,
    command: npmCommand,
    args: ["run", "audit:buttons"],
  },
  {
    name: "miniapp button touch target scan",
    cwd: root,
    command: npmCommand,
    args: ["run", "scan:button-touch-targets"],
  },
  {
    name: "miniapp typecheck",
    cwd: root,
    command: npmCommand,
    args: ["run", "typecheck"],
  },
  {
    name: "wechat devtools CLI detection",
    cwd: root,
    command: npmCommand,
    args: ["run", "devtools:check"],
  },
  {
    name: "wechat devtools project open/login state",
    cwd: root,
    command: npmCommand,
    args: ["run", "devtools:open-check"],
  },
  {
    name: "miniprogram-ci readiness contract",
    cwd: root,
    command: npmCommand,
    args: ["run", "check:miniprogram-ci-readiness"],
  },
  {
    name: "production domain HTTPS check",
    cwd: root,
    command: npmCommand,
    args: ["run", "check:production-domain"],
  },
  {
    name: "production miniapp API smoke",
    cwd: root,
    command: npmCommand,
    args: ["run", "check:production-miniapp-api"],
  },
  {
    name: "production admin frontend check",
    cwd: root,
    command: npmCommand,
    args: ["run", "check:production-admin"],
  },
  {
    name: "production admin API smoke",
    cwd: root,
    command: npmCommand,
    args: ["run", "check:production-admin-api"],
  },
  {
    name: "production admin browser smoke",
    cwd: root,
    command: npmCommand,
    args: ["run", "check:production-admin-browser"],
  },
  {
    name: "secret hygiene check",
    cwd: root,
    command: npmCommand,
    args: ["run", "check:secrets"],
  },
  {
    name: "admin typecheck",
    cwd: adminRoot,
    command: npmCommand,
    args: ["run", "typecheck"],
  },
  ...[
    "check:decoration",
    "check:orders",
    "check:addresses",
    "check:products",
    "check:shop-settings",
    "check:mobile-ops",
  ].map((script) => ({
    name: `admin ${script}`,
    cwd: adminRoot,
    command: npmCommand,
    args: ["run", script],
  })),
  {
    name: "backend miniapp/admin API target tests",
    cwd: backendRoot,
    command: pythonCommand,
    args: [
      "-m",
      "pytest",
      "-o",
      "addopts=",
      "tests/api/test_shop_page_config_api.py",
      "tests/api/test_shop_operations_api.py",
      "tests/api/test_miniapp_catalog_api.py",
      "tests/api/test_miniapp_order_api.py",
      "tests/api/test_admin_order_api.py",
      "tests/api/test_miniapp_address_api.py",
      "tests/api/test_admin_address_api.py",
      "tests/api/test_miniapp_payment_api.py",
      "tests/api/test_miniapp_auth_api.py",
    ],
  },
  {
    name: "backend transfer target tests",
    cwd: backendRoot,
    command: pythonCommand,
    args: [
      "-m",
      "pytest",
      "-o",
      "addopts=",
      "tests/api/test_admin_transfer_api.py",
      "tests/service/test_storefront_conversation.py",
      "tests/api/test_miniapp_chat_api.py",
    ],
  },
];

function nowStamp() {
  const date = new Date();
  const pad = (value) => String(value).padStart(2, "0");
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
    "-",
    pad(date.getHours()),
    pad(date.getMinutes()),
    pad(date.getSeconds()),
  ].join("");
}

function tail(value, maxLines = 40) {
  return String(value || "")
    .split(/\r?\n/)
    .filter(Boolean)
    .slice(-maxLines);
}

function runCommand(check) {
  const startedAt = Date.now();
  const useNodeNpmCli = check.command === npmCommand && process.platform === "win32" && fs.existsSync(npmCliPath);
  const executable = useNodeNpmCli ? process.execPath : check.command;
  const args = useNodeNpmCli ? [npmCliPath, ...check.args] : check.args;
  const result = spawnSync(executable, args, {
    cwd: check.cwd,
    encoding: "utf8",
    shell: false,
    env: process.env,
  });
  const durationMs = Date.now() - startedAt;
  return {
    name: check.name,
    type: "command",
    status: result.status === 0 ? "pass" : "fail",
    cwd: check.cwd,
    command: [executable, ...args].join(" "),
    durationMs,
    exitCode: result.status,
    stdoutTail: tail(result.stdout),
    stderrTail: tail(result.stderr),
    error: result.error ? String(result.error.message || result.error) : "",
  };
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function fileExists(filePath) {
  return fs.existsSync(filePath) && fs.statSync(filePath).isFile();
}

function checkMiniappProjectConfig() {
  const appJsonPath = path.join(root, "miniprogram", "app.json");
  const projectConfigPath = path.join(root, "project.config.json");
  const sitemapPath = path.join(root, "miniprogram", "sitemap.json");
  const failures = [];
  const warnings = [];

  try {
    const appJson = readJson(appJsonPath);
    const pages = new Set(appJson.pages || []);
    for (const page of requiredMiniappPages) {
      if (!pages.has(page)) {
        failures.push(`app.json missing required page: ${page}`);
      }
    }
    if (appJson.renderer !== "skyline") {
      warnings.push("app.json renderer is not skyline");
    }
    if (appJson.componentFramework !== "glass-easel") {
      warnings.push("app.json componentFramework is not glass-easel");
    }
    if (appJson.window?.navigationStyle !== "custom") {
      warnings.push("app.json window.navigationStyle is not custom");
    }
  } catch (error) {
    failures.push(`cannot parse miniprogram/app.json: ${error.message}`);
  }

  try {
    const projectConfig = readJson(projectConfigPath);
    if (projectConfig.miniprogramRoot !== "miniprogram/") {
      failures.push("project.config.json miniprogramRoot must be miniprogram/");
    }
    if (projectConfig.compileType !== "miniprogram") {
      failures.push("project.config.json compileType must be miniprogram");
    }
    if (!projectConfig.setting?.urlCheck) {
      warnings.push("project.config.json setting.urlCheck is not enabled");
    }
    if (!projectConfig.appid || projectConfig.appid === "touristappid") {
      warnings.push("project.config.json appid is not a real Mini Program AppID");
    }
  } catch (error) {
    failures.push(`cannot parse project.config.json: ${error.message}`);
  }

  try {
    readJson(sitemapPath);
  } catch (error) {
    failures.push(`cannot parse miniprogram/sitemap.json: ${error.message}`);
  }

  return {
    name: "miniapp release config",
    type: "static",
    status: failures.length ? "fail" : "pass",
    failures,
    warnings,
  };
}

function checkRequiredFiles() {
  const requiredFiles = [
    path.join(root, "docs", "api-contract.md"),
    path.join(root, "docs", "observability-contract.md"),
    path.join(root, "docs", "page-api-coverage.md"),
    path.join(root, "docs", "release", "miniprogram-ci-readiness.md"),
    path.join(root, "docs", "release", "manual-acceptance-checklist.md"),
    path.join(root, "docs", "harness-engineering", "core", "evidence-index.md"),
    path.join(root, "docs", "harness-engineering", "core", "verification-matrix.md"),
    path.join(root, "miniprogram", "pages", "policy", "index.ts"),
    path.join(root, "miniprogram", "services", "shop-settings.ts"),
    path.join(root, "miniprogram", "services", "orders.ts"),
    path.join(root, "miniprogram", "services", "chat.ts"),
    path.join(backendRoot, "web", "admin", "src", "pages", "decoration", "DecorationPage.vue"),
    path.join(backendRoot, "web", "admin", "src", "pages", "orders", "OrdersPage.vue"),
    path.join(backendRoot, "web", "admin", "src", "pages", "transfers", "TransfersPage.vue"),
    path.join(backendRoot, "web", "admin", "src", "constants", "adminNavigation.ts"),
  ];
  const missing = requiredFiles.filter((filePath) => !fileExists(filePath));
  return {
    name: "required MVP files",
    type: "static",
    status: missing.length ? "fail" : "pass",
    missing,
  };
}

function checkSmokeEvidence() {
  const missing = requiredSmokeScreenshots
    .map((fileName) => path.join(backendUiReports, fileName))
    .filter((filePath) => !fileExists(filePath));
  return {
    name: "browser smoke screenshot evidence",
    type: "evidence",
    status: missing.length ? "fail" : "pass",
    required: requiredSmokeScreenshots.map((fileName) => path.join(backendUiReports, fileName)),
    missing,
  };
}

function checkTempDbResidue() {
  const residues = [];
  if (fs.existsSync(backendUiReports)) {
    for (const name of fs.readdirSync(backendUiReports)) {
      if (/\.db(?:-wal|-shm)?$/i.test(name)) {
        residues.push(path.join(backendUiReports, name));
      }
    }
  }
  return {
    name: "smoke temporary database residue",
    type: "cleanup",
    status: residues.length ? "fail" : "pass",
    residues,
  };
}

function main() {
  fs.mkdirSync(reportsRoot, { recursive: true });

  const report = {
    traceId: "20260617-release-readiness-gate",
    generatedAt: new Date().toISOString(),
    root,
    backendRoot,
    checks: [],
    manualChecklist: path.join(root, "docs", "release", "manual-acceptance-checklist.md"),
    devtoolsCliReport: path.join(root, "reports", "devtools", "latest.json"),
    manualGates: [
      "微信开发者工具编译与核心页面视觉检查",
      "真机或体验版下单、客服、订单详情交互检查",
      "真实微信支付商户参数、支付通知验签和回调落库联调",
      "微信公众平台合法域名、隐私协议、服务类目、体验版二维码和审核记录",
    ],
  };

  report.checks.push(checkMiniappProjectConfig());
  report.checks.push(checkRequiredFiles());
  for (const commandCheck of commandChecks) {
    report.checks.push(runCommand(commandCheck));
  }
  report.checks.push(checkSmokeEvidence());
  report.checks.push(checkTempDbResidue());

  const failed = report.checks.filter((check) => check.status !== "pass");
  report.status = failed.length ? "fail" : "pass";
  report.summary = {
    total: report.checks.length,
    passed: report.checks.length - failed.length,
    failed: failed.length,
    failedChecks: failed.map((check) => check.name),
  };

  const reportPath = path.join(reportsRoot, `readiness-${nowStamp()}.json`);
  const latestPath = path.join(reportsRoot, "latest.json");
  const json = `${JSON.stringify(report, null, 2)}\n`;
  fs.writeFileSync(reportPath, json, "utf8");
  fs.writeFileSync(latestPath, json, "utf8");

  console.log(`Release readiness ${report.status}: ${report.summary.passed}/${report.summary.total} checks passed`);
  console.log(`Report: ${reportPath}`);
  if (failed.length) {
    for (const check of failed) {
      console.error(`- ${check.name}`);
    }
    process.exit(1);
  }
}

main();
