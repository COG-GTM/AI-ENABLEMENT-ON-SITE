import { spawnSync } from "node:child_process";
import process from "node:process";

const requestedTarget = process.argv[2];
const target = requestedTarget === "angular-ux" ? "angular" : requestedTarget;
if (!["react", "angular"].includes(target)) {
  console.error("Choose react, angular, or angular-ux.");
  process.exit(2);
}
const command = process.platform === "win32" ? "npx.cmd" : "npx";
const result = spawnSync(command, ["playwright", "test"], {
  stdio: "inherit",
  env: { ...process.env, APP_TARGET: target, ...(requestedTarget === "angular-ux" ? { SCREENSHOT_SUFFIX: "-ux" } : {}) }
});
process.exit(result.status ?? 1);
