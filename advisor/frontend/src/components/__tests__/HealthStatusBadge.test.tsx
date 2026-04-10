import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { HealthStatusBadge } from "../HealthStatusBadge";

describe("HealthStatusBadge", () => {
  it("renders green as Healthy", () => {
    render(<HealthStatusBadge status="green" />);
    expect(screen.getByText("Healthy")).toBeTruthy();
  });

  it("renders yellow as Degraded", () => {
    render(<HealthStatusBadge status="yellow" />);
    expect(screen.getByText("Degraded")).toBeTruthy();
  });

  it("renders red as Down", () => {
    render(<HealthStatusBadge status="red" />);
    expect(screen.getByText("Down")).toBeTruthy();
  });

  it("renders null as Pending", () => {
    render(<HealthStatusBadge status={null} />);
    expect(screen.getByText("Pending")).toBeTruthy();
  });
});
