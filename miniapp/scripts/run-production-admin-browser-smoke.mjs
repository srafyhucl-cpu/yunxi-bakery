import fs from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";

const root = process.cwd();
const backendRoot = path.resolve(root, "..", "YunxiBakeBot");
const adminRoot = path.join(backendRoot, "web", "admin");
const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";
const npmCliPath = process.platform === "win32"
  ? path.join(path.dirname(process.execPath), "node_modules", "npm", "bin", "npm-cli.js")
  : "";
const remoteTokenTimeoutMs = 15000;
const browserSmokeTimeoutMs = 180000;

function getTokenFromRemoteEnv() {
  const remoteScript = `
from pathlib import Path
import shlex
path = Path('/opt/apps/yunxibakebot/.env')
if not path.exists():
    raise SystemExit(0)
for raw in path.read_text(errors='ignore').splitlines():
    line = raw.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    key, value = line.split('=', 1)
    if key.strip() == 'ADMIN_API_TOKEN':
        print(shlex.split(value.strip())[0] if value.strip() else '')
        break
`;
  const result = spawnSync(
    "ssh",
    [
      "-i",
      "C:\\Users\\srafy\\.ssh\\id_ed25519",
      "-p",
      "22",
      "root@47.94.102.250",
      "python3",
      "-",
    ],
    {
      input: remoteScript,
      encoding: "utf8",
      shell: false,
      timeout: remoteTokenTimeoutMs,
    }
  );
  if (result.error?.code === "ETIMEDOUT") {
    console.warn(`Production admin browser smoke token lookup timed out after ${remoteTokenTimeoutMs}ms; skipping authenticated browser smoke.`);
    return "";
  }
  if (result.status !== 0) {
    if (result.stderr) {
      console.warn(String(result.stderr).trim());
    }
    return "";
  }
  return String(result.stdout || "").trim();
}

function main() {
  const token = process.env.YUNXI_ADMIN_API_TOKEN || process.env.ADMIN_API_TOKEN || getTokenFromRemoteEnv();
  if (!token) {
    console.log("Production admin browser smoke blocked: no admin token available.");
    process.exit(1);
  }
  const useNodeNpmCli = process.platform === "win32" && fs.existsSync(npmCliPath);
  const executable = useNodeNpmCli ? process.execPath : npmCommand;
  const args = useNodeNpmCli ? [npmCliPath, "run", "smoke:production-navigation"] : ["run", "smoke:production-navigation"];
  const result = spawnSync(executable, args, {
    cwd: adminRoot,
    encoding: "utf8",
    shell: false,
    timeout: browserSmokeTimeoutMs,
    env: {
      ...process.env,
      YUNXI_ADMIN_API_TOKEN: token,
    },
  });
  process.stdout.write(result.stdout || "");
  process.stderr.write(result.stderr || "");
  if (result.error) {
    console.error(result.error.message);
    process.exit(1);
  }
  process.exit(result.status ?? 1);
}

main();
