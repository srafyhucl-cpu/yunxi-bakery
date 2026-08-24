import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

const root = process.cwd();
const reportsRoot = path.join(root, "reports", "miniprogram-ci");
const projectConfigPath = path.join(root, "project.config.json");
const packageJsonPath = path.join(root, "package.json");
const requiredPrivateKeyEnv = "MINIPROGRAM_CI_PRIVATE_KEY_PATH";
const optionalRobotEnv = "MINIPROGRAM_CI_ROBOT";
const optionalVersionEnv = "MINIPROGRAM_CI_VERSION";
const optionalDescriptionEnv = "MINIPROGRAM_CI_DESC";
const minRobot = 1;
const maxRobot = 30;

function nowStamp() {
  return new Date()
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\..+$/, "")
    .replace("T", "-");
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function normalizeRelative(filePath) {
  return path.relative(root, filePath).split(path.sep).join("/");
}

function isInsideRepo(filePath) {
  const relativePath = path.relative(root, filePath);
  return Boolean(relativePath) && !relativePath.startsWith("..") && !path.isAbsolute(relativePath);
}

function checkProjectConfig() {
  const failures = [];
  const warnings = [];
  let appid = "";
  try {
    const projectConfig = readJson(projectConfigPath);
    appid = String(projectConfig.appid || "");
    if (projectConfig.miniprogramRoot !== "miniprogram/") {
      failures.push("project.config.json miniprogramRoot 必须是 miniprogram/");
    }
    if (projectConfig.compileType !== "miniprogram") {
      failures.push("project.config.json compileType 必须是 miniprogram");
    }
    if (!appid || appid === "touristappid") {
      failures.push("project.config.json appid 必须是真实小程序 AppID");
    }
    if (!projectConfig.setting?.urlCheck) {
      warnings.push("project.config.json setting.urlCheck 当前未开启，体验版/正式版不能依赖关闭域名校验");
    }
  } catch (error) {
    failures.push(`无法解析 project.config.json: ${error.message}`);
  }
  return {
    name: "project config",
    status: failures.length ? "fail" : "pass",
    appid,
    failures,
    warnings,
  };
}

function checkPackageDependency() {
  const gaps = [];
  let declared = false;
  let installed = false;
  try {
    const packageJson = readJson(packageJsonPath);
    declared = Boolean(
      packageJson.dependencies?.["miniprogram-ci"] ||
        packageJson.devDependencies?.["miniprogram-ci"],
    );
  } catch (error) {
    return {
      name: "miniprogram-ci dependency",
      status: "fail",
      failures: [`无法解析 package.json: ${error.message}`],
      gaps,
    };
  }
  installed = fs.existsSync(path.join(root, "node_modules", "miniprogram-ci"));
  if (!declared) {
    gaps.push("package.json 尚未声明 miniprogram-ci；配置真实上传前再引入依赖");
  }
  if (declared && !installed) {
    gaps.push("node_modules 中尚未安装 miniprogram-ci；安装时需把 npm cache 指向 D 盘");
  }
  return {
    name: "miniprogram-ci dependency",
    status: "pass",
    declared,
    installed,
    gaps,
  };
}

function trackedFiles() {
  const result = spawnSync("git", ["ls-files"], {
    cwd: root,
    encoding: "utf8",
    shell: false,
  });
  if (result.status !== 0) {
    return {
      files: [],
      error: result.stderr || result.stdout || "git ls-files failed",
    };
  }
  return {
    files: String(result.stdout || "")
      .split(/\r?\n/)
      .filter(Boolean),
    error: "",
  };
}

function checkSensitiveFiles() {
  const tracked = trackedFiles();
  if (tracked.error) {
    return {
      name: "private key hygiene",
      status: "fail",
      failures: [tracked.error],
      trackedSensitiveFiles: [],
    };
  }
  const trackedSensitiveFiles = tracked.files.filter((file) => {
    const lower = file.toLowerCase();
    return (
      lower.includes("private_key") ||
      lower.endsWith(".pem") ||
      lower.endsWith(".p12") ||
      lower.endsWith(".pfx") ||
      lower.endsWith(".key")
    );
  });
  return {
    name: "private key hygiene",
    status: trackedSensitiveFiles.length ? "fail" : "pass",
    failures: trackedSensitiveFiles.map((file) => `敏感密钥文件不应被 Git 跟踪: ${file}`),
    trackedSensitiveFiles,
  };
}

