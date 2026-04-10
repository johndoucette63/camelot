import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ContainerList } from "../ContainerList";
import type { ContainerState } from "../../types";

const running = [
  { id: "abc123", name: "plex", image: "linuxserver/plex", status: "running", ports: {}, uptime: "", created: "" },
  { id: "def456", name: "grafana", image: "grafana/grafana", status: "running", ports: {}, uptime: "", created: "" },
];

const stopped = [
  { id: "ghi789", name: "old-service", image: "some/image", status: "exited", ports: {}, uptime: "", created: "" },
];

describe("ContainerList", () => {
  it("renders running containers list", () => {
    const data: ContainerState = { running, stopped: [], refreshed_at: "2026-04-09T12:00:00Z", socket_error: false };
    render(<ContainerList data={data} />);
    expect(screen.getByText("plex")).toBeTruthy();
    expect(screen.getByText("grafana")).toBeTruthy();
    expect(screen.getByText(/Running \(2\)/)).toBeTruthy();
  });

  it("renders stopped containers separately", () => {
    const data: ContainerState = { running, stopped, refreshed_at: "2026-04-09T12:00:00Z", socket_error: false };
    render(<ContainerList data={data} />);
    expect(screen.getByText(/Running \(2\)/)).toBeTruthy();
    expect(screen.getByText(/Stopped \(1\)/)).toBeTruthy();
    expect(screen.getByText("old-service")).toBeTruthy();
  });

  it("shows staleness warning banner when socket_error is true", () => {
    const data: ContainerState = { running, stopped: [], refreshed_at: "2026-04-09T10:00:00Z", socket_error: true };
    render(<ContainerList data={data} />);
    expect(screen.getByText(/Docker socket unavailable/)).toBeTruthy();
  });

  it("shows empty state when no containers", () => {
    const data: ContainerState = { running: [], stopped: [], refreshed_at: null, socket_error: true };
    render(<ContainerList data={data} />);
    expect(screen.getByText(/No container data available/)).toBeTruthy();
  });
});
