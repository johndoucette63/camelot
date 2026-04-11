import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { RecommendationsResponse } from "../../types";

// Stub the services module before importing the component.
vi.mock("../../services/recommendations", () => ({
  fetchRecommendations: vi.fn(),
}));

import RecommendationsPanel from "../RecommendationsPanel";
import { fetchRecommendations } from "../../services/recommendations";

const mockedFetch = vi.mocked(fetchRecommendations);

beforeEach(() => {
  mockedFetch.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("RecommendationsPanel", () => {
  it("shows an All clear empty state when there are no active alerts", async () => {
    const empty: RecommendationsResponse = {
      active: [],
      counts: { critical: 0, warning: 0, info: 0 },
      ai_narrative: null,
    };
    mockedFetch.mockResolvedValue(empty);

    render(<RecommendationsPanel />);

    await waitFor(() => {
      expect(screen.getByText(/All clear/i)).toBeTruthy();
    });
    // Counts chips still present, all zero.
    expect(screen.getByText(/Critical: 0/)).toBeTruthy();
    expect(screen.getByText(/Warning: 0/)).toBeTruthy();
    expect(screen.getByText(/Info: 0/)).toBeTruthy();
    // The AI narrative banner must NOT be rendered when ai_narrative is null.
    expect(screen.queryByLabelText(/AI-assisted narrative/i)).toBeNull();
    expect(screen.queryByText(/AI-assisted/)).toBeNull();
  });

  it("renders active alerts grouped by severity with correct counts", async () => {
    const populated: RecommendationsResponse = {
      active: [
        {
          id: 1,
          rule_id: "service_down",
          rule_name: "Service down",
          severity: "critical",
          target_type: "service",
          target_id: 10,
          target_label: "Plex (HOLYGRAIL)",
          message: "Plex on HOLYGRAIL has been down for ≥ 5 minutes",
          state: "active",
          source: "rule",
          suppressed: false,
          created_at: "2026-04-10T12:00:00Z",
          acknowledged_at: null,
          resolved_at: null,
          resolution_source: null,
        },
        {
          id: 2,
          rule_id: "disk_high",
          rule_name: "Disk usage high",
          severity: "warning",
          target_type: "device",
          target_id: 20,
          target_label: "nas",
          message: "nas disk at 97%",
          state: "active",
          source: "rule",
          suppressed: false,
          created_at: "2026-04-10T11:59:00Z",
          acknowledged_at: null,
          resolved_at: null,
          resolution_source: null,
        },
        {
          id: 3,
          rule_id: "ollama_unavailable",
          rule_name: "Ollama unavailable",
          severity: "info",
          target_type: "system",
          target_id: null,
          target_label: null,
          message: "Ollama is not reachable",
          state: "active",
          source: "rule",
          suppressed: false,
          created_at: "2026-04-10T11:58:00Z",
          acknowledged_at: null,
          resolved_at: null,
          resolution_source: null,
        },
      ],
      counts: { critical: 1, warning: 1, info: 1 },
      ai_narrative: null,
    };
    mockedFetch.mockResolvedValue(populated);

    render(<RecommendationsPanel />);

    await waitFor(() => {
      expect(screen.getByText("Plex (HOLYGRAIL)")).toBeTruthy();
    });
    expect(screen.getByText("nas")).toBeTruthy();
    expect(screen.getByText(/Ollama is not reachable/)).toBeTruthy();

    expect(screen.getByText(/Critical: 1/)).toBeTruthy();
    expect(screen.getByText(/Warning: 1/)).toBeTruthy();
    expect(screen.getByText(/Info: 1/)).toBeTruthy();

    // Group headings.
    expect(screen.getByText("Critical")).toBeTruthy();
    expect(screen.getByText("Warning")).toBeTruthy();
    expect(screen.getByText("Info")).toBeTruthy();

    // Empty-state text must NOT appear when there are active alerts.
    expect(screen.queryByText(/All clear/i)).toBeNull();
  });

  it("does not render the AI narrative banner when ai_narrative is null", async () => {
    const withAlertsNoNarrative: RecommendationsResponse = {
      active: [
        {
          id: 99,
          rule_id: "disk_high",
          rule_name: "Disk usage high",
          severity: "warning",
          target_type: "device",
          target_id: 1,
          target_label: "torrentbox",
          message: "torrentbox disk at 95%",
          state: "active",
          source: "rule",
          suppressed: false,
          created_at: "2026-04-10T12:00:00Z",
          acknowledged_at: null,
          resolved_at: null,
          resolution_source: null,
        },
      ],
      counts: { critical: 0, warning: 1, info: 0 },
      ai_narrative: null,
    };
    mockedFetch.mockResolvedValue(withAlertsNoNarrative);

    render(<RecommendationsPanel />);

    await waitFor(() => {
      expect(screen.getByText("torrentbox")).toBeTruthy();
    });
    expect(screen.queryByLabelText(/AI-assisted narrative/i)).toBeNull();
    expect(screen.queryByText(/AI-assisted/)).toBeNull();
  });

  it("renders the AI-assisted banner with badge when ai_narrative is non-null", async () => {
    const withNarrative: RecommendationsResponse = {
      active: [
        {
          id: 1,
          rule_id: "disk_high",
          rule_name: "Disk usage high",
          severity: "warning",
          target_type: "device",
          target_id: 1,
          target_label: "nas",
          message: "nas disk at 97%",
          state: "active",
          source: "rule",
          suppressed: false,
          created_at: "2026-04-10T12:00:00Z",
          acknowledged_at: null,
          resolved_at: null,
          resolution_source: null,
        },
      ],
      counts: { critical: 0, warning: 1, info: 0 },
      ai_narrative: {
        text: "Two correlated disk pressure signals on the NAS cluster.",
        generated_at: "2026-04-10T12:00:00Z",
        source: "ollama",
      },
    };
    mockedFetch.mockResolvedValue(withNarrative);

    render(<RecommendationsPanel />);

    await waitFor(() => {
      expect(screen.getByLabelText(/AI-assisted narrative/i)).toBeTruthy();
    });
    expect(screen.getByText(/AI-assisted/)).toBeTruthy();
    expect(
      screen.getByText(/correlated disk pressure signals/i),
    ).toBeTruthy();
  });

  it("hides the AI-assisted banner when ai_narrative is null even with active alerts", async () => {
    const withoutNarrative: RecommendationsResponse = {
      active: [
        {
          id: 2,
          rule_id: "service_down",
          rule_name: "Service down",
          severity: "critical",
          target_type: "service",
          target_id: 10,
          target_label: "Plex",
          message: "Plex down",
          state: "active",
          source: "rule",
          suppressed: false,
          created_at: "2026-04-10T12:00:00Z",
          acknowledged_at: null,
          resolved_at: null,
          resolution_source: null,
        },
      ],
      counts: { critical: 1, warning: 0, info: 0 },
      ai_narrative: null,
    };
    mockedFetch.mockResolvedValue(withoutNarrative);

    render(<RecommendationsPanel />);

    await waitFor(() => {
      expect(screen.getByText("Plex")).toBeTruthy();
    });
    expect(screen.queryByLabelText(/AI-assisted narrative/i)).toBeNull();
    expect(screen.queryByText(/AI-assisted/)).toBeNull();
  });
});
