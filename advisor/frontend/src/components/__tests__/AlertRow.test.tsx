import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

import AlertRow from "../AlertRow";
import type { Alert } from "../../types";

function renderRow(
  alert: Alert,
  handlers: {
    onAcknowledge?: (id: number) => void;
    onResolve?: (id: number) => void;
  } = {},
) {
  return render(
    <table>
      <tbody>
        <AlertRow
          alert={alert}
          onAcknowledge={handlers.onAcknowledge}
          onResolve={handlers.onResolve}
        />
      </tbody>
    </table>,
  );
}

const baseAlert: Alert = {
  id: 42,
  rule_id: "pi_cpu_high",
  rule_name: "Sustained high CPU on Pi",
  severity: "warning",
  target_type: "device",
  target_id: 7,
  target_label: "torrentbox",
  message: "CPU at 95% for 10m",
  state: "active",
  source: "rule",
  suppressed: false,
  created_at: "2026-04-10T12:34:56Z",
  acknowledged_at: null,
  resolved_at: null,
  resolution_source: null,
};

describe("AlertRow", () => {
  let onAcknowledge: ReturnType<typeof vi.fn>;
  let onResolve: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    onAcknowledge = vi.fn();
    onResolve = vi.fn();
  });

  it("renders an active alert with severity, target, message, state and both action buttons", () => {
    renderRow(baseAlert, { onAcknowledge, onResolve });

    const row = screen.getByTestId(`alert-row-${baseAlert.id}`);
    const row_scope = within(row);

    // Severity badge
    expect(row_scope.getByText(/warning/i)).toBeTruthy();
    // Target label (not the rule name fallback)
    expect(row_scope.getByText("torrentbox")).toBeTruthy();
    // Message
    expect(row_scope.getByText("CPU at 95% for 10m")).toBeTruthy();
    // State label
    expect(row_scope.getByText("active")).toBeTruthy();
    // Formatted time — we can't pin locale formatting, but the cell must not
    // render the em-dash placeholder for a valid ISO timestamp.
    expect(row_scope.queryByText("—")).toBeNull();

    // Both action buttons visible for an active alert
    expect(row_scope.getByRole("button", { name: /ack/i })).toBeTruthy();
    expect(row_scope.getByRole("button", { name: /resolve/i })).toBeTruthy();
  });

  it("hides the Ack button for an acknowledged alert but keeps Resolve", () => {
    const ack: Alert = {
      ...baseAlert,
      state: "acknowledged",
      acknowledged_at: "2026-04-10T12:40:00Z",
    };
    renderRow(ack, { onAcknowledge, onResolve });

    const row = screen.getByTestId(`alert-row-${ack.id}`);
    const row_scope = within(row);

    expect(row_scope.queryByRole("button", { name: /ack/i })).toBeNull();
    expect(row_scope.getByRole("button", { name: /resolve/i })).toBeTruthy();
  });

  it("hides both action buttons for a resolved alert", () => {
    const resolved: Alert = {
      ...baseAlert,
      state: "resolved",
      acknowledged_at: "2026-04-10T12:40:00Z",
      resolved_at: "2026-04-10T12:45:00Z",
      resolution_source: "manual",
    };
    renderRow(resolved, { onAcknowledge, onResolve });

    const row = screen.getByTestId(`alert-row-${resolved.id}`);
    const row_scope = within(row);

    expect(row_scope.queryByRole("button", { name: /ack/i })).toBeNull();
    expect(row_scope.queryByRole("button", { name: /resolve/i })).toBeNull();
  });

  it("invokes onAcknowledge/onResolve with the alert id when buttons are clicked", () => {
    renderRow(baseAlert, { onAcknowledge, onResolve });

    const row = screen.getByTestId(`alert-row-${baseAlert.id}`);
    const row_scope = within(row);

    fireEvent.click(row_scope.getByRole("button", { name: /ack/i }));
    expect(onAcknowledge).toHaveBeenCalledTimes(1);
    expect(onAcknowledge).toHaveBeenCalledWith(baseAlert.id);
    expect(onResolve).not.toHaveBeenCalled();

    fireEvent.click(row_scope.getByRole("button", { name: /resolve/i }));
    expect(onResolve).toHaveBeenCalledTimes(1);
    expect(onResolve).toHaveBeenCalledWith(baseAlert.id);
  });

  it("falls back to rule_name when target_label is null", () => {
    const systemAlert: Alert = {
      ...baseAlert,
      id: 99,
      target_type: "system",
      target_id: null,
      target_label: null,
      rule_name: "Ollama unavailable",
      rule_id: "ollama_unavailable",
    };
    renderRow(systemAlert, { onAcknowledge, onResolve });

    const row = screen.getByTestId(`alert-row-${systemAlert.id}`);
    const row_scope = within(row);

    expect(row_scope.getByText("Ollama unavailable")).toBeTruthy();
  });
});
