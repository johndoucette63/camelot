import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { NotificationSink } from "../../types";

// Stub the services module before importing the component.
vi.mock("../../services/settings", () => ({
  fetchNotificationSinks: vi.fn(),
  createNotificationSink: vi.fn(),
  updateNotificationSink: vi.fn(),
  testNotificationSink: vi.fn(),
  deleteNotificationSink: vi.fn(),
}));

import NotificationSinkForm from "../NotificationSinkForm";
import {
  fetchNotificationSinks,
  createNotificationSink,
  updateNotificationSink,
  testNotificationSink,
  deleteNotificationSink,
} from "../../services/settings";

const mockedFetch = vi.mocked(fetchNotificationSinks);
const mockedCreate = vi.mocked(createNotificationSink);
const mockedUpdate = vi.mocked(updateNotificationSink);
const mockedTest = vi.mocked(testNotificationSink);
const mockedDelete = vi.mocked(deleteNotificationSink);

function existingSink(): NotificationSink {
  return {
    id: 7,
    type: "home_assistant",
    name: "HA",
    enabled: true,
    endpoint_masked: "http://homeassistant.holygrail/api/webhook/***",
    min_severity: "warning",
    created_at: "2026-04-10T12:00:00Z",
    updated_at: "2026-04-10T12:00:00Z",
  };
}

beforeEach(() => {
  mockedFetch.mockReset();
  mockedCreate.mockReset();
  mockedUpdate.mockReset();
  mockedTest.mockReset();
  mockedDelete.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("NotificationSinkForm", () => {
  it("renders the masked endpoint as a password input when editing an existing sink", async () => {
    mockedFetch.mockResolvedValue([existingSink()]);

    render(<NotificationSinkForm />);

    // Wait for the draft to populate from the fetched sink.
    await waitFor(() => {
      const nameInput = screen.getByDisplayValue("HA") as HTMLInputElement;
      expect(nameInput).toBeTruthy();
    });

    const endpointInput = screen.getByDisplayValue(
      "http://homeassistant.holygrail/api/webhook/***",
    ) as HTMLInputElement;
    expect(endpointInput).toBeTruthy();
    expect(endpointInput.type).toBe("password");
  });

  it("updates without sending endpoint when the masked value is unchanged", async () => {
    mockedFetch.mockResolvedValue([existingSink()]);
    mockedUpdate.mockResolvedValue({} as any);

    render(<NotificationSinkForm />);

    await waitFor(() => {
      expect(screen.getByDisplayValue("HA")).toBeTruthy();
    });

    // Click the Update button without touching the endpoint field.
    const updateBtn = screen.getByRole("button", { name: /update/i });
    fireEvent.click(updateBtn);

    await waitFor(() => {
      expect(mockedUpdate).toHaveBeenCalled();
    });

    const [id, payload] = mockedUpdate.mock.calls[0]!;
    expect(id).toBe(7);
    expect(payload).toEqual({
      name: "HA",
      enabled: true,
      min_severity: "warning",
    });
    expect((payload as any).endpoint).toBeUndefined();
  });

  it("updates with endpoint when the masked value has been replaced", async () => {
    mockedFetch.mockResolvedValue([existingSink()]);
    mockedUpdate.mockResolvedValue({} as any);

    render(<NotificationSinkForm />);

    await waitFor(() => {
      expect(screen.getByDisplayValue("HA")).toBeTruthy();
    });

    const endpointInput = screen.getByDisplayValue(
      "http://homeassistant.holygrail/api/webhook/***",
    ) as HTMLInputElement;
    fireEvent.change(endpointInput, {
      target: { value: "http://new-ha/api/webhook/NEW-TOKEN" },
    });

    const updateBtn = screen.getByRole("button", { name: /update/i });
    fireEvent.click(updateBtn);

    await waitFor(() => {
      expect(mockedUpdate).toHaveBeenCalled();
    });

    const [id, payload] = mockedUpdate.mock.calls[0]!;
    expect(id).toBe(7);
    expect(payload).toMatchObject({
      name: "HA",
      enabled: true,
      min_severity: "warning",
      endpoint: "http://new-ha/api/webhook/NEW-TOKEN",
    });
  });

  it("shows the success banner after a successful Test click", async () => {
    mockedFetch.mockResolvedValue([existingSink()]);
    mockedTest.mockResolvedValue({
      ok: true,
      status_code: 200,
      latency_ms: 42,
    });

    render(<NotificationSinkForm />);

    await waitFor(() => {
      expect(screen.getByDisplayValue("HA")).toBeTruthy();
    });

    const testBtn = screen.getByRole("button", { name: /^test$/i });
    fireEvent.click(testBtn);

    await waitFor(() => {
      expect(mockedTest).toHaveBeenCalledWith(7);
    });
    await waitFor(() => {
      expect(screen.getByText(/Delivered in 42 ms/i)).toBeTruthy();
    });
  });

  it("shows the failure banner after a failed Test click", async () => {
    mockedFetch.mockResolvedValue([existingSink()]);
    mockedTest.mockResolvedValue({ ok: false, error: "boom" });

    render(<NotificationSinkForm />);

    await waitFor(() => {
      expect(screen.getByDisplayValue("HA")).toBeTruthy();
    });

    const testBtn = screen.getByRole("button", { name: /^test$/i });
    fireEvent.click(testBtn);

    await waitFor(() => {
      expect(mockedTest).toHaveBeenCalledWith(7);
    });
    await waitFor(() => {
      expect(screen.getByText(/Failed: boom/i)).toBeTruthy();
    });
  });
});
