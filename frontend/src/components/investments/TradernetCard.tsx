import { RefreshCw } from "lucide-react";
import Decimal from "decimal.js";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { useInvestmentPositions, useTradernetPortfolio, useTradernetStatus } from "@/hooks/useInvestments";
import { useTranslation } from "@/lib/i18n";
import { reconcileTradernetPositions } from "@/lib/tradernetReconciliation";

function decimal(value: string | null, currency?: string) {
  if (value === null) return "—";
  try {
    const amount = new Decimal(value);
    const rendered = amount.toDecimalPlaces(currency ? 2 : 8).toFixed()
      .replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
    return currency ? `${rendered} ${currency}` : rendered;
  } catch {
    return "—";
  }
}

export function TradernetCard() {
  const { t } = useTranslation();
  const status = useTradernetStatus();
  const configured = status.data?.configured === true;
  const portfolio = useTradernetPortfolio(configured);
  const local = useInvestmentPositions();
  const reconciliation = portfolio.data ? reconcileTradernetPositions(portfolio.data.positions, local.data ?? []) : [];
  const differences = reconciliation.filter((row) => row.status !== "matched");

  return <Card>
    <CardHeader>
      <div><CardTitle>{t("investments.tradernet.title")}</CardTitle><p className="mt-1 text-xs text-text-muted">{t("investments.tradernet.readOnly")}</p></div>
      {configured && <Button type="button" variant="secondary" disabled={portfolio.isFetching} onClick={() => void portfolio.refetch()}><RefreshCw size={16} className={portfolio.isFetching ? "animate-spin" : ""} />{t("investments.tradernet.refresh")}</Button>}
    </CardHeader>
    <CardContent className="space-y-4">
      {status.isLoading && <p className="text-sm text-text-muted">{t("common.loading")}</p>}
      {status.isError && <p className="text-sm text-danger" role="alert">{t("investments.tradernet.statusError")}</p>}
      {status.data && !configured && <div className="rounded-lg border border-border bg-surface-0 p-4"><p className="text-sm font-medium">{t("investments.tradernet.notConfigured")}</p><p className="mt-2 text-xs leading-relaxed text-text-muted">{t("investments.tradernet.configureHint")}</p></div>}
      {configured && portfolio.isLoading && <p className="text-sm text-text-muted">{t("investments.tradernet.loading")}</p>}
      {configured && portfolio.isError && <p className="text-sm text-danger" role="alert">{t("investments.tradernet.loadError")}</p>}
      {portfolio.data && <>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {portfolio.data.accounts.map((account) => <div key={account.currency} className="rounded-lg border border-border bg-surface-0 p-3"><p className="text-xs text-text-muted">{t("investments.tradernet.available")} · {account.currency}</p><p className="mt-1 text-lg font-semibold">{decimal(account.available_funds, account.currency)}</p></div>)}
        </div>
        {!portfolio.data.positions.length ? <p className="text-sm text-text-muted">{t("investments.tradernet.empty")}</p> : <div className="overflow-x-auto"><table className="w-full min-w-[640px] text-sm"><thead><tr className="text-left text-text-muted"><th className="py-2">Ticker</th><th>{t("investments.quantity")}</th><th>{t("investments.tradernet.marketPrice")}</th><th>{t("investments.value")}</th><th>{t("investments.unrealized")}</th></tr></thead><tbody>{portfolio.data.positions.map((position) => <tr key={position.external_position_id ?? position.ticker} className="border-t border-border"><td className="py-3 font-medium">{position.ticker}<div className="text-xs text-text-muted">{position.name}</div></td><td>{decimal(position.quantity)}</td><td>{decimal(position.market_price, position.currency)}</td><td>{decimal(position.market_value, position.currency)}</td><td className={position.unrealized_profit === null || !new Decimal(position.unrealized_profit).isNegative() ? "text-success" : "text-danger"}>{decimal(position.unrealized_profit, position.currency)}</td></tr>)}</tbody></table></div>}
        <section className="border-t border-border pt-4">
          <h4 className="text-sm font-medium">{t("investments.tradernet.reconciliation")}</h4>
          <p className="mt-1 text-xs text-text-muted">{t("investments.tradernet.reconciliationHint")}</p>
          {local.isLoading ? <p className="mt-3 text-sm text-text-muted">{t("common.loading")}</p> : !differences.length ? <p className="mt-3 text-sm text-success">{t("investments.tradernet.reconciled")}</p> : <div className="mt-3 overflow-x-auto"><table className="w-full min-w-[560px] text-sm"><thead><tr className="text-left text-text-muted"><th className="py-2">Ticker</th><th>{t("investments.tradernet.brokerQuantity")}</th><th>{t("investments.tradernet.localQuantity")}</th><th>{t("investments.tradernet.difference")}</th><th>{t("investments.tradernet.state")}</th></tr></thead><tbody>{differences.map((row) => <tr key={row.key} className="border-t border-border"><td className="py-3 font-medium">{row.ticker}<div className="text-xs text-text-muted">{row.currency}</div></td><td>{decimal(row.remoteQuantity)}</td><td>{decimal(row.localQuantity)}</td><td>{decimal(row.difference)}</td><td className="text-warning">{row.status === "mismatch" ? t("investments.tradernet.mismatch") : row.status === "remote_only" ? t("investments.tradernet.remote_only") : t("investments.tradernet.local_only")}</td></tr>)}</tbody></table></div>}
        </section>
        <p className="text-xs text-text-muted">{t("investments.tradernet.updated", { time: new Date(portfolio.data.fetched_at).toLocaleString() })}</p>
      </>}
    </CardContent>
  </Card>;
}
