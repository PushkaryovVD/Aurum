import { useMemo, useState } from "react";
import { History, LayoutTemplate, Plus } from "lucide-react";
import { ApiError } from "@/api/client";
import { AvailableToAssignCard } from "@/components/envelopes/AvailableToAssignCard";
import { EnvelopeAssignModal } from "@/components/envelopes/EnvelopeAssignModal";
import { EnvelopeAuditList } from "@/components/envelopes/EnvelopeAuditList";
import { EnvelopeMoveModal } from "@/components/envelopes/EnvelopeMoveModal";
import { EnvelopeTable } from "@/components/envelopes/EnvelopeTable";
import { EnvelopeTemplateModal } from "@/components/envelopes/EnvelopeTemplateModal";
import { EnvelopeWarnings } from "@/components/envelopes/EnvelopeWarnings";
import { envelopeErrorKey } from "@/components/envelopes/envelopeFormLogic";
import { ContextualHelp } from "@/components/help/ContextualHelp";
import { MonthSelector } from "@/components/layout/MonthSelector";
import { YearSelector } from "@/components/layout/YearSelector";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { useCategories } from "@/hooks/useCategories";
import {
  useCloseMonth,
  useDeleteAllocation,
  useEnvelopeAudit,
  useEnvelopeMonth,
  useEnvelopeMonths,
  useMoveEnvelope,
  useOpenEnvelopeMonth,
  useReopenMonth,
  useSetAllocation,
} from "@/hooks/useEnvelopes";
import { useTransactionYears } from "@/hooks/useTransactions";
import { useTranslation, type TranslationKey } from "@/lib/i18n";
import type { EnvelopeItem } from "@/types";

export function EnvelopePage() {
  const { t } = useTranslation();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [assignOpen, setAssignOpen] = useState(false);
  const [moveOpen, setMoveOpen] = useState(false);
  const [templateOpen, setTemplateOpen] = useState(false);
  const [selectedItem, setSelectedItem] = useState<EnvelopeItem | null>(null);
  const [actionError, setActionError] = useState<TranslationKey | null>(null);

  const { data: transactionYears } = useTransactionYears();
  const { data: monthSummaries } = useEnvelopeMonths();
  const { data: categories = [] } = useCategories();
  const { data: envelopeMonth, isLoading, isError } = useEnvelopeMonth(year, month);
  const { data: audit = [] } = useEnvelopeAudit(year, month, envelopeMonth?.tracking_start !== null);
  const openMonth = useOpenEnvelopeMonth(year, month);
  const setAllocation = useSetAllocation(year, month);
  const deleteAllocation = useDeleteAllocation(year, month);
  const moveEnvelope = useMoveEnvelope(year, month);
  const closeMonth = useCloseMonth(year, month);
  const reopenMonth = useReopenMonth(year, month);

  const years = useMemo(() => {
    const values = new Set([now.getFullYear(), ...(transactionYears ?? []), ...(monthSummaries ?? []).map((entry) => entry.year)]);
    return Array.from(values);
  }, [monthSummaries, now, transactionYears]);

  function showActionError(caught: unknown) {
    setActionError(envelopeErrorKey(caught instanceof ApiError ? caught : {}));
  }

  function editItem(item: EnvelopeItem) {
    setSelectedItem(item);
    setAssignOpen(true);
  }

  function addItem() {
    setSelectedItem(null);
    setAssignOpen(true);
  }

  function moveItem(item: EnvelopeItem) {
    setSelectedItem(item);
    setMoveOpen(true);
  }

  async function toggleClosed() {
    if (!envelopeMonth) return;
    setActionError(null);
    if (!envelopeMonth.is_closed && !window.confirm(t("envelope.closed.confirm"))) return;
    try {
      if (envelopeMonth.is_closed) await reopenMonth.mutateAsync();
      else await closeMonth.mutateAsync();
    } catch (caught) {
      showActionError(caught);
    }
  }

  const planningPending = closeMonth.isPending || reopenMonth.isPending || openMonth.isPending;

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-semibold text-text-primary">{t("envelope.title")}</h1>
        <p className="mt-1 max-w-3xl text-sm text-text-muted">{t("envelope.subtitle")}</p>
      </header>
      <ContextualHelp topicId="envelopes" />

      <div className="flex items-center gap-3">
        <div className="min-w-0 flex-1"><MonthSelector month={month} onChange={setMonth} /></div>
        <YearSelector years={years} year={year} onChange={setYear} />
      </div>

      {isLoading ? (
        <p className="py-12 text-center text-sm text-text-muted">{t("common.loading")}</p>
      ) : isError || !envelopeMonth ? (
        <p className="rounded-lg border border-danger/30 bg-danger/10 p-4 text-sm text-danger">{t("envelope.error.load")}</p>
      ) : (
        <>
          <AvailableToAssignCard month={envelopeMonth} />
          <EnvelopeWarnings warnings={envelopeMonth.warnings} />
          <p className="rounded-lg border border-border bg-surface-1 p-3 text-sm text-text-muted">{t("envelope.continuityHint")}</p>

          <Card>
            <CardHeader className="flex-col items-stretch sm:flex-row sm:items-center">
              <CardTitle>{t("envelope.title")}</CardTitle>
              <div className="grid grid-cols-1 gap-2 sm:flex">
                {envelopeMonth.tracking_start === null ? (
                  <Button type="button" disabled={planningPending} onClick={() => openMonth.mutateAsync().catch(showActionError)}>{openMonth.isPending ? t("envelope.opening") : t("envelope.openMonth")}</Button>
                ) : (
                  <>
                    <Button type="button" variant="secondary" disabled={envelopeMonth.is_closed} onClick={addItem}><Plus size={16} />{t("common.add")}</Button>
                    <Button type="button" variant="secondary" onClick={() => setTemplateOpen(true)}><LayoutTemplate size={16} />{t("envelope.template.title")}</Button>
                    <Button type="button" variant={envelopeMonth.is_closed ? "secondary" : "ghost"} disabled={planningPending} onClick={toggleClosed}>{envelopeMonth.is_closed ? t("envelope.closed.reopen") : t("envelope.closed.close")}</Button>
                  </>
                )}
              </div>
            </CardHeader>
            <CardContent>
              <EnvelopeTable items={envelopeMonth.items} categories={categories} isClosed={envelopeMonth.is_closed} onAssign={editItem} onMove={moveItem} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle><span className="flex items-center gap-2"><History size={15} />{t("envelope.audit.title")}</span></CardTitle></CardHeader>
            <CardContent><EnvelopeAuditList items={audit} /></CardContent>
          </Card>

          {actionError && <p className="text-sm text-danger" role="alert">{t(actionError)}</p>}

          <EnvelopeAssignModal
            open={assignOpen}
            onClose={() => setAssignOpen(false)}
            item={selectedItem}
            categories={categories}
            unavailableCategoryIds={envelopeMonth.items.filter((item) => item.has_row).map((item) => item.category_id)}
            availableToAssign={envelopeMonth.available_to_assign}
            onSave={(categoryId, input) => setAllocation.mutateAsync({ categoryId, input })}
            onDelete={(categoryId) => deleteAllocation.mutateAsync(categoryId)}
          />
          <EnvelopeMoveModal open={moveOpen} onClose={() => setMoveOpen(false)} source={selectedItem} items={envelopeMonth.items} onMove={(input) => moveEnvelope.mutateAsync(input)} />
          <EnvelopeTemplateModal open={templateOpen} onClose={() => setTemplateOpen(false)} year={year} month={month} items={envelopeMonth.items} isClosed={envelopeMonth.is_closed} />
        </>
      )}
    </div>
  );
}
