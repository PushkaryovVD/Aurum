import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { useAccounts } from "@/hooks/useAccounts";
import {
  useCreateInvestmentPortfolio, useCreateSecurity, useCreateSecurityDividend,
  useCreateSecurityTrade, useDeleteSecurityDividend, useDeleteSecurityTrade,
  useInvestmentPortfolios, useInvestmentPositions, useSetSecurityPrice,
} from "@/hooks/useInvestments";
import { useTranslation } from "@/lib/i18n";

const field = "h-9 w-full rounded-lg border border-border bg-surface-0 px-3 text-sm text-text-primary";
const today = new Date().toISOString().slice(0, 10);
const number = (value: string | null, currency: string) => value === null ? "—" :
  new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 2 }).format(Number(value));

export function InvestmentsPage() {
  const { t } = useTranslation();
  const { data: accounts = [] } = useAccounts();
  const { data: portfolios = [] } = useInvestmentPortfolios();
  const { data: positions = [], isLoading } = useInvestmentPositions();
  const portfolioMutation = useCreateInvestmentPortfolio();
  const securityMutation = useCreateSecurity();
  const tradeMutation = useCreateSecurityTrade();
  const dividendMutation = useCreateSecurityDividend();
  const priceMutation = useSetSecurityPrice();
  const deleteTrade = useDeleteSecurityTrade();
  const deleteDividend = useDeleteSecurityDividend();
  const investmentAccounts = accounts.filter((row) => row.type === "investment" && !row.is_archived);
  const [selected, setSelected] = useState<number | null>(null);
  const active = useMemo(() => positions.find((row) => row.asset_id === selected) ?? positions[0], [positions, selected]);

  function submitPortfolio(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    portfolioMutation.mutate({ name: String(form.get("name")), account_id: Number(form.get("account")) });
    event.currentTarget.reset();
  }
  function submitSecurity(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    securityMutation.mutate({ portfolio_id: Number(form.get("portfolio")), name: form.get("name"), ticker: form.get("ticker"), isin: form.get("isin") || null, exchange: form.get("exchange") || null, currency: form.get("currency") });
    event.currentTarget.reset();
  }
  function submitEvent(event: FormEvent<HTMLFormElement>, kind: "trade" | "dividend" | "price") {
    event.preventDefault(); if (!active) return; const form = new FormData(event.currentTarget);
    const rate = form.get("rate") ? String(form.get("rate")) : null;
    if (kind === "trade") tradeMutation.mutate({ assetId: active.asset_id, body: { type: form.get("type"), quantity: form.get("quantity"), price_per_unit: form.get("price"), fee: form.get("fee") || "0", date: form.get("date"), exchange_rate_to_kzt: rate } });
    if (kind === "dividend") dividendMutation.mutate({ assetId: active.asset_id, body: { gross_amount: form.get("gross"), tax_amount: form.get("tax") || "0", date: form.get("date"), exchange_rate_to_kzt: rate } });
    if (kind === "price") priceMutation.mutate({ assetId: active.asset_id, body: { price_per_unit: form.get("price"), as_of_date: form.get("date"), exchange_rate_to_kzt: rate } });
    event.currentTarget.reset();
  }

  return <div className="space-y-5">
    <Card><CardHeader><CardTitle>{t("nav.investments")}</CardTitle></CardHeader><CardContent>
      {!investmentAccounts.length && <p className="mb-4 text-sm text-warning">{t("investments.needAccount")}</p>}
      <div className="grid gap-4 lg:grid-cols-2">
        <form className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]" onSubmit={submitPortfolio}>
          <input className={field} name="name" required placeholder={t("investments.portfolioName")} />
          <select className={field} name="account" required defaultValue=""><option value="" disabled>{t("investments.cashAccount")}</option>{investmentAccounts.map(a => <option key={a.id} value={a.id}>{a.name} ({a.currency})</option>)}</select>
          <Button disabled={!investmentAccounts.length}>{t("investments.addPortfolio")}</Button>
        </form>
        <form className="grid gap-2 sm:grid-cols-3" onSubmit={submitSecurity}>
          <select className={field} name="portfolio" required defaultValue=""><option value="" disabled>{t("investments.portfolio")}</option>{portfolios.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
          <input className={field} name="name" required placeholder={t("investments.securityName")} />
          <input className={field} name="ticker" required placeholder="Ticker" />
          <input className={field} name="isin" placeholder="ISIN" />
          <input className={field} name="exchange" placeholder={t("investments.exchange")} />
          <input className={field} name="currency" required maxLength={3} defaultValue="KZT" />
          <Button className="sm:col-span-3" disabled={!portfolios.length}>{t("investments.addSecurity")}</Button>
        </form>
      </div>
    </CardContent></Card>

    <div className="grid gap-5 xl:grid-cols-[1.2fr_1fr]">
      <Card><CardHeader><CardTitle>{t("investments.positions")}</CardTitle></CardHeader><CardContent>
        {isLoading ? <p>{t("common.loading")}</p> : !positions.length ? <p className="text-sm text-text-muted">{t("investments.empty")}</p> :
        <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="text-left text-text-muted"><th className="py-2">Ticker</th><th>{t("investments.quantity")}</th><th>{t("investments.average")}</th><th>{t("investments.value")}</th><th>{t("investments.result")}</th></tr></thead><tbody>{positions.map(row => <tr key={row.asset_id} onClick={() => setSelected(row.asset_id)} className="cursor-pointer border-t border-border hover:bg-surface-2"><td className="py-3 font-medium">{row.ticker}<div className="text-xs text-text-muted">{row.name}</div></td><td>{Number(row.quantity)}</td><td>{number(row.average_cost, row.currency)}</td><td>{number(row.current_value, row.currency)}</td><td className={Number(row.total_return) >= 0 ? "text-success" : "text-danger"}>{number(row.total_return, row.currency)}</td></tr>)}</tbody></table></div>}
      </CardContent></Card>

      <Card><CardHeader><CardTitle>{active ? `${active.ticker} · ${t("investments.operations")}` : t("investments.operations")}</CardTitle></CardHeader><CardContent className="space-y-4">
        {!active ? <p className="text-sm text-text-muted">{t("investments.selectSecurity")}</p> : <>
          <div className="grid grid-cols-2 gap-2 text-sm"><div>{t("investments.realized")}<strong className="block">{number(active.realized_profit, active.currency)}</strong></div><div>{t("investments.unrealized")}<strong className="block">{number(active.unrealized_profit, active.currency)}</strong></div><div>{t("investments.dividends")}<strong className="block">{number(active.net_dividends, active.currency)}</strong></div><div>{t("investments.costBasis")}<strong className="block">{number(active.cost_basis, active.currency)}</strong></div></div>
          <form className="grid grid-cols-2 gap-2" onSubmit={e => submitEvent(e, "trade")}><select className={field} name="type"><option value="buy">{t("investments.buy")}</option><option value="sell">{t("investments.sell")}</option></select><input className={field} name="quantity" type="number" step="any" min="0" required placeholder={t("investments.quantity")} /><input className={field} name="price" type="number" step="any" required placeholder={t("investments.price")} /><input className={field} name="fee" type="number" step="any" placeholder={t("investments.fee")} /><input className={field} name="date" type="date" required defaultValue={today} /><input className={field} name="rate" type="number" step="any" placeholder={t("investments.rate")} /><Button className="col-span-2">{t("investments.saveTrade")}</Button></form>
          <form className="grid grid-cols-2 gap-2 border-t border-border pt-4" onSubmit={e => submitEvent(e, "dividend")}><input className={field} name="gross" type="number" step="any" required placeholder={t("investments.gross")} /><input className={field} name="tax" type="number" step="any" placeholder={t("investments.tax")} /><input className={field} name="date" type="date" required defaultValue={today} /><input className={field} name="rate" type="number" step="any" placeholder={t("investments.rate")} /><Button className="col-span-2">{t("investments.saveDividend")}</Button></form>
          <form className="grid grid-cols-2 gap-2 border-t border-border pt-4" onSubmit={e => submitEvent(e, "price")}><input className={field} name="price" type="number" step="any" required placeholder={t("investments.currentPrice")} /><input className={field} name="date" type="date" required defaultValue={today} /><input className={field} name="rate" type="number" step="any" placeholder={t("investments.rate")} /><Button>{t("investments.updatePrice")}</Button></form>
          {(active.trades.length > 0 || active.dividends.length > 0) && <div className="border-t border-border pt-3 text-xs text-text-muted">{[...active.trades.map(x => ({ id:x.id, date:x.date, text:`${x.type.toUpperCase()} ${x.quantity} × ${x.price_per_unit}`, remove:() => deleteTrade.mutate(x.id) })), ...active.dividends.map(x => ({ id:x.id, date:x.date, text:`${t("investments.dividend")} ${x.net_amount}`, remove:() => deleteDividend.mutate(x.id) }))].sort((a,b) => b.date.localeCompare(a.date)).map(x => <div key={`${x.text}-${x.id}`} className="flex items-center justify-between border-b border-border py-2"><span>{x.date} · {x.text}</span><button className="text-danger" onClick={x.remove}>{t("common.delete")}</button></div>)}</div>}
        </>}
      </CardContent></Card>
    </div>
  </div>;
}
