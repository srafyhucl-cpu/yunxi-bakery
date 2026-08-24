import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

const root = process.cwd();
const reportsRoot = path.join(root, "reports", "devtools");
const knownCliPaths = [
  "D:\\微信web开发者工具\\cli.bat",
  "D:\\Program Files\\Tencent\\微信web开发者工具\\cli.bat",
  "D:\\Program Files (x86)\\Tencent\\微信web开发者工具\\cli.bat",
  "C:\\Program Files\\Tencent\\微信web开发者工具\\cli.bat",
  "C:\\Program Files (x86)\\Tencent\\微信web开发者工具\\cli.bat",
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

function tail(value, maxLines = 30) {
  return String(value || "")
    .split(/\r?\n/)
    .filter(Boolean)
    .slice(-maxLines);
}

function findCliPath() {
  const pathEntries = String(process.env.PATH || "").split(path.delimiter);
  const candidates = [
    ...knownCliPaths,
    ...pathEntries.map((entry) => path.join(entry, "cli.bat")),
  ];
  return candidates.find((candidate) => fs.existsSync(candidate) && fs.statSync(candidate).isFile()) || "";
}

function runCli(cliPath, args, timeoutMs) {
  const startedAt = Date.now();
  const result = spawnSync(cliPath, args, {
    cwd: root,
    encoding: "utf8",
    timeout: timeoutMs,
    shell: process.platform === "win32",
  });
  return {
    command: [cliPath, ...args].join(" "),
    durationMs: Date.now() - startedAt,
    exitCode: result.status,
    signal: result.signal || "",
    timedOut: result.error?.code === "ETIMEDOUT",
    stdoutTail: tail(result.stdout),
    stderrTail: tail(result.stderr),
    error: result.error ? String(result.error.message || result.error) : "",
  };
}

function main() {
  fs.mkdirSync(reportsRoot, { recursive: true });
  const cliPath = findCliPath();
  const report = {
    traceId: "20260617-devtools-cli-detection",
    generatedAt: new Date().toISOString(),
    project: root,
    cliPath,
    status: "fail",
    checks: [],
    notes: [],
  };

  if (!cliPath) {
    report.notes.push("未在常见路径或 PATH 中找到微信开发者工具 cli.bat");
  } else {
    report.checks.push({
      name: "cli help",
      ...runCli(cliPath, ["--help"], 30000),
    });
    const versionPath = path.join(path.dirname(cliPath), "version");
    if (fs.existsSync(versionPath)) {
      report.version = fs.readFileSync(versionPath, "utf8").trim();
    }

    const helpOk = report.checks[0].exitCode === 0 && !report.checks[0].timedOut;
    report.status = helpOk ? "pass" : "fail";
    report.notes.push(
      helpOk
        ? "CLI 可执行；项目 open/preview 仍可能需要 IDE 前台登录、自动化端口或信任确认"
        : "CLI 存在但 help 调用失败，请手工打开微信开发者工具检查",
    );
  }

  const reportPath = path.join(reportsRoot, `devtools-cli-${nowStamp()}.json`);
  const latestPath = path.join(reportsRoot, "latest.json");
  const payload = `${JSON.stringify(report, null, 2)}\n`;
  fs.writeFileSync(reportPath, payload, "utf8");
  fs.writeFileSync(latestPath, payload, "utf8");

  console.log(`DevTools CLI detection ${report.status}: ${cliPath || "not found"}`);
  console.log(`Report: ${reportPath}`);
  if (report.status !== "pass") {
    process.exit(1);
  }
}

main();
