export type FindingStatus = "PASS" | "FAIL" | "CANNOT_SCAN";
export type ScanStatus = "RUNNING" | "COMPLETED" | "FAILED";
export type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

export const FINDING_STATUSES: FindingStatus[] = ["FAIL", "CANNOT_SCAN", "PASS"];
export const SEVERITIES: Severity[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];
export const PROVIDERS = ["aws", "azure", "gcp"];

export type StatusCounts = Record<FindingStatus, number>;

export interface ScanSummary {
  id: number;
  status: ScanStatus;
  started_at: string;
  finished_at: string | null;
  account_ids: string[] | null;
  error: string | null;
  score: number | null;
  counts: StatusCounts;
}

export interface AccountScore {
  account_id: string;
  score: number | null;
  counts: StatusCounts;
}

export interface ScanDetail extends ScanSummary {
  fail_by_severity: Record<Severity, number>;
  accounts: AccountScore[];
}

export interface Finding {
  id: number;
  scan_id: number;
  check_id: string;
  title: string;
  provider: string;
  account_id: string;
  region: string | null;
  resource_id: string | null;
  status: FindingStatus;
  severity: Severity;
  details: string;
}

export interface FindingsPage {
  items: Finding[];
  total: number;
  page: number;
  page_size: number;
}

export interface FindingFilters {
  status: string;
  severity: string;
  provider: string;
  account_id: string;
}

export type ErrorKind = "down" | "error";

export class ApiError extends Error {
  kind: ErrorKind;
  status: number | null;

  constructor(kind: ErrorKind, message: string, status: number | null = null) {
    super(message);
    this.kind = kind;
    this.status = status;
  }
}

const BASE_URL = import.meta.env.VITE_API_URL ?? "/api";
const API_DOWN = "Can't reach the API. Check that it is running.";
const DOWN_STATUSES = [502, 503, 504];

async function request<T>(
  path: string,
  isExpected: (body: unknown) => body is T,
  init?: RequestInit,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, init);
  } catch {
    throw new ApiError("down", API_DOWN);
  }
  if (DOWN_STATUSES.includes(response.status)) {
    throw new ApiError("down", API_DOWN, response.status);
  }
  if (!response.ok) {
    throw new ApiError("error", await errorMessage(response), response.status);
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new ApiError("error", "The API sent a response that isn't JSON.", response.status);
  }
  if (!isExpected(body)) {
    throw new ApiError("error", "The API sent a response in an unexpected format.", response.status);
  }
  return body;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") {
      return body.detail;
    }
  } catch {
    // The body wasn't JSON; fall through to the generic message.
  }
  return `Request failed with status ${response.status}.`;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isScanSummary(value: unknown): value is ScanSummary {
  return (
    isObject(value) &&
    typeof value.id === "number" &&
    typeof value.status === "string" &&
    typeof value.started_at === "string" &&
    isObject(value.counts)
  );
}

function isScanList(value: unknown): value is ScanSummary[] {
  return Array.isArray(value) && value.every(isScanSummary);
}

function isScanDetail(value: unknown): value is ScanDetail {
  return (
    isObject(value) &&
    isScanSummary(value) &&
    isObject(value.fail_by_severity) &&
    Array.isArray(value.accounts)
  );
}

function isFinding(value: unknown): value is Finding {
  return (
    isObject(value) &&
    typeof value.id === "number" &&
    typeof value.check_id === "string" &&
    typeof value.status === "string" &&
    typeof value.severity === "string" &&
    typeof value.details === "string"
  );
}

function isFindingsPage(value: unknown): value is FindingsPage {
  return (
    isObject(value) &&
    Array.isArray(value.items) &&
    value.items.every(isFinding) &&
    typeof value.total === "number"
  );
}

export function listScans(): Promise<ScanSummary[]> {
  return request("/scans", isScanList);
}

export function getScan(id: number): Promise<ScanDetail> {
  return request(`/scans/${id}`, isScanDetail);
}

export function startScan(): Promise<ScanSummary> {
  return request("/scans", isScanSummary, { method: "POST" });
}

export function listFindings(
  scanId: number,
  filters: FindingFilters,
  page: number,
  pageSize: number,
): Promise<FindingsPage> {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  for (const [key, value] of Object.entries(filters)) {
    if (value) {
      params.set(key, value);
    }
  }
  return request(`/scans/${scanId}/findings?${params}`, isFindingsPage);
}

export function errorText(error: unknown, action: string): string {
  if (error instanceof ApiError && error.kind === "down") {
    return error.message;
  }
  const reason = error instanceof Error ? error.message : String(error);
  return `Couldn't ${action}. ${reason}`;
}
