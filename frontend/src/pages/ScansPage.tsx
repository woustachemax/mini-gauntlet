import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { errorText, listScans, startScan, type ScanSummary } from "@/api";
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
import { formatDuration, formatScore, formatTime } from "@/format";
import { LINK } from "@/lib/utils";

const POLL_MS = 1500;

export default function ScansPage() {
  const [scans, setScans] = useState<ScanSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const load = useCallback(async () => {
    try {
      setScans(await listScans());
      setError(null);
    } catch (e) {
      setError(errorText(e, "load scans"));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const anyRunning = scans?.some((scan) => scan.status === "RUNNING") ?? false;
  useEffect(() => {
    if (!anyRunning) {
      return;
    }
    const timer = setInterval(load, POLL_MS);
    return () => clearInterval(timer);
  }, [anyRunning, load]);

  async function runScan() {
    setStarting(true);
    try {
      await startScan();
      await load();
    } catch (e) {
      setError(errorText(e, "start a scan"));
    } finally {
      setStarting(false);
    }
  }

  const loading = scans === null && !error;

  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center gap-4">
        <h1 className="text-base font-semibold">Scans</h1>
        <Button onClick={runScan} disabled={starting}>
          {starting ? "Starting…" : "Run scan"}
        </Button>
      </div>

      {error && <ErrorLine message={error} onRetry={load} />}
      {scans?.length === 0 && (
        <p className="text-muted-foreground">
          No scans yet. Run a scan to check every account in the inventory.
        </p>
      )}

      {(loading || (scans && scans.length > 0)) && (
        <Table className="table-fixed">
          <TableHeader>
            <TableRow>
              <TableHead className="w-16">Scan</TableHead>
              <TableHead className="w-28">Status</TableHead>
              <TableHead className="w-52">Started</TableHead>
              <TableHead className="w-24 text-right">Duration</TableHead>
              <TableHead className="w-20 text-right">Score</TableHead>
              <TableHead className="w-80 pl-8">Accounts</TableHead>
              <TableHead>Error</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading && <SkeletonRows rows={3} columns={7} />}
            {scans?.map((scan) => (
              <TableRow key={scan.id}>
                <TableCell>
                  <Link to={`/scans/${scan.id}`} className={`${LINK} font-mono tabular-nums`}>
                    #{scan.id}
                  </Link>
                </TableCell>
                <TableCell>
                  <StatusText status={scan.status} />
                </TableCell>
                <TableCell className="tabular-nums">{formatTime(scan.started_at)}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatDuration(scan.started_at, scan.finished_at)}
                </TableCell>
                <TableCell className="text-right tabular-nums">{formatScore(scan.score)}</TableCell>
                <TableCell
                  className="truncate pl-8 font-mono"
                  title={scan.account_ids?.join(", ")}
                >
                  {scan.account_ids ? (
                    scan.account_ids.join(", ")
                  ) : (
                    <span className="text-muted-foreground font-sans">All</span>
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground truncate" title={scan.error ?? undefined}>
                  {scan.error}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </section>
  );
}
