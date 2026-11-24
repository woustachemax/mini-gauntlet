import { useEffect, useState } from "react";

import {
  FINDING_STATUSES,
  PROVIDERS,
  SEVERITIES,
  errorText,
  listFindings,
  type FindingFilters,
  type FindingsPage,
} from "@/api";
import { ErrorLine, SkeletonRows, StatusText } from "@/components";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { label } from "@/format";
import { LINK, cn } from "@/lib/utils";

const PAGE_SIZE = 25;
const NO_FILTERS: FindingFilters = { status: "", severity: "", provider: "", account_id: "" };

// Native <select> styled like a small dark shadcn SelectTrigger, so the filter test keeps
// driving it with fireEvent.change.
const SELECT_CLASSES =
  "border-input text-foreground bg-background h-7 rounded-md border px-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring";

interface Props {
  scanId: number;
  accountIds: string[];
}

export default function FindingsTable({ scanId, accountIds }: Props) {
  const [filters, setFilters] = useState<FindingFilters>(NO_FILTERS);
  const [page, setPage] = useState(1);
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<FindingsPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Ignore a response that arrives after the filters or page have changed again.
    let stale = false;
    setResult(null);
    setError(null);
    listFindings(scanId, filters, page, PAGE_SIZE)
      .then((data) => !stale && setResult(data))
      .catch((e) => !stale && setError(errorText(e, "load findings")));
    return () => {
      stale = true;
    };
  }, [scanId, filters, page, attempt]);

  function setFilter(key: keyof FindingFilters, value: string) {
    setFilters({ ...filters, [key]: value });
    setPage(1);
  }

  function clearFilters() {
    setFilters(NO_FILTERS);
    setPage(1);
  }

  const anyFilter = Object.values(filters).some(Boolean);
  const pageCount = result ? Math.max(1, Math.ceil(result.total / PAGE_SIZE)) : 1;
  const first = (page - 1) * PAGE_SIZE + 1;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-4">
        <FilterSelect
          label="Status"
          value={filters.status}
          options={FINDING_STATUSES}
          onChange={(value) => setFilter("status", value)}
        />
        <FilterSelect
          label="Severity"
          value={filters.severity}
          options={SEVERITIES}
          onChange={(value) => setFilter("severity", value)}
        />
        <FilterSelect
          label="Provider"
          value={filters.provider}
          options={PROVIDERS}
          onChange={(value) => setFilter("provider", value)}
        />
        <FilterSelect
          label="Account"
          value={filters.account_id}
          options={accountIds}
          onChange={(value) => setFilter("account_id", value)}
        />
        {anyFilter && (
          <button type="button" onClick={clearFilters} className={`${LINK} text-xs`}>
            Clear filters
          </button>
        )}
      </div>

      {error && <ErrorLine message={error} onRetry={() => setAttempt(attempt + 1)} />}
      {result?.total === 0 && (
        <p className="text-muted-foreground py-2">No findings match these filters.</p>
      )}

      {!error && result?.total !== 0 && (
        <Table className="table-fixed">
          <TableHeader>
            <TableRow>
              <TableHead className="w-24">Status</TableHead>
              <TableHead className="w-20">Severity</TableHead>
              <TableHead className="w-28">Check</TableHead>
              <TableHead className="w-44">Account</TableHead>
              <TableHead className="w-28">Region</TableHead>
              <TableHead className="w-52">Resource</TableHead>
              <TableHead>Details</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!result && <SkeletonRows rows={8} columns={7} />}
            {result?.items.map((finding) => (
              <TableRow key={finding.id}>
                <TableCell>
                  <StatusText status={finding.status} />
                </TableCell>
                <TableCell
                  className={cn(finding.status === "PASS" ? "text-zinc-600" : "text-zinc-300")}
                >
                  {label(finding.severity)}
                </TableCell>
                <TableCell className="font-mono" title={finding.title}>
                  {finding.check_id}
                </TableCell>
                <TableCell className="truncate font-mono" title={finding.account_id}>
                  {finding.account_id}
                </TableCell>
                <TableCell className="font-mono">
                  {finding.region ?? <span className="text-muted-foreground">—</span>}
                </TableCell>
                <TableCell className="truncate font-mono" title={finding.resource_id ?? undefined}>
                  {finding.resource_id ?? <span className="text-muted-foreground">—</span>}
                </TableCell>
                <TableCell className="whitespace-normal">{finding.details}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      {result && result.total > 0 && (
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground text-xs tabular-nums">
            {first}-{first + result.items.length - 1} of {result.total}
          </span>
          <Button variant="ghost" onClick={() => setPage(page - 1)} disabled={page <= 1}>
            Previous
          </Button>
          <Button variant="ghost" onClick={() => setPage(page + 1)} disabled={page >= pageCount}>
            Next
          </Button>
        </div>
      )}
    </div>
  );
}

interface FilterSelectProps {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}

function FilterSelect({ label: name, value, options, onChange }: FilterSelectProps) {
  return (
    <label className="text-muted-foreground flex items-center gap-2 text-xs">
      {name}
      <select
        className={SELECT_CLASSES}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">All</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {label(option)}
          </option>
        ))}
      </select>
    </label>
  );
}
