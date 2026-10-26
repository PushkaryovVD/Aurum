import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowDown, ArrowUp } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { RangeSelector } from "@/components/layout/RangeSelector";
import { formatReportingAmount, formatSignedReportingAmount, getIntlLocale } from "@/lib/format";
import { ReportingCurrencyNote } from "@/components/ui/ReportingCurrencyNote";
import { getCurrency } from "@/lib/i18n";
import { useTranslation } from "@/lib/i18n";
import type { NetWorthRange, NetWorthSummary } from "@/types";

interface NetWorthChartProps {
  summary: NetWorthSummary | undefined;
  isLoading: boolean;
  /** Request failed with no cached data: show "—" instead of a confirmed zero. */
  unavailable?: boolean;
  range: NetWorthRange;
  onRangeChange: (range: NetWorthRange) => void;
}

function formatAxisDate(iso: string): string {
  return new Intl.DateTimeFormat(getIntlLocale(), { month: "short", day: "numeric", year: "numeric" }).format(
    new Date(`${iso}T00:00:00`)
  );
}

/** Jan-1 of every year strictly inside the range, so a multi-year chart gets
 * a year landmark on its axis instead of just two endpoint dates — lets you
 * place "5 years ago" without hovering pixel-by-pixel. Single-year ranges
 * return an empty array and the axis stays hidden, unchanged from before. */
function computeYearTicks(dates: string[]): string[] {
  if (dates.length < 2) return [];
  const start = dates[0];
  const end = dates[dates.length - 1];
  const startYear = Number(start.slice(0, 4));
  const endYear = Number(end.slice(0, 4));
  if (startYear === endYear) return [];

  const ticks: string[] = [];
  for (let year = startYear + 1; year <= endYear; year++) {
    const jan1 = `${year}-01-01`;
    if (jan1 >= start && jan1 <= end) ticks.push(jan1);
  }
  return ticks;
}

function ChartTooltip({
  active,
  payload,
  currency,
}: {
  active?: boolean;
  payload?: Array<{ payload: { date: string; value: number | null } }>;
  currency: string;
}) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="rounded-lg border border-border bg-surface-1 px-3 py-2 text-sm shadow-md">
      <p className="text-text-muted">{formatAxisDate(point.date)}</p>
      <p className="font-medium text-text-primary">{formatReportingAmount(point.value, currency)}</p>
    </div>
  );
}

export function NetWorthChart({ summary, isLoading, unavailable = false, range, onRangeChange }: NetWorthChartProps) {
  const { t } = useTranslation();
  // The figures are in the currency the backend converted them into; the
  // settings value only stands in before the first response arrives.
  const currency = summary?.reporting_currency ?? getCurrency();
  const isPositive = summary && summary.change_amount !== null ? Number(summary.change_amount) >= 0 : true;
  const trendColor = isPositive ? "var(--success)" : "var(--danger)";
  // A day without a rate stays a gap (null) rather than dropping to zero.
  const chartData =
    summary?.series.map((point) => ({ date: point.date, value: point.value === null ? null : Number(point.value) })) ?? [];
  const yearTicks = computeYearTicks(chartData.map((point) => point.date));

  return (
    <Card>
      <CardHeader className="items-start">
        <div>
          <CardTitle>{t("nav.netWorth")}</CardTitle>
          <p className="mt-1.5 text-2xl font-semibold tabular-nums text-text-primary sm:text-[28px]">
            {isLoading ? "…" : unavailable ? "—" : formatReportingAmount(summary ? summary.current : 0, currency)}
          </p>
          {summary && (
            <p
              className="mt-1 flex items-center gap-1 text-sm font-medium"
              style={{ color: trendColor }}
            >
              {isPositive ? <ArrowUp size={14} /> : <ArrowDown size={14} />}
              {formatSignedReportingAmount(summary.change_amount, currency)}
              {summary.change_percent !== null && ` (${isPositive ? "+" : ""}${summary.change_percent.toFixed(1)}%)`}
              <span className="font-normal text-text-muted">{t("netWorth.periodSuffix")}</span>
            </p>
          )}
        </div>
        <RangeSelector value={range} onChange={onRangeChange} />
      </CardHeader>
      <CardContent>
        <div className="h-56 w-full sm:h-64">
          {isLoading || unavailable || chartData.length === 0 ? (
            <div className="flex h-full items-center justify-center text-sm text-text-muted">
              {isLoading ? t("common.loading") : unavailable ? "—" : t("netWorth.noChartData")}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 8, right: 4, bottom: 0, left: 4 }}>
                <defs>
                  <linearGradient id="netWorthFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={trendColor} stopOpacity={0.18} />
                    <stop offset="100%" stopColor={trendColor} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <YAxis hide domain={["auto", "auto"]} />
                {yearTicks.length > 0 && (
                  <XAxis
                    dataKey="date"
                    type="category"
                    ticks={yearTicks}
                    tickFormatter={(value: string) => value.slice(0, 4)}
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "var(--text-muted)", fontSize: 11 }}
                    interval="preserveStartEnd"
                  />
                )}
                <Tooltip content={<ChartTooltip currency={currency} />} cursor={{ stroke: "var(--gridline)", strokeWidth: 1 }} />
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke={trendColor}
                  strokeWidth={2}
                  fill="url(#netWorthFill)"
                  isAnimationActive={false}
                  activeDot={{ r: 4, strokeWidth: 0 }}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
        {chartData.length > 1 && (
          <div className="mt-2 flex justify-between text-xs text-text-muted">
            <span>{formatAxisDate(chartData[0].date)}</span>
            <span>{formatAxisDate(chartData[chartData.length - 1].date)}</span>
          </div>
        )}
        {summary && (
          <ReportingCurrencyNote currency={summary.reporting_currency} incomplete={summary.incomplete} className="mt-2" />
        )}
      </CardContent>
    </Card>
  );
}
