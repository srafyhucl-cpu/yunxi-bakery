import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

const root = process.cwd();
const reportsRoot = path.join(root, "reports", "devtools");
const cliPath = "D:\\微信web开发者工具\\cli.bat";

function nowStamp() {
  return new Date()
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\..+$/, "")
    .replace("T", "-");
}

function tail(value, maxLines = 40) {
  return String(value || "")
    .split(/\r?\n/)
    .filter(Boolean)
    .slice(-maxLines);
}

function run(args, timeoutMs) {
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
  const checks = [];
  const report = {
    traceId: "20260617-devtools-open-project",
    generatedAt: new Date().toISOString(),
    project: root,
    cliPath,
    status: "fail",
    checks,
    notes: [],
  };

  if (!fs.existsSync(cliPath)) {
    report.notes.push("微信开发者工具 CLI 不存在");
  } else {
    const openCheck = {
      name: "open project",
      ...run(["open", "--project", root], 60000),
    };
    checks.push(openCheck);
    const hasInitError = [
      ...(openCheck.stdoutTail || []),
      ...(openCheck.stderrTail || []),
    ].some((line) => /initialize-error|wait IDE port timeout|port timeout|throw err|Error:|EEXIST/i.test(line));
    report.status = openCheck.exitCode === 0 && !openCheck.timedOut ? (hasInitError ? "needs_manual_confirmation" : "pass") : "fail";
    if (report.status === "needs_manual_confirmation") {
      report.notes.push("CLI open 已返回成功，但检测到 IDE 初始化/端口等待提示，需要前台确认编译与页面视觉");
    } else if (report.status !== "pass") {
      report.notes.push("CLI open 未完成；通常需要前台打开 IDE、确认登录、项目信任或重启自动化端口");
    }
  }

  const payload = `${JSON.stringify(report, null, 2)}\n`;
  const reportPath = path.join(reportsRoot, `devtools-open-${nowStamp()}.json`);
  fs.writeFileSync(reportPath, payload, "utf8");
  fs.writeFileSync(path.join(reportsRoot, "open-latest.json"), payload, "utf8");
  console.log(`DevTools open ${report.status}: ${root}`);
  console.log(`Report: ${reportPath}`);
  if (report.status !== "pass") {
    process.exit(1);
  }
}

main();
