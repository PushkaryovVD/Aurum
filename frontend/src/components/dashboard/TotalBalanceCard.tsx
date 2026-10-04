import { Card } from "@/components/ui/Card";
import { formatCurrency } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import type { BalanceSummary } from "@/types";

interface TotalBalanceCardProps {
  balance?: BalanceSummary;
  isLoading: boolean;
}

/** All-time money across every account, in the app's reporting currency.
 *
 * Each account's balance stays in its own currency — this card is the only
 * place they get added up, so it says out loud which currency the total is in
 * and what had to be converted to get there. A currency with no available rate
 * is listed but left out of the total rather than quietly treated as though it
 * were already in the reporting currency. */
export function TotalBalanceCard({ balance, isLoading }: TotalBalanceCardProps) {
  const { t } = useTranslation();
  const reporting = balance?.reporting_currency ?? "KZT";
  // The reporting currency's own row would just repeat the headline figure.
  const foreign = (balance?.items ?? []).filter((item) => item.currency !== reporting);
  const convertedAny = foreign.some((item) => item.amount_reporting !== null);

  return (
    <Card className="p-card sm:py-7">
      <p className="text-sm font-medium text-text-secondary">{t("dashboard.balanceTitle")}</p>
      <p className="mt-3 break-words text-3xl font-semibold leading-tight tracking-tight tabular-nums text-text-primary [overflow-wrap:anywhere] sm:text-4xl">
        {isLoading ? "…" : formatCurrency(balance?.total ?? 0, reporting)}
      </p>
      <p className="mt-2 text-xs leading-5 text-text-muted">{t("dashboard.balanceCaption", { currency: reporting })}</p>

      {foreign.length > 0 && (
        <ul className="mt-3 space-y-1.5 border-t border-gridline pt-3">
          {foreign.map((item) => (
            <li key={item.currency} className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-xs">
              <span className="font-medium text-text-secondary">{item.currency}</span>
              <span className="min-w-0 break-words text-right tabular-nums text-text-muted [overflow-wrap:anywhere]">
                {formatCurrency(item.amount, item.currency)}
                {item.amount_reporting !== null ? (
                  <span className="ml-2 text-text-secondary">≈ {formatCurrency(item.amount_reporting, reporting)}</span>
                ) : (
                  <span className="ml-2 text-warning">· {t("dashboard.balanceMissingRate")}</span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}

      {convertedAny && <p className="mt-2 text-[11px] text-text-muted">{t("dashboard.balanceConvertedNote")}</p>}
      {balance?.incomplete && <p className="mt-2 text-[11px] text-warning">{t("dashboard.balanceIncomplete")}</p>}
    </Card>
  );
}
