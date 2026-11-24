import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError, SEVERITIES, errorText, getScan, type ScanDetail } from "@/api";
import { ErrorLine, StatusText } from "@/components";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDuration, formatScore, formatTime, label } from "@/format";
import { LINK } from "@/lib/utils";
import FindingsTable from "./FindingsTable";

const POLL_MS = 1500;

export default function ScanPage() {
  const scanId = Number(useParams().id);
  const validId = Number.isInteger(scanId);
  const [scan, setScan] = useState<ScanDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(!validId);

  const load = useCallback(async () => {
    try {
      setScan(await getScan(scanId));
      setError(null);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setNotFound(true);
      } else {
        setError(errorText(e, "load this scan"));
      }
    }
  }, [scanId]);

  useEffect(() => {
    if (validId) {
      load();
    }
  }, [validId, load]);

  const running = scan?.status === "RUNNING";
  useEffect(() => {
    if (!running) {
      return;
    }
    const timer = setInterval(load, POLL_MS);
    return () => clearInterval(timer);
  }, [running, load]);

  return (
    <section className="flex flex-col gap-6">
      <nav aria-label="Breadcrumb" className="text-muted-foreground flex gap-2">
        <Link to="/" className={LINK}>
          Scans
        </Link>
        <span>/</span>
        <span>Scan {validId ? scanId : "?"}</span>
      </nav>

      {notFound && <ErrorLine message="Scan not found." />}
      {!notFound && error && <ErrorLine message={error} onRetry={load} />}
      {!notFound && !error && scan === null && (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-3 w-96" />
        </div>
      )}

      {scan && (
        <>
          <div className="flex flex-col gap-1">
            <h1 className="text-base font-semibold">Scan {scan.id}</h1>
            <p className="text-muted-foreground flex flex-wrap gap-4">
              <StatusText status={scan.status} />
              <span className="tabular-nums">Started {formatTime(scan.started_at)}</span>
              <span className="tabular-nums">
                Took {formatDuration(scan.started_at, scan.finished_at)}
              </span>
              <span>
                {scan.account_ids ? (
                  <span className="font-mono">{scan.account_ids.join(", ")}</span>
                ) : (
                  "All accounts"
                )}
              </span>
            </p>
          </div>

          {scan.status === "FAILED" && <ErrorLine message={`Scan failed: ${scan.error}`} />}
          {running && (
            <p className="text-muted-foreground">Scan is running. Results appear when it finishes.</p>
          )}

          {scan.status === "COMPLETED" && (
            <>
              <dl className="flex gap-12">
                <SummaryNumber name="Score" value={formatScore(scan.score)} />
                <SummaryNumber name="Fail" value={scan.counts.FAIL} />
                <SummaryNumber name="Cannot scan" value={scan.counts.CANNOT_SCAN} />
                <SummaryNumber name="Pass" value={scan.counts.PASS} />
              </dl>

              <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-12">
                <div className="flex flex-col gap-2">
                  <h2 className="font-medium">Failures by severity</h2>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Severity</TableHead>
                        <TableHead className="text-right">Failures</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {SEVERITIES.map((severity) => (
                        <TableRow key={severity}>
                          <TableCell>{label(severity)}</TableCell>
                          <TableCell className="text-right tabular-nums">
                            {scan.fail_by_severity[severity]}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>

                <div className="flex flex-col gap-2">
                  <h2 className="font-medium">Score per account</h2>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Account</TableHead>
                        <TableHead className="text-right">Score</TableHead>
                        <TableHead className="text-right">Fail</TableHead>
                        <TableHead className="text-right">Cannot scan</TableHead>
                        <TableHead className="text-right">Pass</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {scan.accounts.map((account) => (
                        <TableRow key={account.account_id}>
                          <TableCell className="font-mono">{account.account_id}</TableCell>
                          <TableCell className="text-right tabular-nums">
                            {formatScore(account.score)}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">{account.counts.FAIL}</TableCell>
                          <TableCell className="text-right tabular-nums">
                            {account.counts.CANNOT_SCAN}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">{account.counts.PASS}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </div>

              <div className="flex flex-col gap-2">
                <h2 className="font-medium">Findings</h2>
                <FindingsTable
                  scanId={scan.id}
                  accountIds={scan.accounts.map((account) => account.account_id)}
                />
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}

function SummaryNumber({ name, value }: { name: string; value: string | number }) {
  return (
    <div className="flex flex-col-reverse">
      <dt className="text-muted-foreground text-xs">{name}</dt>
      <dd className="text-xl tabular-nums">{value}</dd>
    </div>
  );
}