function checkPrivateKeyPath() {
  const gaps = [];
  const failures = [];
  const rawValue = process.env[requiredPrivateKeyEnv] || "";
  const resolvedPath = rawValue ? path.resolve(root, rawValue) : "";
  if (!rawValue) {
    gaps.push(`${requiredPrivateKeyEnv} 未配置；不会执行 miniprogram-ci 预览或上传`);
  } else if (!fs.existsSync(resolvedPath) || !fs.statSync(resolvedPath).isFile()) {
    failures.push(`${requiredPrivateKeyEnv} 指向的文件不存在或不是文件`);
  } else if (isInsideRepo(resolvedPath)) {
    failures.push(`${requiredPrivateKeyEnv} 指向仓库内部文件，密钥必须放在仓库外或 CI 临时目录`);
  }
  return {
    name: "private key path",
    status: failures.length ? "fail" : "pass",
    envName: requiredPrivateKeyEnv,
    configured: Boolean(rawValue),
    pathHint: rawValue ? normalizeRelative(resolvedPath) : "",
    failures,
    gaps,
  };
}

function checkOptionalCiEnv() {
  const gaps = [];
  const failures = [];
  const robot = process.env[optionalRobotEnv] || "";
  const version = process.env[optionalVersionEnv] || "";
  const description = process.env[optionalDescriptionEnv] || "";
  if (robot) {
    const robotNumber = Number.parseInt(robot, 10);
    if (!Number.isInteger(robotNumber) || robotNumber < minRobot || robotNumber > maxRobot) {
      failures.push(`${optionalRobotEnv} 必须是 ${minRobot}-${maxRobot} 之间的整数`);
    }
  } else {
    gaps.push(`${optionalRobotEnv} 未配置；默认上传机器人号需在真实 CI 脚本中显式指定`);
  }
  if (!version) {
    gaps.push(`${optionalVersionEnv} 未配置；上传体验版或正式包前必须有版本号`);
  }
  if (!description) {
    gaps.push(`${optionalDescriptionEnv} 未配置；上传前必须写明版本说明`);
  }
  return {
    name: "optional upload env",
    status: failures.length ? "fail" : "pass",
    configured: {
      [optionalRobotEnv]: Boolean(robot),
      [optionalVersionEnv]: Boolean(version),
      [optionalDescriptionEnv]: Boolean(description),
    },
    failures,
    gaps,
  };
}

function main() {
  fs.mkdirSync(reportsRoot, { recursive: true });
  const checks = [
    checkProjectConfig(),
    checkPackageDependency(),
    checkSensitiveFiles(),
    checkPrivateKeyPath(),
    checkOptionalCiEnv(),
  ];
  const failures = checks.flatMap((check) => check.failures || []);
  const gaps = checks.flatMap((check) => check.gaps || []);
  const report = {
    traceId: "20260707-miniapp-miniprogram-ci-readiness",
    generatedAt: new Date().toISOString(),
    status: failures.length ? "fail" : gaps.length ? "needs_configuration" : "pass",
    projectPath: root,
    checks,
    summary: {
      failures: failures.length,
      configurationGaps: gaps.length,
      gaps,
    },
    notes: [
      "本检查只读，不调用微信上传接口，不生成体验版，不读取密钥内容。",
      "配置真实 miniprogram-ci 前，私钥文件必须放在仓库外或 CI 临时目录，且不得进入 Git 跟踪。",
    ],
  };
  const payload = `${JSON.stringify(report, null, 2)}\n`;
  const reportPath = path.join(reportsRoot, `miniprogram-ci-readiness-${nowStamp()}.json`);
  fs.writeFileSync(reportPath, payload, "utf8");
  fs.writeFileSync(path.join(reportsRoot, "latest.json"), payload, "utf8");
  console.log(
    `miniprogram-ci readiness ${report.status}: ${failures.length} failures, ${gaps.length} configuration gaps.`,
  );
  console.log(`Report: ${reportPath}`);
  if (failures.length) {
    for (const failure of failures) {
      console.error(`- ${failure}`);
    }
    process.exit(1);
  }
}

main();
