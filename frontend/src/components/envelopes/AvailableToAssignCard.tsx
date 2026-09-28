import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { formatCurrency } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import type { EnvelopeMonth } from "@/types";

interface AvailableToAssignCardProps {
  month: EnvelopeMonth;
}

export function AvailableToAssignCard({ month }: AvailableToAssignCardProps) {
  const { t } = useTranslation();
  const isNegative = month.available_to_assign.trim().startsWith("-");

  return (
    <Card className={isNegative ? "border-danger/50" : undefined}>
      <CardHeader>
        <CardTitle>{t("envelope.available.title")}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className={`text-3xl font-semibold tabular-nums ${isNegative ? "text-danger" : "text-success"}`}>
          {formatCurrency(month.available_to_assign)}
        </p>
        <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
          <div className="rounded-lg bg-surface-2 p-3">
            <dt className="text-xs text-text-muted">{t("envelope.available.income")}</dt>
            <dd className="mt-1 font-medium tabular-nums text-text-primary">{formatCurrency(month.income)}</dd>
          </div>
          <div className="rounded-lg bg-surface-2 p-3">
            <dt className="text-xs text-text-muted">{t("envelope.available.assigned")}</dt>
            <dd className="mt-1 font-medium tabular-nums text-text-primary">{formatCurrency(month.assigned)}</dd>
          </div>
        </dl>
        <p className="mt-3 text-xs text-text-muted">{t("envelope.available.cumulativeHint")}</p>
      </CardContent>
    </Card>
  );
}
