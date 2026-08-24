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

function tail(value, maxLines = 60) {
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

function fileInfo(filePath) {
  if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
    return { exists: false, size: 0 };
  }
  return {
    exists: true,
    size: fs.statSync(filePath).size,
  };
}

function sleep(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

function waitForFile(filePath, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  let info = fileInfo(filePath);
  while ((!info.exists || info.size === 0) && Date.now() < deadline) {
    sleep(250);
    info = fileInfo(filePath);
  }
  return info;
}

function main() {
  fs.mkdirSync(reportsRoot, { recursive: true });
  const stamp = nowStamp();
  const qrPath = path.join(reportsRoot, `devtools-preview-${stamp}.png`);
  const infoPath = path.join(reportsRoot, `devtools-preview-${stamp}-info.json`);
  const reportPath = path.join(reportsRoot, `devtools-preview-${stamp}.json`);
  const latestPath = path.join(reportsRoot, "preview-latest.json");
  const latestQrPath = path.join(reportsRoot, "preview-latest.png");

  const report = {
    traceId: "20260617-devtools-preview-check",
    generatedAt: new Date().toISOString(),
    project: root,
    cliPath,
    qrPath,
    infoPath,
    status: "fail",
    checks: [],
    notes: [],
  };

  if (!fs.existsSync(cliPath)) {
    report.notes.push("微信开发者工具 CLI 不存在");
  } else {
    const isLoginCheck = {
      name: "islogin",
      ...run(["islogin"], 30000),
    };
    report.checks.push(isLoginCheck);

    const previewCheck = {
      name: "preview",
      ...run(
        [
          "preview",
          "--project",
          root,
          "--qr-format",
          "image",
          "--qr-output",
          qrPath,
          "--info-output",
          infoPath,
        ],
        120000,
      ),
    };
    report.checks.push(previewCheck);

    const qr = waitForFile(qrPath);
    const info = waitForFile(infoPath);
    report.artifacts = {
      qr,
      info,
    };
    const outputText = [
      ...(previewCheck.stdoutTail || []),
      ...(previewCheck.stderrTail || []),
    ].join("\n");
    const needsManualConfirmation = /initialize-error|wait IDE port timeout|login|登录|permission|权限|trust|信任/i.test(outputText);
    const hasCliErrorOutput = /\[error\]|code:\s*10|错误 undefined/i.test(outputText);
    const ok = previewCheck.exitCode === 0 && !previewCheck.timedOut && qr.exists && qr.size > 0;
    report.status = ok ? "pass" : needsManualConfirmation ? "needs_manual_confirmation" : "fail";
    if (report.status === "pass") {
      fs.copyFileSync(qrPath, latestQrPath);
      report.notes.push("DevTools preview 已生成二维码；仍需真机扫码验证页面和合法域名请求。");
      if (hasCliErrorOutput) {
        report.notes.push("DevTools CLI 同时输出了 code 10/错误信息，但二维码和包体信息已落盘；按二维码产物作为本次预览可用证据。");
      }
    } else if (report.status === "needs_manual_confirmation") {
      report.notes.push("DevTools preview 需要前台登录、项目信任或自动化端口确认；未生成可验收二维码。");
    } else {
      report.notes.push("DevTools preview 未生成可验收二维码。");
    }
  }

  const payload = `${JSON.stringify(report, null, 2)}\n`;
  fs.writeFileSync(reportPath, payload, "utf8");
  fs.writeFileSync(latestPath, payload, "utf8");
  console.log(`DevTools preview ${report.status}: ${root}`);
  console.log(`Report: ${reportPath}`);
  if (report.status !== "pass") {
    process.exit(1);
  }
}

main();
