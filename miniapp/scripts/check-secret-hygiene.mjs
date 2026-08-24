import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

const root = process.cwd();
const backendRoot = path.resolve(root, "..", "YunxiBakeBot");
const reportsRoot = path.join(root, "reports", "secret-check");

const scannedRoots = [
  { name: "miniapp", root },
  { name: "backend", root: backendRoot },
];

const excludedSegments = new Set([
  ".git",
  "node_modules",
  "miniprogram_npm",
  "dist",
  "build",
  "__pycache__",
  ".pytest_cache",
  "htmlcov",
  "reports",
  "data",
]);

const scannedExtensions = new Set([
  ".js",
  ".mjs",
  ".ts",
  ".tsx",
  ".vue",
  ".json",
  ".md",
  ".py",
  ".sh",
  ".yml",
  ".yaml",
  ".toml",
  ".env",
  ".example",
  ".conf",
  ".txt",
]);

const allowedValuePatterns = [
  /^$/,
  /^your[-_]/i,
  /^<.+>$/,
  /^secret-value$/,
  /^\$\{?[A-Z0-9_]+\}?$/,
  /^settings\.[A-Z0-9_]+$/,
  /^os\.environ\./,
  /^process\.env\.[A-Z0-9_]+$/,
  /^import\.meta\.env\.[A-Z0-9_]+$/,
  /^[A-Z][A-Z0-9_]*$/,
  /^[a-z][A-Za-z0-9_]*$/,
  /^sk-your/i,
  /^TOKEN_FROM_/,
  /^CHANGE_ME/i,
  /^ci[-_]/i,
  /^LOCAL_[A-Z0-9_]+_TOKEN$/,
  /^callback-token$/,
  /^mock[_-]/i,
  /^test[_-]/i,
  /^dummy/i,
  /^example/i,
  /^base64\.b64encode/,
  /^\($/,
];

const secretAssignments = [
  /\b([A-Z][A-Z0-9_]*)\b\s*:\s*[^=]+=\s*["']?([^"'\s#;,<>]+)/,
  /\b([A-Z][A-Z0-9_]*)\b\s*=\s*["']?([^"'\s#;,<>]+)/,
  /\b([A-Z][A-Z0-9_]*)\b\s*:\s*["']?([^"'\s#;,<>]+)/,
];

const rawSecretPatterns = [
  /-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----/,
  /\bsk-[A-Za-z0-9_-]{20,}\b/,
  /\b(?:AKIA|ASIA)[A-Z0-9]{16}\b/,
  /\bgh[pousr]_[A-Za-z0-9_]{30,}\b/,
];

function toPosixRelative(rootDir, filePath) {
  return path.relative(rootDir, filePath).split(path.sep).join("/");
}

function shouldSkipPath(filePath) {
  return filePath
    .split(path.sep)
    .some((segment) => excludedSegments.has(segment));
}

function shouldScanFile(filePath) {
  const base = path.basename(filePath);
  if (base === ".env") {
    return false;
  }
  if (base.startsWith(".env.") || base === ".env.example") {
    return true;
  }
  return scannedExtensions.has(path.extname(filePath));
}

function walkFiles(dir, files = []) {
  if (!fs.existsSync(dir)) {
    return files;
  }
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const entryPath = path.join(dir, entry.name);
    if (shouldSkipPath(entryPath)) {
      continue;
    }
    if (entry.isDirectory()) {
      walkFiles(entryPath, files);
    } else if (entry.isFile() && shouldScanFile(entryPath)) {
      files.push(entryPath);
    }
  }
  return files;
}

function isAllowedValue(value) {
  const normalized = value.trim().replace(/^["']|["']$/g, "");
  return allowedValuePatterns.some((pattern) => pattern.test(normalized));
}

function isSensitiveConfigKey(key) {
  return (
    key.includes("API_KEY") ||
    key.includes("PRIVATE_KEY") ||
    key.includes("AES_KEY") ||
    key.includes("APP_SECRET") ||
    key.includes("CLIENT_SECRET") ||
    key.includes("SECRET") ||
    key.includes("CERT") ||
    key.includes("MCH_ID") ||
    key === "TOKEN" ||
    key.endsWith("_TOKEN")
  );
}

function isComparisonLine(line) {
  return /[!<>=]=/.test(line);
}

function isShellParameterExpansion(line) {
  return /\$\{[A-Z0-9_]+:-/.test(line);
}

function isSecretReferenceLine(line) {
  return /\$\{\{\s*secrets\.[A-Z0-9_]+\s*\}\}/.test(line);
}

function isShellConfigValidationLine(line) {
  return /\b(?:grep|sed)\b/.test(line);
}

function isPythonAssertionLine(line) {
  return /^\s*(?:assert|self\.assert)/.test(line);
}

function isDynamicSecretGenerationLine(line) {
  return /\bsecrets\.token_(?:urlsafe|hex)\s*\(/.test(line);
}

function isTestSecretFixture(relativePath, key) {
  return (
    key.startsWith("TEST_") &&
    (relativePath.startsWith("tests/") || relativePath.startsWith("scripts/check_"))
  );
}

function scanFile(repoName, repoRoot, filePath) {
  const findings = [];
  let text = "";
  try {
    text = fs.readFileSync(filePath, "utf8");
  } catch {
    return findings;
  }
  const relativePath = toPosixRelative(repoRoot, filePath);
  const lines = text.split(/\r?\n/);
  lines.forEach((line, index) => {
    for (const pattern of rawSecretPatterns) {
      if (/sk-your/i.test(line)) {
        continue;
      }
      if (pattern.test(line)) {
        findings.push({
          repo: repoName,
          file: relativePath,
          line: index + 1,
          type: "raw-secret-pattern",
          message: "疑似私钥、云密钥或 API key 片段",
          preview: line.trim().slice(0, 160),
        });
      }
    }
    for (const pattern of secretAssignments) {
      const match = line.match(pattern);
      if (!match) {
        continue;
      }
      const key = match[1] || "";
      if (
        !isSensitiveConfigKey(key) ||
        isComparisonLine(line) ||
        isShellParameterExpansion(line) ||
        isSecretReferenceLine(line) ||
        isTestSecretFixture(relativePath, key) ||
        isShellConfigValidationLine(line) ||
        isPythonAssertionLine(line) ||
        isDynamicSecretGenerationLine(line)
      ) {
        continue;
      }
      const value = match[2] || "";
      if (!isAllowedValue(value)) {
        findings.push({
          repo: repoName,
          file: relativePath,
          line: index + 1,
          type: "secret-assignment",
          message: "敏感配置疑似被赋真实值",
          keyHint: key,
          preview: line.replace(value, "<redacted>").trim().slice(0, 160),
        });
      }
    }
  });
  return findings;
}

function runGit(repoRoot, args) {
  return spawnSync("git", args, {
    cwd: repoRoot,
    encoding: "utf8",
    shell: false,
  });
}

function checkTrackedSensitiveFiles(repoName, repoRoot) {
  const result = runGit(repoRoot, ["ls-files"]);
  if (result.status !== 0) {
    return [
      {
        repo: repoName,
        type: "git-ls-files-error",
        message: result.stderr || result.stdout || "git ls-files failed",
      },
    ];
  }
  return String(result.stdout || "")
    .split(/\r?\n/)
    .filter(Boolean)
    .filter((file) => {
      const normalized = file.toLowerCase();
      if (normalized === ".env.example") {
        return false;
      }
      return (
        normalized === ".env" ||
        normalized.includes("private_key") ||
        normalized.endsWith(".pem") ||
        normalized.endsWith(".p12") ||
        normalized.endsWith(".pfx") ||
        normalized.endsWith(".key")
      );
    })
    .map((file) => ({
      repo: repoName,
      file,
      type: "tracked-sensitive-file",
      message: "敏感文件不应被 Git 跟踪",
    }));
}

function main() {
  fs.mkdirSync(reportsRoot, { recursive: true });
  const checks = [];
  const findings = [];
  for (const repo of scannedRoots) {
    const trackedSensitiveFiles = checkTrackedSensitiveFiles(repo.name, repo.root);
    findings.push(...trackedSensitiveFiles);
    const files = walkFiles(repo.root);
    let scannedCount = 0;
    for (const filePath of files) {
      scannedCount += 1;
      findings.push(...scanFile(repo.name, repo.root, filePath));
    }
    checks.push({
      repo: repo.name,
      root: repo.root,
      scannedFiles: scannedCount,
      trackedSensitiveFiles: trackedSensitiveFiles.length,
    });
  }

  const report = {
    traceId: "20260617-secret-hygiene-check",
    generatedAt: new Date().toISOString(),
    status: findings.length ? "fail" : "pass",
    checks,
    findings,
  };
  const stamp = new Date()
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\..+$/, "")
    .replace("T", "-");
  const reportPath = path.join(reportsRoot, `secret-hygiene-${stamp}.json`);
  const payload = `${JSON.stringify(report, null, 2)}\n`;
  fs.writeFileSync(reportPath, payload, "utf8");
  fs.writeFileSync(path.join(reportsRoot, "latest.json"), payload, "utf8");
  console.log(`Secret hygiene ${report.status}: ${checks.map((item) => `${item.repo} ${item.scannedFiles} files`).join(", ")}`);
  console.log(`Report: ${reportPath}`);
  if (findings.length) {
    for (const finding of findings.slice(0, 20)) {
      console.error(`- ${finding.repo}:${finding.file || ""}:${finding.line || ""} ${finding.message}`);
    }
    process.exit(1);
  }
}

main();
