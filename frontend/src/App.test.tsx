import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { Finding, ScanDetail, ScanSummary } from "./api";
import App from "./App";

const XSS = "<img src=x onerror=alert(1)>";

const completed: ScanSummary = {
  id: 2,
  status: "COMPLETED",
  started_at: "2026-11-24T07:29:32.764Z",
  finished_at: "2026-11-24T07:29:35.774Z",
  account_ids: null,
  error: null,
  score: 60,
  counts: { PASS: 27, FAIL: 18, CANNOT_SCAN: 4 },
};

const failed: ScanSummary = {
  id: 1,
  status: "FAILED",
  started_at: "2026-11-24T07:00:00.000Z",
  finished_at: "2026-11-24T07:00:00.100Z",
  account_ids: ["example-corp-gcp"],
  error: "FileNotFoundError: no inventory",
  score: null,
  counts: { PASS: 0, FAIL: 0, CANNOT_SCAN: 0 },
};

const detail: ScanDetail = {
  ...completed,
  fail_by_severity: { CRITICAL: 1, HIGH: 0, MEDIUM: 0, LOW: 0 },
  accounts: [{ account_id: "example-corp-gcp", score: 0, counts: { PASS: 0, FAIL: 1, CANNOT_SCAN: 0 } }],
};

const xssFinding: Finding = {
  id: 10,
  scan_id: 2,
  check_id: "GCP-VPC-01",
  title: "Firewall rule doesn't expose SSH or RDP to the internet",
  provider: "gcp",
  account_id: "example-corp-gcp",
  region: "global",
  resource_id: XSS,
  status: "FAIL",
  severity: "CRITICAL",
  details: `firewall rule ${XSS} allows tcp 3389 from 0.0.0.0/0`,
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockApi(routes: Record<string, unknown>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input).split("?")[0];
    return path in routes ? json(routes[path]) : json({ detail: "scan not found" }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <App />
    </MemoryRouter>,
  );
}

describe("Scans page", () => {
  it("renders a row per scan and N/A for a null score", async () => {
    mockApi({ "/api/scans": [completed, failed] });
    renderAt("/");

    expect(await screen.findByText("#2")).toBeInTheDocument();
    expect(screen.getByText("#1")).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(3);
    expect(screen.getByText("60.0")).toBeInTheDocument();
    expect(screen.getByText("N/A")).toBeInTheDocument();
    expect(screen.getByText("3.0 s")).toBeInTheDocument();
    expect(screen.getByText("FileNotFoundError: no inventory")).toBeInTheDocument();
  });

  it("shows a clear error when the API is down", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    renderAt("/");

    expect(await screen.findByRole("alert")).toHaveTextContent("Can't reach the API");
  });

  it("treats a 502 from the proxy as the API being down", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("Bad Gateway", { status: 502 })));
    renderAt("/");

    expect(await screen.findByRole("alert")).toHaveTextContent("Can't reach the API");
  });

  it("shows a generic error, not the empty state, for a 500", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 500 })));
    renderAt("/");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Couldn't load scans. Request failed with status 500.");
    expect(alert).not.toHaveTextContent("Can't reach the API");
    expect(screen.queryByText(/No scans yet/)).toBeNull();
  });

  it("shows a generic error, not the empty state, for a 200 that isn't JSON", async () => {
    const html = new Response("<!doctype html><title>Mini Gauntlet</title>", {
      status: 200,
      headers: { "Content-Type": "text/html" },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(html));
    renderAt("/");

    expect(await screen.findByRole("alert")).toHaveTextContent("isn't JSON");
    expect(screen.queryByText(/No scans yet/)).toBeNull();
  });

  it("shows a generic error, not the empty state, for JSON in the wrong shape", async () => {
    mockApi({ "/api/scans": { scans: [] } });
    renderAt("/");

    expect(await screen.findByRole("alert")).toHaveTextContent("unexpected format");
    expect(screen.queryByText(/No scans yet/)).toBeNull();
  });

  it("shows the empty state", async () => {
    mockApi({ "/api/scans": [] });
    renderAt("/");

    expect(await screen.findByText(/No scans yet/)).toBeInTheDocument();
  });

  it("starts a scan with a POST when Run scan is clicked", async () => {
    const fetchMock = mockApi({ "/api/scans": [] });
    renderAt("/");
    await screen.findByText(/No scans yet/);

    fireEvent.click(screen.getByRole("button", { name: "Run scan" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/scans", { method: "POST" }),
    );
  });
});

describe("Scan page", () => {
  it("renders snapshot strings as text and never as HTML", async () => {
    mockApi({
      "/api/scans/2": detail,
      "/api/scans/2/findings": { items: [xssFinding], total: 1, page: 1, page_size: 25 },
    });
    const { container } = renderAt("/scans/2");

    expect(await screen.findByText(xssFinding.details)).toBeInTheDocument();
    expect(screen.getByText(XSS)).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
  });

  it("sends the chosen filters to the API and resets to page 1", async () => {
    const fetchMock = mockApi({
      "/api/scans/2": detail,
      "/api/scans/2/findings": { items: [xssFinding], total: 1, page: 1, page_size: 25 },
    });
    renderAt("/scans/2");
    await screen.findByText(xssFinding.details);

    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "FAIL" } });
    fireEvent.change(screen.getByLabelText("Provider"), { target: { value: "gcp" } });

    await waitFor(() => {
      const urls = fetchMock.mock.calls.map(([input]) => String(input));
      expect(urls).toContain("/api/scans/2/findings?page=1&page_size=25&status=FAIL&provider=gcp");
    });
  });

  it("shows not found for an unknown scan", async () => {
    mockApi({});
    renderAt("/scans/999");

    expect(await screen.findByRole("alert")).toHaveTextContent("Scan not found.");
  });
});
