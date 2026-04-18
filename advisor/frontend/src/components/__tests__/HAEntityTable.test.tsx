import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { HAEntitiesResponse } from "../../types";

import HAEntityTable from "../HAEntityTable";

function makeEntity(
  overrides: Partial<HAEntitiesResponse["entities"][number]> = {},
) {
  return {
    entity_id: "switch.lamp",
    ha_device_id: "dev-1",
    domain: "switch",
    friendly_name: "Lamp",
    state: "on",
    last_changed: "2026-04-17T14:03:12Z",
    attributes: {},
    ...overrides,
  };
}

function response(
  overrides: Partial<HAEntitiesResponse> = {},
): HAEntitiesResponse {
  return {
    connection_status: "ok",
    polled_at: "2026-04-17T14:03:12Z",
    stale: false,
    entities: [
      makeEntity({ entity_id: "switch.lamp", friendly_name: "Lamp" }),
      makeEntity({
        entity_id: "switch.fan",
        domain: "switch",
        friendly_name: "Fan",
      }),
      makeEntity({
        entity_id: "binary_sensor.front_door",
        domain: "binary_sensor",
        friendly_name: "Front Door",
        state: "off",
      }),
      makeEntity({
        entity_id: "sensor.temperature",
        domain: "sensor",
        friendly_name: "Kitchen Temperature",
        state: "21.5",
      }),
    ],
    ...overrides,
  };
}

beforeEach(() => {
  // no-op; HAEntityTable is driven by props — no service mock required.
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("HAEntityTable", () => {
  it("renders a row per entity", () => {
    render(<HAEntityTable response={response()} />);

    expect(screen.getByText("Lamp")).toBeTruthy();
    expect(screen.getByText("Fan")).toBeTruthy();
    expect(screen.getByText("Front Door")).toBeTruthy();
    expect(screen.getByText("Kitchen Temperature")).toBeTruthy();
  });

  it("filters visible rows via domain filter pills", async () => {
    render(<HAEntityTable response={response()} />);

    // The component renders a domain filter pill per unique domain. Click
    // the binary_sensor pill and assert only the binary_sensor row remains.
    // Accept matches by role="button" with an accessible name, by
    // data-testid, or by literal visible text.
    const pill =
      screen.queryByRole("button", { name: /binary_sensor/i }) ||
      screen.queryByTestId("ha-domain-filter-binary_sensor") ||
      screen.getByText("binary_sensor");

    fireEvent.click(pill);

    await waitFor(() => {
      expect(screen.getByText("Front Door")).toBeTruthy();
      expect(screen.queryByText("Lamp")).toBeNull();
      expect(screen.queryByText("Fan")).toBeNull();
      expect(screen.queryByText("Kitchen Temperature")).toBeNull();
    });
  });

  it("renders a stale banner when response.stale === true", () => {
    render(
      <HAEntityTable
        response={response({
          stale: true,
          connection_status: "unreachable",
        })}
      />,
    );

    // Accept any user-visible copy signalling staleness.
    const stale =
      screen.queryByText(/stale/i) ||
      screen.queryByText(/unreachable/i) ||
      screen.queryByTestId("ha-stale-banner");
    expect(stale).toBeTruthy();
  });

  it("renders an empty-state when entities is []", () => {
    render(<HAEntityTable response={response({ entities: [] })} />);

    // Accept any empty-state copy.
    const empty =
      screen.queryByText(/no entities/i) ||
      screen.queryByText(/no Home Assistant entities/i) ||
      screen.queryByText(/empty/i) ||
      screen.queryByText(/nothing to show/i) ||
      screen.queryByTestId("ha-entity-empty");
    expect(empty).toBeTruthy();
  });
});
