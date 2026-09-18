import { useQuery } from "@tanstack/react-query";
import { fetchExchangeRate } from "@/api/exchangeRates";

export function useExchangeRate(date: string, currency?: string) {
  const normalized = currency?.toUpperCase();
  return useQuery({
    queryKey: ["exchange-rate", date, normalized],
    queryFn: () => fetchExchangeRate(date, normalized!),
    enabled: Boolean(date && normalized && normalized !== "KZT"),
    staleTime: Infinity,
    retry: false,
  });
}
