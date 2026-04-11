import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { RuleMute } from "../../types";

vi.mock("../../services/settings", () => ({
  fetchMutes: vi.fn(),
  cancelMute: vi.fn(),
}));

import MuteList from "../MuteList";
import { fetchMutes, cancelMute } from "../../services/settings";

const mockedFetch = vi.mocked(fetchMutes);
const mockedCancel = vi.mocked(cancelMute);

function makeMute(overrides: Partial<RuleMute> = {}): RuleMute {
  // expires 1 hour from now in UTC
  const expires = new Date(Date.now() + 3600 * 1000).toISOString();
  return {
    id: 1,
    rule_id: "disk_high",
    rule_name: "Disk usage high",
    target_type: "device",
    target_id: 42,
    target_label: "nas",
    created_at: new Date().toISOString(),
    expires_at: expires,
    remaining_seconds: 3600,
    note: "rebooting nas for upgrade",
    ...overrides,
  };
}

beforeEach(() => {
  mockedFetch.mockReset();
  mockedCancel.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("MuteList", () => {
  it("renders active mutes with rule name, target label, note, and remaining time", async () => {
    mockedFetch.mockResolvedValue([
      makeMute({
        target_label: "holygrail",
        note: "maintenance window",
      }),
    ]);

    render(<MuteList />);

    await waitFor(() => {
      expect(screen.getByText(/Disk usage high/)).toBeTruthy();
    });
    expect(screen.getByText(/holygrail/)).toBeTruthy();
    expect(screen.getByText(/maintenance window/)).toBeTruthy();
    // Some "expires in ..." text rendered — exact formatting depends on
    // clock, so just assert the prefix.
    expect(screen.getByText(/expires in/i)).toBeTruthy();
  });

  it("calls cancelMute and removes the row when Cancel is clicked", async () => {
    mockedFetch.mockResolvedValue([
      makeMute({ id: 1 }),
      makeMute({
        id: 2,
        rule_name: "Service down",
        target_label: "plex",
        note: null,
      }),
    ]);
    mockedCancel.mockResolvedValue(undefined);

    render(<MuteList />);

    await waitFor(() => {
      expect(screen.getByText(/Disk usage high/)).toBeTruthy();
    });
    expect(screen.getByText(/Service down/)).toBeTruthy();

    const cancelButtons = screen.getAllByRole("button", { name: /cancel/i });
    // Click the first row's cancel button (id=1 — Disk usage high).
    fireEvent.click(cancelButtons[0]!);

    await waitFor(() => {
      expect(mockedCancel).toHaveBeenCalledWith(1);
    });

    // After cancellation the first row is removed; the second is still there.
    await waitFor(() => {
      expect(screen.queryByText(/Disk usage high/)).toBeNull();
    });
    expect(screen.getByText(/Service down/)).toBeTruthy();
  });

  it("shows 'No active mutes.' when the list is empty", async () => {
    mockedFetch.mockResolvedValue([]);

    render(<MuteList />);

    await waitFor(() => {
      expect(screen.getByText(/No active mutes/i)).toBeTruthy();
    });
  });
});
