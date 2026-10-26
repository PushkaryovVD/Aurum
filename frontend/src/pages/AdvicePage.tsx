import { Lightbulb, TrendingUp, TriangleAlert } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { useAdvice } from "@/hooks/useAdvice";
import { formatCurrency } from "@/lib/format";
import { QueryStateNotice } from "@/components/ui/QueryStateNotice";
import { ReportingCurrencyNote } from "@/components/ui/ReportingCurrencyNote";
import { useTranslation } from "@/lib/i18n";
import { queryDisplayState } from "@/lib/queryDisplayState";
import { translateCategoryName } from "@/lib/categoryLabels";
import type { AdviceItem } from "@/types";

const TONE_STYLES: Record<AdviceItem["tone"], string> = {
  positive: "border-success/30 bg-success/10 text-success",
  warning: "border-danger/30 bg-danger/10 text-danger",
  neutral: "border-border bg-surface-1 text-text-primary",
};

const TONE_ICONS: Record<AdviceItem["tone"], typeof Lightbulb> = {
  positive: TrendingUp,
  warning: TriangleAlert,
  neutral: Lightbulb,
};

// Each advice key needs its own params → translated message mapping since
// some params (amounts) must be currency-formatted and category names
// translated before interpolation — unlike AlertBanner's alerts, which only
// ever interpolate raw numbers. Money params are in the response's
// reporting_currency, passed in as `currency`.
function adviceMessage(item: AdviceItem, t: ReturnType<typeof useTranslation>["t"], currency: string): string {
  switch (item.key) {
    case "rising_category":
      return t("advice.risingCategory", {
        category: translateCategoryName(String(item.params.category)),
        percent: item.params.percent,
        current: formatCurrency(Number(item.params.current), currency),
        average: formatCurrency(Number(item.params.average), currency),
      });
    case "unbudgeted_top_category":
      return t("advice.unbudgetedTopCategory", {
        category: translateCategoryName(String(item.params.category)),
        amount: formatCurrency(Number(item.params.amount), currency),
      });
    case "savings_rate_trend": {
      const diff = Number(item.params.diff);
      return t("advice.savingsRateTrend", { rate: item.params.rate, diff: `${diff > 0 ? "+" : ""}${diff}` });
    }
    default:
      return item.key;
  }
}

export function AdvicePage() {
  const { t, currency: settingsCurrency } = useTranslation();
  const { data, isLoading, isError } = useAdvice();
  const currency = data?.reporting_currency ?? settingsCurrency;
  const displayState = queryDisplayState(data !== undefined, isLoading, isError);
  const items = data?.items ?? [];

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>{t("nav.advice")}</CardTitle>
        </CardHeader>
        <CardContent>
          <QueryStateNotice
            state={displayState}
            unavailableText={t("advice.unavailable")}
            staleText={t("advice.stale")}
            className="mb-3"
          />
          {displayState === "loading" ? (
            <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : displayState === "unavailable" ? null : items.length === 0 ? (
            <p className="py-10 text-center text-sm text-text-muted">{t("advice.empty")}</p>
          ) : (
            <div className="space-y-2">
              {items.map((item) => {
                const Icon = TONE_ICONS[item.tone];
                return (
                  <div
                    key={item.key}
                    className={`flex items-start gap-2.5 rounded-lg border px-4 py-3 text-sm ${TONE_STYLES[item.tone]}`}
                  >
                    <Icon size={16} className="mt-0.5 shrink-0" />
                    <span>{adviceMessage(item, t, currency)}</span>
                  </div>
                );
              })}
            </div>
          )}
          {data && (
            <ReportingCurrencyNote currency={data.reporting_currency} incomplete={data.incomplete} className="mt-3" />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
