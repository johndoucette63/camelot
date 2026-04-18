import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Stub the services module before importing the component under test.
vi.mock("../../services/settings", () => ({
  createNotificationSink: vi.fn(),
  fetchAvailableHaServices: vi.fn(),
}));

import HomeAssistantSinkForm from "../HomeAssistantSinkForm";
import {
  createNotificationSink,
  fetchAvailableHaServices,
} from "../../services/settings";

const mockedCreate = vi.mocked(createNotificationSink);
const mockedFetch = vi.mocked(fetchAvailableHaServices);

beforeEach(() => {
  mockedCreate.mockReset();
  mockedFetch.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("HomeAssistantSinkForm", () => {
  it("populates the service dropdown from the services endpoint", async () => {
    mockedFetch.mockResolvedValue({
      ok: true,
      services: ["mobile_app_pixel9", "mobile_app_ipad"],
    });

    render(<HomeAssistantSinkForm />);

    await waitFor(() => {
      expect(screen.getByTestId("ha-service-select")).toBeTruthy();
    });
    // Both services appear as options (prefixed with notify. for display).
    expect(screen.getByText(/notify\.mobile_app_pixel9/)).toBeTruthy();
    expect(screen.getByText(/notify\.mobile_app_ipad/)).toBeTruthy();
  });

  it("falls back to free-text when the service endpoint returns 409", async () => {
    mockedFetch.mockResolvedValue({
      ok: false,
      services: [],
      detail: "Home Assistant is not currently reachable",
    });

    render(<HomeAssistantSinkForm />);

    await waitFor(() => {
      expect(screen.getByTestId("ha-service-text")).toBeTruthy();
    });
    expect(screen.getByTestId("ha-service-fallback-reason")).toBeTruthy();
    expect(
      screen.getByText(/home assistant is not currently reachable/i),
    ).toBeTruthy();
  });

  it("defaults min_severity to 'critical'", async () => {
    mockedFetch.mockResolvedValue({
      ok: true,
      services: ["mobile_app_pixel9"],
    });

    render(<HomeAssistantSinkForm />);

    await waitFor(() => {
      expect(screen.getByTestId("ha-service-select")).toBeTruthy();
    });

    const severitySelect = screen.getByLabelText(
      /min severity/i,
    ) as HTMLSelectElement;
    expect(severitySelect.value).toBe("critical");
  });

  it("posts with the canonical (bare) service name on save", async () => {
    mockedFetch.mockResolvedValue({
      ok: true,
      services: ["mobile_app_pixel9"],
    });
    mockedCreate.mockResolvedValue({} as unknown);

    render(<HomeAssistantSinkForm />);

    await waitFor(() => {
      expect(screen.getByTestId("ha-service-select")).toBeTruthy();
    });

    // Fill in required name.
    const nameInput = screen.getByLabelText(/^name$/i);
    fireEvent.change(nameInput, { target: { value: "Phone (HA push)" } });

    // Default service is mobile_app_pixel9 from the dropdown.
    const saveBtn = screen.getByRole("button", { name: /save/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(mockedCreate).toHaveBeenCalled();
    });

    const payload = mockedCreate.mock.calls[0]![0];
    expect(payload).toMatchObject({
      type: "home_assistant",
      name: "Phone (HA push)",
      endpoint: "mobile_app_pixel9", // bare suffix, no `notify.` prefix
      min_severity: "critical",
      enabled: true,
    });
  });

  it("strips a 'notify.' prefix from free-text entry on save", async () => {
    mockedFetch.mockResolvedValue({
      ok: false,
      services: [],
      detail: "HA unreachable",
    });
    mockedCreate.mockResolvedValue({} as unknown);

    render(<HomeAssistantSinkForm />);

    await waitFor(() => {
      expect(screen.getByTestId("ha-service-text")).toBeTruthy();
    });

    const nameInput = screen.getByLabelText(/^name$/i);
    fireEvent.change(nameInput, { target: { value: "Phone" } });

    const svcInput = screen.getByTestId("ha-service-text");
    fireEvent.change(svcInput, {
      target: { value: "notify.mobile_app_pixel9" },
    });

    const saveBtn = screen.getByRole("button", { name: /save/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(mockedCreate).toHaveBeenCalled();
    });

    const payload = mockedCreate.mock.calls[0]![0];
    expect(payload.endpoint).toBe("mobile_app_pixel9");
  });
});
