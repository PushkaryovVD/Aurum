import { api } from "@/api/client";
import type { CrossRate } from "@/types";

/** One currency's price in another, e.g. "how many EUR does a USD buy". Same
 * currency on both sides is a legitimate question — the answer is 1 — and the
 * response also carries both KZT legs, so one call covers the rate and the
 * account's KZT equivalent alike. */
export function fetchCrossRate(date: string, from: string, to: string) {
  const params = new URLSearchParams({ date, from, to });
  return api.get<CrossRate>(`/exchange-rates/cross?${params}`);
}
