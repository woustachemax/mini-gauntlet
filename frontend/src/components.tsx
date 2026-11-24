import { Skeleton } from "@/components/ui/skeleton";
import { TableCell, TableRow } from "@/components/ui/table";
import { label } from "@/format";
import { LINK } from "@/lib/utils";

const STATUS_COLOURS: Record<string, string> = {
  FAIL: "text-red-400",
  FAILED: "text-red-400",
  CANNOT_SCAN: "text-amber-400",
  PASS: "text-zinc-500",
  COMPLETED: "text-zinc-500",
  RUNNING: "text-zinc-200",
};

export function StatusText({ status }: { status: string }) {
  return <span className={STATUS_COLOURS[status] ?? "text-zinc-500"}>{label(status)}</span>;
}

export function ErrorLine({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <p role="alert" className="text-zinc-300">
      {message}
      {onRetry && (
        <button type="button" onClick={onRetry} className={`${LINK} ml-2`}>
          Retry
        </button>
      )}
    </p>
  );
}

export function SkeletonRows({ rows, columns }: { rows: number; columns: number }) {
  return Array.from({ length: rows }, (_, row) => (
    <TableRow key={row} aria-hidden="true">
      {Array.from({ length: columns }, (_, column) => (
        <TableCell key={column}>
          <Skeleton className="h-3 w-3/4" />
        </TableCell>
      ))}
    </TableRow>
  ));
}
