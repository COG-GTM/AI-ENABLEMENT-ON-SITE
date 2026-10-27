import { defineConfig } from "@playwright/test";

const target = process.env.APP_TARGET === "angular" ? "angular" : "react";
const port = target === "angular" ? 4200 : 4173;
const baseURL = process.env.BASE_URL ?? `http://127.0.0.1:${port}`;
const appPath = target === "angular" ? "../angular-app" : "../react-prototype";
const command = target === "angular"
  ? `npm --prefix ${appPath} run start:e2e`
  : `npm --prefix ${appPath} run dev -- --host 127.0.0.1 --port ${port} --strictPort`;

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  retries: 0,
  reporter: "list",
  use: {
    baseURL,
    video: "on",
    trace: "retain-on-failure",
    launchOptions: process.env.BROWSER_CHANNEL === "chrome" ? { channel: "chrome" } : {}
  },
  webServer: {
    command,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000
  }
});
