import { api } from "@/api/client";
import type { ExchangeRate } from "@/types";

export function fetchExchangeRate(date: string, currency: string) {
  const params = new URLSearchParams({ date, currency });
  return api.get<ExchangeRate>(`/exchange-rates?${params}`);
}
