import Decimal from "decimal.js";
import type { TradernetPosition } from "@/api/investments";
import type { SecurityPosition } from "@/types";

export type ReconciliationStatus = "matched" | "mismatch" | "remote_only" | "local_only";

export interface ReconciliationRow {
  key: string;
  ticker: string;
  name: string;
  currency: string;
  remoteQuantity: string;
  localQuantity: string;
  difference: string;
  status: ReconciliationStatus;
}

const keyOf = (ticker: string, currency: string) => `${ticker.trim().toUpperCase()}::${currency.trim().toUpperCase()}`;

function add(target: Map<string, { ticker: string; name: string; currency: string; quantity: Decimal }>, ticker: string, name: string, currency: string, quantity: string) {
  const key = keyOf(ticker, currency);
  const current = target.get(key);
  const amount = new Decimal(quantity);
  if (current) current.quantity = current.quantity.plus(amount);
  else target.set(key, { ticker: ticker.trim().toUpperCase(), name, currency: currency.trim().toUpperCase(), quantity: amount });
}

export function reconcileTradernetPositions(remote: TradernetPosition[], local: SecurityPosition[]): ReconciliationRow[] {
  const remoteByKey = new Map<string, { ticker: string; name: string; currency: string; quantity: Decimal }>();
  const localByKey = new Map<string, { ticker: string; name: string; currency: string; quantity: Decimal }>();
  remote.forEach((row) => add(remoteByKey, row.ticker, row.name, row.currency, row.quantity));
  local.forEach((row) => add(localByKey, row.ticker, row.name, row.currency, row.quantity));

  const keys = new Set([...remoteByKey.keys(), ...localByKey.keys()]);
  return [...keys].map((key) => {
    const remoteRow = remoteByKey.get(key);
    const localRow = localByKey.get(key);
    const remoteQuantity = remoteRow?.quantity ?? new Decimal(0);
    const localQuantity = localRow?.quantity ?? new Decimal(0);
    const difference = remoteQuantity.minus(localQuantity);
    const status: ReconciliationStatus = !remoteRow ? "local_only" : !localRow ? "remote_only" : difference.isZero() ? "matched" : "mismatch";
    const source = remoteRow ?? localRow!;
    return {
      key,
      ticker: source.ticker,
      name: source.name,
      currency: source.currency,
      remoteQuantity: remoteQuantity.toFixed(),
      localQuantity: localQuantity.toFixed(),
      difference: difference.toFixed(),
      status,
    };
  }).sort((a, b) => a.status.localeCompare(b.status) || a.ticker.localeCompare(b.ticker));
}
