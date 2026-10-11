export type QueryDisplayState = "loading" | "ready" | "stale" | "unavailable";

/**
 * Convert React Query's independent data/loading/error flags into a UI state.
 * An error with cached data is not the same as an empty result: the data may
 * still be useful, but must be labelled stale. An error without data must not
 * be rendered as a confirmed zero or empty collection.
 */
export function queryDisplayState(
  hasData: boolean,
  isLoading: boolean,
  isError: boolean,
): QueryDisplayState {
  if (isError) return hasData ? "stale" : "unavailable";
  if (isLoading && !hasData) return "loading";
  return "ready";
}

