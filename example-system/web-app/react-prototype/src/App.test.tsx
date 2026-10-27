import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";

const requests = [
  { id: "REQ-101", title: "Replace worn drive belt", type: "repair", priority: "standard", status: "open", serialNumber: "EQ-2048", createdAt: "2026-10-20T09:00:00.000Z" },
  { id: "REQ-102", title: "Inspect control panel", type: "inspection", priority: "urgent", status: "in-progress", justification: "Inspection is needed before scheduled operation.", createdAt: "2026-10-21T09:00:00.000Z" }
];

function mount() {
  return render(<BrowserRouter><App /></BrowserRouter>);
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => requests }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("request workflow", () => {
  it("loads the fixture and filters by text", async () => {
    const user = userEvent.setup();
    mount();
    expect(await screen.findByText(/Replace worn drive belt/)).toBeInTheDocument();
    await user.type(screen.getByTestId("request-filter"), "control");
    await waitFor(() => expect(screen.queryByText(/Replace worn drive belt/)).not.toBeInTheDocument());
    expect(screen.getByText(/Inspect control panel/)).toBeInTheDocument();
  });

  it("requires a serial number for repairs and a long reason for urgent work", async () => {
    const user = userEvent.setup();
    mount();
    await user.click(screen.getByRole("link", { name: "New request" }));
    await user.type(screen.getByTestId("request-title"), "Repair pump");
    await user.selectOptions(screen.getByTestId("request-type"), "repair");
    await user.selectOptions(screen.getByTestId("request-priority"), "urgent");
    await user.type(screen.getByTestId("request-justification"), "Needs attention");
    await user.click(screen.getByTestId("request-submit"));
    expect(screen.getByTestId("validation-summary")).toHaveTextContent("serial number");
    expect(screen.getByTestId("validation-summary")).toHaveTextContent("20 characters");
    await user.type(screen.getByTestId("request-serial-number"), "EQ-555");
    await user.clear(screen.getByTestId("request-justification"));
    await user.type(screen.getByTestId("request-justification"), "Urgent repair before next shift");
    await user.click(screen.getByTestId("request-submit"));
    expect(await screen.findByTestId("form-success")).toHaveTextContent("Request created");
  });
});
