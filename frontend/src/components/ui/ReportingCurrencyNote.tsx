import { useTranslation } from "@/lib/i18n";
import { cn } from "@/lib/utils";

interface ReportingCurrencyNoteProps {
  /** The `reporting_currency` the response says its amounts are in. */
  currency: string;
  /** The response's `incomplete` flag: some amount had no exchange rate. */
  incomplete?: boolean;
  className?: string;
}

/** Says out loud what an aggregate's numbers are: KZT ledger sums converted
 * into the workspace currency (only shown when that currency isn't KZT), and —
 * when the backend had no rate for part of it — that the "—" amounts are
 * unknown rather than zero. Renders nothing for a plain, complete KZT answer. */
export function ReportingCurrencyNote({ currency, incomplete = false, className }: ReportingCurrencyNoteProps) {
  const { t } = useTranslation();
  const converted = currency.toUpperCase() !== "KZT";
  if (!converted && !incomplete) return null;
  return (
    <div className={cn("space-y-1 text-[11px] leading-4", className)}>
      {converted && !incomplete && <p className="text-text-muted">{t("reporting.convertedNote", { currency })}</p>}
      {incomplete && (
        <p className="text-warning" role="status">
          {t("reporting.incomplete", { currency })}
        </p>
      )}
    </div>
  );
}
