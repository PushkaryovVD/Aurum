import { useState } from "react";
import { MonthSelector } from "@/components/layout/MonthSelector";
import { YearSelector } from "@/components/layout/YearSelector";
import { StatCard } from "@/components/dashboard/StatCard";
import { SpendingByCategoryCard } from "@/components/dashboard/SpendingByCategoryCard";
import { TotalBalanceCard } from "@/components/dashboard/TotalBalanceCard";
import { RecentTransactionsCard } from "@/components/dashboard/RecentTransactionsCard";
import { AlertBanner } from "@/components/insights/AlertBanner";
import { Page, PageHeader } from "@/components/ui/Page";
import { useDashboardSummary } from "@/hooks/useDashboard";
import { useTransactionYears } from "@/hooks/useTransactions";
import { formatCurrency, formatSignedCurrency } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";

/** Share of income left over after spending (net / real_income). `null` when
 * there was no income to take a share of, rather than a misleading 0%. */
function savingsRate(realIncome: number, net: number): number | null {
  return realIncome > 0 ? (net / realIncome) * 100 : null;
}

function formatPercent(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(0)}%`;
}

export function DashboardPage() {
  const { t } = useTranslation();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const { data: years } = useTransactionYears();

  const { data, isLoading, isError } = useDashboardSummary(year, month);
  const rate = data ? savingsRate(Number(data.real_income), Number(data.net)) : null;

  return (
    <Page>
      <PageHeader
        title={t("nav.dashboard")}
        actions={
          <div className="flex w-full min-w-0 items-center gap-2 sm:w-auto">
            <div className="min-w-0 flex-1 sm:max-w-xl">
              <MonthSelector month={month} onChange={setMonth} />
            </div>
            <YearSelector years={years ?? [now.getFullYear()]} year={year} onChange={setYear} />
          </div>
        }
      />

      <AlertBanner excludeKeys={["risky_allocation_exceeded"]} />

      {isError && (
        <p className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
          {t("dashboard.errorLoading")}
        </p>
      )}

      <TotalBalanceCard balance={data?.balance} isLoading={isLoading} />

      <div className="grid grid-cols-1 gap-3 min-[375px]:grid-cols-2 sm:gap-4 lg:grid-cols-4">
        <StatCard
          label={t("dashboard.statRealIncomeLabel")}
          value={isLoading ? "…" : formatCurrency(data?.real_income ?? 0)}
          caption={t("dashboard.statRealIncomeCaption")}
          tone="success"
        />
        <StatCard
          label={t("dashboard.statSpentLabel")}
          value={isLoading ? "…" : formatCurrency(data?.spent ?? 0)}
          caption={t("dashboard.statSpentCaption")}
          tone="danger"
        />
        <StatCard
          label={t("dashboard.statNetLabel")}
          value={isLoading ? "…" : formatSignedCurrency(data?.net ?? 0)}
          caption={t("dashboard.statNetCaption")}
          tone={Number(data?.net ?? 0) >= 0 ? "success" : "danger"}
        />
        <StatCard
          label={t("dashboard.statSavingsRateLabel")}
          value={isLoading ? "…" : rate === null ? "—" : formatPercent(rate)}
          caption={t("dashboard.statSavingsRateCaption")}
          tone={rate === null ? "default" : rate >= 0 ? "success" : "danger"}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <SpendingByCategoryCard items={data?.spending_by_category ?? []} />
        <RecentTransactionsCard year={year} month={month} />
      </div>
    </Page>
  );
}
