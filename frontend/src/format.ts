const dateTime = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "medium" });

export function formatTime(iso: string | null): string {
  return iso ? dateTime.format(new Date(iso)) : "—";
}

export function formatDuration(start: string, end: string | null): string {
  if (!end) {
    return "—";
  }
  const seconds = (new Date(end).getTime() - new Date(start).getTime()) / 1000;
  return `${seconds.toFixed(1)} s`;
}

export function formatScore(score: number | null): string {
  return score === null ? "N/A" : score.toFixed(1);
}

const LABELS: Record<string, string> = {
  PASS: "Pass",
  FAIL: "Fail",
  CANNOT_SCAN: "Cannot scan",
  RUNNING: "Running",
  COMPLETED: "Completed",
  FAILED: "Failed",
  CRITICAL: "Critical",
  HIGH: "High",
  MEDIUM: "Medium",
  LOW: "Low",
  aws: "AWS",
  azure: "Azure",
  gcp: "GCP",
};

export function label(value: string): string {
  return LABELS[value] ?? value;
}
