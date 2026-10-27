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

  await page.getByTestId("request-title").fill("   ");
  await page.getByTestId("request-type").selectOption("repair");
  await page.getByTestId("request-priority").selectOption("urgent");
  await page.getByTestId("request-serial-number").fill("   ");
  await page.getByTestId("request-justification").fill(" 123456789012345678 ");
  await page.getByTestId("request-submit").click();
  await expect(page.getByTestId("validation-summary")).toContainText("request title");
  await expect(page.getByTestId("validation-summary")).toContainText("serial number");
  await expect(page.getByTestId("validation-summary")).toContainText("at least 20 characters");
  if (process.env.APP_TARGET === "angular") {
    const formUrl = page.url();
    await page.getByRole("link", { name: "Enter the equipment serial number." }).click();
    await expect(page).toHaveURL(formUrl);
    await expect(page.getByTestId("request-serial-number")).toBeFocused();
  } else {
    await expect(page).toHaveURL(/\/requests\/new$/);
    await expect(page.getByTestId("request-title")).toBeFocused();
  }

  await page.getByTestId("request-title").fill(" Replace lift motor ");
  await page.getByTestId("request-justification").fill(" Urgent work required before the next shift. ");
  await page.getByTestId("request-submit").click();
  await expect(page.getByTestId("validation-summary")).toContainText("serial number");

  const report = await new AxeBuilder({ page }).analyze();
  console.log(`axe violations (${process.env.APP_TARGET ?? "react"}): ${JSON.stringify(report.violations.map(({ id, impact }) => ({ id, impact })))}`);
  const critical = report.violations.filter((violation) => violation.impact === "critical");
  expect(critical, "critical accessibility violations").toEqual([]);

  await page.getByTestId("request-serial-number").fill(" EQ-7788 ");
  await page.getByTestId("request-submit").click();
  await expect(page.getByTestId("form-success")).toBeVisible();
  await page.getByRole("link", { name: "Requests", exact: true }).click();
  await page.getByTestId("request-filter").fill("lift motor");
  await expect(page.getByText(/Replace lift motor/)).toBeVisible();
  await page.getByText(/Replace lift motor/).click();
  await expect(page.getByTestId("request-detail")).toContainText("Replace lift motor");
  await expect(page.getByTestId("request-detail")).toContainText("EQ-7788");

  await testInfo.attach("browser-console-errors", { body: consoleErrors.join("\n") || "none", contentType: "text/plain" });
});

test("submitting the blank reset form replaces success with validation", async ({ page }) => {
  await page.goto("/requests/new");
  await page.getByTestId("request-title").fill("Repair pump");
  await page.getByTestId("request-type").selectOption("repair");
  await page.getByTestId("request-serial-number").fill("EQ-7788");
  await page.getByTestId("request-submit").click();
  await expect(page.getByTestId("form-success")).toBeVisible();

  await page.getByTestId("request-submit").click();

  await expect(page.getByTestId("validation-summary")).toBeVisible();
  await expect(page.getByTestId("validation-summary")).toContainText("request title");
  await expect(page.getByTestId("form-success")).toHaveCount(0);
});

test("captures the static UX concept", async ({ page }) => {
  await page.goto(pathToFileURL(mockupPath).href);
  await expect(page.getByRole("heading", { name: "New service request" })).toBeVisible();
  await page.screenshot({ path: path.join(evidenceDir, "request-form-mockup.png"), fullPage: true });
});
