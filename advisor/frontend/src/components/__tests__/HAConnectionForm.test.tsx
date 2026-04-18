import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { HAConnection, HAConnectionStatus } from "../../types";

// Stub the services module before importing the component under test.
vi.mock("../../services/homeAssistant", () => ({
  getHomeAssistantConnection: vi.fn(),
  upsertHomeAssistantConnection: vi.fn(),
  testHomeAssistantConnection: vi.fn(),
  deleteHomeAssistantConnection: vi.fn(),
}));

import HAConnectionForm from "../HAConnectionForm";
import {
  getHomeAssistantConnection,
  upsertHomeAssistantConnection,
  testHomeAssistantConnection,
  deleteHomeAssistantConnection,
} from "../../services/homeAssistant";

const mockedGet = vi.mocked(getHomeAssistantConnection);
const mockedUpsert = vi.mocked(upsertHomeAssistantConnection);
const mockedTest = vi.mocked(testHomeAssistantConnection);
const mockedDelete = vi.mocked(deleteHomeAssistantConnection);

function configuredConnection(
  overrides: Partial<HAConnection> = {},
): HAConnection {
  return {
    configured: true,
    base_url: "http://homeassistant.local:8123",
    token_masked: "\u2026WXYZ",
    status: "ok",
    last_success_at: "2026-04-17T14:03:12Z",
    last_error: null,
    last_error_at: null,
    ...overrides,
  };
}

function unconfiguredConnection(): HAConnection {
  return {
    configured: false,
    base_url: null,
    token_masked: null,
    status: "not_configured",
    last_success_at: null,
    last_error: null,
    last_error_at: null,
  };
}

beforeEach(() => {
  mockedGet.mockReset();
  mockedUpsert.mockReset();
  mockedTest.mockReset();
  mockedDelete.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("HAConnectionForm", () => {
  it("renders the masked token when a connection is already configured", async () => {
    mockedGet.mockResolvedValue(configuredConnection());

    render(<HAConnectionForm />);

    await waitFor(() => {
      // The masked token is shown as the `value` of a disabled input, not
      // body text — use getByDisplayValue so the query looks at form
      // control values.
      expect(screen.getByDisplayValue(/\u2026WXYZ|\.\.\.WXYZ/)).toBeTruthy();
    });
  });

  it("reveals the access-token input after clicking Replace token", async () => {
    mockedGet.mockResolvedValue(configuredConnection());

    render(<HAConnectionForm />);

    await waitFor(() => {
      expect(screen.getByDisplayValue(/\u2026WXYZ|\.\.\.WXYZ/)).toBeTruthy();
    });

    const replaceButton = screen.getByRole("button", { name: /replace token/i });
    fireEvent.click(replaceButton);

    // After clicking, an editable access-token input is present. Accept
    // either a placeholder, label text, or an input of type="password"
    // named "access_token".
    await waitFor(() => {
      const byLabel = screen.queryByLabelText(/access token/i);
      const byPlaceholder = screen.queryByPlaceholderText(/access token|llat_/i);
      expect(byLabel || byPlaceholder).toBeTruthy();
    });
  });

  const statuses: HAConnectionStatus[] = [
    "ok",
    "auth_failure",
    "unreachable",
    "unexpected_payload",
  ];

  statuses.forEach((status) => {
    it(`renders a distinct status pill for '${status}'`, async () => {
      mockedGet.mockResolvedValue(configuredConnection({ status }));

      render(<HAConnectionForm />);

      // Each status renders distinct copy. Accept matches by text OR by a
      // data-testid of the form ha-status-<class>. Either implementation
      // satisfies "four distinct pills".
      await waitFor(() => {
        const byTestId = screen.queryByTestId(`ha-status-${status}`);
        if (byTestId) {
          expect(byTestId).toBeTruthy();
          return;
        }
        // Fallback: user-visible copy for each class. Use exact strings so
        // the match isn't diluted by nearby labels (e.g. "Connection OK"
        // vs. the word "ok" in "token" fields).
        const labelExact: Record<HAConnectionStatus, string> = {
          ok: "Connection OK",
          auth_failure: "Authentication failed",
          unreachable: "Home Assistant unreachable",
          unexpected_payload: "Unexpected response",
          not_configured: "Not configured",
        };
        expect(screen.getByText(labelExact[status])).toBeTruthy();
      });
    });
  });

  it("posts to the upsert service with the expected payload on Save", async () => {
    mockedGet.mockResolvedValue(unconfiguredConnection());
    mockedUpsert.mockResolvedValue(configuredConnection());

    render(<HAConnectionForm />);

    await waitFor(() => {
      expect(mockedGet).toHaveBeenCalled();
    });

    // Enter base URL and token, then click Save.
    const baseUrlInput =
      screen.queryByLabelText(/base url/i) ||
      screen.getByPlaceholderText(/homeassistant\.local|http/i);
    fireEvent.change(baseUrlInput, {
      target: { value: "http://homeassistant.local:8123" },
    });

    const tokenInput =
      screen.queryByLabelText(/access token/i) ||
      screen.getByPlaceholderText(/access token|llat_/i);
    fireEvent.change(tokenInput, {
      target: { value: "llat_FRESH_TOKEN_WXYZ" },
    });

    const saveBtn = screen.getByRole("button", { name: /save/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(mockedUpsert).toHaveBeenCalled();
    });

    const payload = mockedUpsert.mock.calls[0]![0];
    expect(payload).toMatchObject({
      base_url: "http://homeassistant.local:8123",
      access_token: "llat_FRESH_TOKEN_WXYZ",
    });
  });
});
