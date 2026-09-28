import { formatCurrency, getIntlLocale } from "@/lib/format";
import { useTranslation, type TranslationKey } from "@/lib/i18n";
import type { EnvelopeAuditEvent } from "@/types";

const EVENT_KEYS: Record<EnvelopeAuditEvent["event_type"], TranslationKey> = {
  allocation: "envelope.audit.allocation",
  move: "envelope.audit.move",
  template_applied: "envelope.audit.template_applied",
  month_closed: "envelope.audit.month_closed",
  month_reopened: "envelope.audit.month_reopened",
};

interface EnvelopeAuditListProps {
  items: EnvelopeAuditEvent[];
}

export function EnvelopeAuditList({ items }: EnvelopeAuditListProps) {
  const { t } = useTranslation();
  if (items.length === 0) return <p className="py-4 text-sm text-text-muted">{t("envelope.audit.empty")}</p>;

  return (
    <ol className="divide-y divide-gridline">
      {items.map((item) => (
        <li key={item.id} className="flex items-start justify-between gap-3 py-3 text-sm">
          <div className="min-w-0"><p className="font-medium text-text-primary">{t(EVENT_KEYS[item.event_type])}</p>{item.note && <p className="mt-0.5 break-words text-xs text-text-muted">{item.note}</p>}<time className="mt-1 block text-xs text-text-muted">{new Intl.DateTimeFormat(getIntlLocale(), { dateStyle: "medium", timeStyle: "short" }).format(new Date(item.created_at))}</time></div>
          <span className="shrink-0 tabular-nums text-text-secondary">{formatCurrency(item.amount)}</span>
        </li>
      ))}
    </ol>
  );
}
