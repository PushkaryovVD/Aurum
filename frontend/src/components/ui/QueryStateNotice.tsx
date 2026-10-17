import { cn } from "@/lib/utils";
import type { QueryDisplayState } from "@/lib/queryDisplayState";

interface QueryStateNoticeProps {
  state: QueryDisplayState;
  /** Shown when the request failed and there is no cached data to fall back on. */
  unavailableText: string;
  /** Shown when the request failed but previously loaded data is still displayed. */
  staleText: string;
  /** Extra classes, e.g. a bottom margin when the notice sits above a list. */
  className?: string;
}

/**
 * Shared banner for the "honest states" pattern: an error without data is an
 * explicit "unavailable" message (never an empty list or a zero), an error
 * with cached data is a polite stale warning. Renders nothing otherwise.
 */
export function QueryStateNotice({ state, unavailableText, staleText, className }: QueryStateNoticeProps) {
  if (state === "unavailable") {
    return (
      <p className={cn("rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger", className)} role="alert">
        {unavailableText}
      </p>
    );
  }
  if (state === "stale") {
    return (
      <p className={cn("rounded-lg border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-warning", className)} role="status">
        {staleText}
      </p>
    );
  }
  return null;
}
