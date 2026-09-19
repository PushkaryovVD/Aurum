import { useQuery } from "@tanstack/react-query";
import { fetchCrossRate } from "@/api/exchangeRates";

/** The rate between two currencies, resolved server-side.
 *
 * Disabled only when there is no date or no currency yet. A same-currency pair
 * is a legitimate question — the answer is 1 — and the response still carries
 * the KZT legs, so the transaction form gets both the rate it fills in and the
 * account's KZT rate from a single request instead of two.
 */
export function useCrossRate(date: string, from?: string, to?: string) {
  const source = from?.toUpperCase();
  const target = to?.toUpperCase();
  return useQuery({
    queryKey: ["cross-rate", date, source, target],
    queryFn: () => fetchCrossRate(date, source!, target!),
    enabled: Boolean(date && source && target),
    staleTime: Infinity,
    retry: false,
  });
}
