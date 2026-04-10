import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { DashboardSummary } from "../DashboardSummary";

const mockSummary = {
  total: 12,
  healthy: 10,
  degraded: 1,
  down: 1,
  unchecked: 0,
  hosts: [
    { label: "HOLYGRAIL", total: 6, healthy: 6, degraded: 0, down: 0 },
    { label: "Torrentbox", total: 4, healthy: 3, degraded: 1, down: 0 },
  ],
  hosts_unreachable: [],
};

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("DashboardSummary", () => {
  it("renders N/M healthy headline", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => mockSummary,
    } as Response);

    render(<DashboardSummary />);
    await waitFor(() => {
      expect(screen.getByText(/10 \/ 12 services healthy/)).toBeTruthy();
    });
  });

  it("renders color-coded status pills", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => mockSummary,
    } as Response);

    render(<DashboardSummary />);
    await waitFor(() => {
      expect(screen.getByText(/10 healthy/)).toBeTruthy();
      expect(screen.getAllByText(/degraded/).length).toBeGreaterThan(0);
      expect(screen.getByText(/1 down/)).toBeTruthy();
    });
  });

  it("renders per-host breakdown", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => mockSummary,
    } as Response);

    render(<DashboardSummary />);
    await waitFor(() => {
      expect(screen.getByText("HOLYGRAIL")).toBeTruthy();
      expect(screen.getByText("Torrentbox")).toBeTruthy();
    });
  });

  it("renders unreachable hosts alert", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({ ...mockSummary, hosts_unreachable: ["NAS"] }),
    } as Response);

    render(<DashboardSummary />);
    await waitFor(() => {
      expect(screen.getByText(/Host unreachable/)).toBeTruthy();
      expect(screen.getByText(/NAS/)).toBeTruthy();
    });
  });
});
