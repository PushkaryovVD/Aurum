import { describe, expect, it } from "vitest";
import type { TradernetPosition } from "@/api/investments";
import type { SecurityPosition } from "@/types";
import { reconcileTradernetPositions } from "./tradernetReconciliation";

const remote = (ticker: string, currency: string, quantity: string): TradernetPosition => ({
  external_position_id: null, ticker, name: ticker, currency, quantity,
  market_price: null, market_value: null, book_price: null, unrealized_profit: null,
});
const local = (ticker: string, currency: string, quantity: string): SecurityPosition => ({
  asset_id: 1, portfolio_id: 1, ticker, name: ticker, currency, quantity, isin: null, exchange: null,
  average_cost: null, cost_basis: "0", current_price: null, current_value: null,
  realized_profit: "0", unrealized_profit: null, net_dividends: "0", total_return: "0", trades: [], dividends: [],
});

describe("Tradernet reconciliation", () => {
  it("matches normalized tickers without converting quantities to JS numbers", () => {
    const rows = reconcileTradernetPositions(
      [remote("aapl.us", "usd", "0.123456789012"), remote("AAPL.US", "USD", "0.000000000001")],
      [local("AAPL.US", "USD", "0.123456789013")],
    );
    expect(rows).toEqual([expect.objectContaining({ status: "matched", difference: "0", remoteQuantity: "0.123456789013" })]);
  });

  it("marks mismatched and one-sided positions explicitly", () => {
    const rows = reconcileTradernetPositions(
      [remote("AAPL.US", "USD", "3"), remote("MSFT.US", "USD", "2")],
      [local("AAPL.US", "USD", "1"), local("KZTK.KZ", "KZT", "5")],
    );
    expect(Object.fromEntries(rows.map((row) => [row.ticker, [row.status, row.difference]]))).toEqual({
      "KZTK.KZ": ["local_only", "-5"],
      "AAPL.US": ["mismatch", "2"],
      "MSFT.US": ["remote_only", "2"],
    });
  });
});
