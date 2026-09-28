import { AlertTriangle, Info } from "lucide-react";
import { formatCurrency } from "@/lib/format";
import { useTranslation, type TranslationKey } from "@/lib/i18n";
import type { EnvelopeWarning } from "@/types";

const WARNING_KEYS: Record<EnvelopeWarning["code"], TranslationKey> = {
  overspent: "envelope.warning.overspent",
  underfunded: "envelope.warning.underfunded",
  unbudgeted_spending: "envelope.warning.unbudgeted",
  refund_without_envelope: "envelope.warning.refundWithoutEnvelope",
  available_to_assign_negative: "envelope.warning.negativeAvailable",
  fx_coverage_incomplete: "envelope.warning.fxIncomplete",
  income_before_tracking_start: "envelope.warning.incomeBeforeStart",
  closed_month_ledger_drift: "envelope.warning.closedDrift",
};

const WARNING_TONES = new Set<EnvelopeWarning["code"]>([
  "overspent",
  "available_to_assign_negative",
  "fx_coverage_incomplete",
  "closed_month_ledger_drift",
]);

interface EnvelopeWarningsProps {
  warnings: EnvelopeWarning[];
}

export function EnvelopeWarnings({ warnings }: EnvelopeWarningsProps) {
  const { t } = useTranslation();
  if (warnings.length === 0) return null;

  return (
    <div className="space-y-2" aria-live="polite">
      {warnings.map((warning, index) => {
        const isWarning = WARNING_TONES.has(warning.code);
        const Icon = isWarning ? AlertTriangle : Info;
        const amount = warning.amount ?? warning.delta;
        return (
          <div
            key={`${warning.code}-${warning.category_id ?? "month"}-${index}`}
            data-warning-code={warning.code}
            className={`flex gap-2 rounded-lg border p-3 text-sm ${
              isWarning
                ? "border-warning/40 bg-warning/10 text-text-primary"
                : "border-border bg-surface-1 text-text-secondary"
            }`}
          >
            <Icon size={17} className="mt-0.5 shrink-0" />
            <span>{t(WARNING_KEYS[warning.code], amount ? { amount: formatCurrency(amount) } : undefined)}</span>
          </div>
        );
      })}
    </div>
  );
}
