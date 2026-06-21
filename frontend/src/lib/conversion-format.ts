const dateFormatter = new Intl.DateTimeFormat("en-GB", {
  dateStyle: "medium",
  timeStyle: "short",
});

export function formatDate(epochMs: number): string {
  return dateFormatter.format(new Date(epochMs));
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  const totalSeconds = Math.round(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
}

export const statusStyles: Record<string, string> = {
  success: "bg-emerald-50 text-emerald-700",
  partial: "bg-amber-50 text-amber-700",
  error: "bg-red-50 text-red-700",
};

// Turns the row-disposition counts into "23 possible duplicates, 4 missing
// required fields" style text — skips any category that's zero, so a file
// with only one kind of issue doesn't show "0 duplicates" noise.
export function breakdownPhrase(r: { missingFields: number; duplicates: number; internal: number }): string {
  const parts: string[] = [];
  if (r.duplicates) parts.push(`${r.duplicates} possible duplicate${r.duplicates === 1 ? "" : "s"}`);
  if (r.missingFields) parts.push(`${r.missingFields} missing required field${r.missingFields === 1 ? "" : "s"}`);
  if (r.internal) parts.push(`${r.internal} flagged as internal entr${r.internal === 1 ? "y" : "ies"}`);
  return parts.join(", ");
}
