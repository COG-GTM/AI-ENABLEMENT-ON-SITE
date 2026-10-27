import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const evidenceDir = path.resolve("../evidence");
const mockupPath = fileURLToPath(new URL("../../mockups/request-form-v2.html", import.meta.url));

test("create, filter, open details, and validate a service request", async ({ page }, testInfo) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await mkdir(evidenceDir, { recursive: true });
  await page.goto("/requests/new");
  await expect(page.getByTestId("request-form")).toBeVisible();
  await page.screenshot({ path: path.join(evidenceDir, `${process.env.APP_TARGET ?? "react"}-form${process.env.SCREENSHOT_SUFFIX ?? ""}.png`), fullPage: true });

  await page.getByTestId("request-title").fill("Replace lift motor");
  await page.getByTestId("request-type").selectOption("repair");
  await page.getByTestId("request-priority").selectOption("urgent");
  await page.getByTestId("request-justification").fill("Too short");
  await page.getByTestId("request-submit").click();
  await expect(page.getByTestId("validation-summary")).toContainText("serial number");
  await expect(page.getByTestId("validation-summary")).toContainText("at least 20 characters");

  await page.getByTestId("request-justification").fill("Urgent work required before the next shift.");
  await page.getByTestId("request-submit").click();
  await expect(page.getByTestId("validation-summary")).toContainText("serial number");

  const report = await new AxeBuilder({ page }).analyze();
  console.log(`axe violations (${process.env.APP_TARGET ?? "react"}): ${JSON.stringify(report.violations.map(({ id, impact }) => ({ id, impact })))}`);
  const critical = report.violations.filter((violation) => violation.impact === "critical");
  expect(critical, "critical accessibility violations").toEqual([]);

  await page.getByTestId("request-serial-number").fill("EQ-7788");
  await page.getByTestId("request-submit").click();
  await expect(page.getByTestId("form-success")).toBeVisible();
  await page.getByRole("link", { name: "Requests", exact: true }).click();
  await page.getByTestId("request-filter").fill("lift motor");
  await expect(page.getByText(/Replace lift motor/)).toBeVisible();
  await page.getByText(/Replace lift motor/).click();
  await expect(page.getByTestId("request-detail")).toContainText("EQ-7788");

  await testInfo.attach("browser-console-errors", { body: consoleErrors.join("\n") || "none", contentType: "text/plain" });
});

test("captures the static UX concept", async ({ page }) => {
  await page.goto(pathToFileURL(mockupPath).href);
  await expect(page.getByRole("heading", { name: "New service request" })).toBeVisible();
  await page.screenshot({ path: path.join(evidenceDir, "request-form-mockup.png"), fullPage: true });
});
