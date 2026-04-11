import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Threshold } from "../../types";

// Stub the services module before importing the component.
vi.mock("../../services/settings", () => ({
  fetchThresholds: vi.fn(),
  updateThreshold: vi.fn(),
}));

import ThresholdForm from "../ThresholdForm";
import { fetchThresholds, updateThreshold } from "../../services/settings";

const mockedFetch = vi.mocked(fetchThresholds);
const mockedUpdate = vi.mocked(updateThreshold);

function makeThresholds(): Threshold[] {
  return [
    {
      key: "cpu_percent",
      value: 80,
      unit: "%",
      default_value: 80,
      min_value: 10,
      max_value: 100,
      updated_at: "2026-04-10T12:00:00Z",
    },
    {
      key: "disk_percent",
      value: 85,
      unit: "%",
      default_value: 85,
      min_value: 10,
      max_value: 100,
      updated_at: "2026-04-10T12:00:00Z",
    },
    {
      key: "service_down_minutes",
      value: 5,
      unit: "minutes",
      default_value: 5,
      min_value: 1,
      max_value: 1440,
      updated_at: "2026-04-10T12:00:00Z",
    },
    {
      key: "device_offline_minutes",
      value: 10,
      unit: "minutes",
      default_value: 10,
      min_value: 1,
      max_value: 1440,
      updated_at: "2026-04-10T12:00:00Z",
    },
  ];
}

beforeEach(() => {
  mockedFetch.mockReset();
  mockedUpdate.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("ThresholdForm", () => {
  it("renders all four threshold rows after load", async () => {
    mockedFetch.mockResolvedValue(makeThresholds());

    render(<ThresholdForm />);

    await waitFor(() => {
      expect(screen.getByText("cpu_percent")).toBeTruthy();
    });
    expect(screen.getByText("disk_percent")).toBeTruthy();
    expect(screen.getByText("service_down_minutes")).toBeTruthy();
    expect(screen.getByText("device_offline_minutes")).toBeTruthy();

    // Each row has its input populated with the current value.
    const cpuInput = screen.getByLabelText(
      /value for cpu_percent/i,
    ) as HTMLInputElement;
    expect(cpuInput.value).toBe("80");
  });

  it("shows inline validation error for out-of-range value and does not call updateThreshold", async () => {
    mockedFetch.mockResolvedValue(makeThresholds());

    render(<ThresholdForm />);
    await waitFor(() => {
      expect(screen.getByText("cpu_percent")).toBeTruthy();
    });

    const cpuInput = screen.getByLabelText(
      /value for cpu_percent/i,
    ) as HTMLInputElement;
    fireEvent.change(cpuInput, { target: { value: "150" } });

    // Find the Save button in the same row (it's enabled once dirty).
    const saveButtons = screen.getAllByRole("button", { name: /save/i });
    // First row is cpu_percent (thresholds rendered in order).
    fireEvent.click(saveButtons[0]!);

    await waitFor(() => {
      expect(screen.getByText(/between 10 and 100/i)).toBeTruthy();
    });
    expect(mockedUpdate).not.toHaveBeenCalled();
  });

  it("calls updateThreshold with a valid value and re-renders the new value", async () => {
    mockedFetch.mockResolvedValue(makeThresholds());
    mockedUpdate.mockResolvedValue({
      key: "cpu_percent",
      value: 90,
      unit: "%",
      default_value: 80,
      min_value: 10,
      max_value: 100,
      updated_at: "2026-04-10T12:05:00Z",
    });

    render(<ThresholdForm />);
    await waitFor(() => {
      expect(screen.getByText("cpu_percent")).toBeTruthy();
    });

    const cpuInput = screen.getByLabelText(
      /value for cpu_percent/i,
    ) as HTMLInputElement;
    fireEvent.change(cpuInput, { target: { value: "90" } });

    const saveButtons = screen.getAllByRole("button", { name: /save/i });
    fireEvent.click(saveButtons[0]!);

    await waitFor(() => {
      expect(mockedUpdate).toHaveBeenCalledWith("cpu_percent", 90);
    });

    // After the resolved promise, the input reflects the returned value.
    await waitFor(() => {
      const refreshed = screen.getByLabelText(
        /value for cpu_percent/i,
      ) as HTMLInputElement;
      expect(refreshed.value).toBe("90");
    });
  });

  it("shows an inline error when the API returns a 400", async () => {
    mockedFetch.mockResolvedValue(makeThresholds());
    mockedUpdate.mockRejectedValue(
      new Error("value must be between 10.0 and 100.0"),
    );

    render(<ThresholdForm />);
    await waitFor(() => {
      expect(screen.getByText("cpu_percent")).toBeTruthy();
    });

    const cpuInput = screen.getByLabelText(
      /value for cpu_percent/i,
    ) as HTMLInputElement;
    fireEvent.change(cpuInput, { target: { value: "95" } });

    const saveButtons = screen.getAllByRole("button", { name: /save/i });
    fireEvent.click(saveButtons[0]!);

    await waitFor(() => {
      expect(screen.getByText(/between 10\.0 and 100\.0/i)).toBeTruthy();
    });
    expect(mockedUpdate).toHaveBeenCalledWith("cpu_percent", 95);
  });
});
