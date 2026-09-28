import { useEffect, useState } from "react";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Input, Label, Select } from "@/components/ui/Input";
import {
  useApplyTemplate,
  useCreateTemplate,
  useDeleteTemplate,
  useFund,
  useFundNextMonth,
  useTemplates,
} from "@/hooks/useEnvelopes";
import { formatCurrency } from "@/lib/format";
import { useTranslation, type TranslationKey } from "@/lib/i18n";
import type { EnvelopeItem } from "@/types";
import { envelopeErrorKey } from "./envelopeFormLogic";

interface EnvelopeTemplateModalProps {
  open: boolean;
  onClose: () => void;
  year: number;
  month: number;
  items: EnvelopeItem[];
  isClosed: boolean;
}

export function EnvelopeTemplateModal({ open, onClose, year, month, items, isClosed }: EnvelopeTemplateModalProps) {
  const { t } = useTranslation();
  const { data: templates = [] } = useTemplates();
  const createTemplate = useCreateTemplate();
  const deleteTemplate = useDeleteTemplate();
  const applyTemplate = useApplyTemplate(year, month);
  const fund = useFund(year, month);
  const fundNext = useFundNextMonth(year, month);
  const [templateId, setTemplateId] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<TranslationKey | null>(null);
  const [unfunded, setUnfunded] = useState<Array<{ category_id: number; shortfall: string }>>([]);

  useEffect(() => {
    if (!open) return;
    setTemplateId(String(templates[0]?.id ?? ""));
    setName("");
    setError(null);
    setUnfunded([]);
  }, [open, templates]);

  const pending = createTemplate.isPending || deleteTemplate.isPending || applyTemplate.isPending || fund.isPending || fundNext.isPending;

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
    } catch (caught) {
      setError(envelopeErrorKey(caught instanceof ApiError ? caught : {}));
    }
  }

  async function createCurrentPlan() {
    const trimmed = name.trim();
    if (!trimmed) return;
    await run(async () => {
      const created = await createTemplate.mutateAsync({
        name: trimmed,
        items: items.filter((item) => item.has_row).map((item) => ({
          category_id: item.category_id,
          planned_amount: item.planned_amount,
          rollover_positive: item.rollover_positive,
          rollover_negative: item.rollover_negative,
        })),
      });
      setTemplateId(String(created.id));
      setName("");
    });
  }

  async function fundPlan() {
    await run(async () => {
      const result = await fund.mutateAsync({ template_id: templateId ? Number(templateId) : null });
      setUnfunded(result.unfunded ?? []);
    });
  }

  async function removeTemplate() {
    const selected = templates.find((template) => template.id === Number(templateId));
    if (!selected || !window.confirm(t("envelope.template.confirmDelete", { name: selected.name }))) return;
    await run(async () => {
      await deleteTemplate.mutateAsync(selected.id);
      setTemplateId("");
    });
  }

  return (
    <Dialog open={open} onClose={onClose} title={t("envelope.template.title")}>
      <div className="space-y-5">
        <div>
          <Label htmlFor="envelope-template">{t("envelope.template.select")}</Label>
          <Select id="envelope-template" value={templateId} onChange={(event) => setTemplateId(event.target.value)}>
            <option value="">{t("envelope.template.none")}</option>
            {templates.map((template) => <option key={template.id} value={template.id}>{template.name}</option>)}
          </Select>
          <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
            <Button type="button" variant="secondary" disabled={pending || isClosed || !templateId} onClick={() => run(() => applyTemplate.mutateAsync(Number(templateId)))}>{t("envelope.template.apply")}</Button>
            <Button type="button" disabled={pending || isClosed} onClick={fundPlan}>{t("envelope.template.fund")}</Button>
            <Button type="button" className="sm:col-span-2" disabled={pending || isClosed} onClick={() => run(() => fundNext.mutateAsync())}>{t("envelope.template.nextMonth")}</Button>
            <Button type="button" variant="ghost" className="sm:col-span-2 text-danger" disabled={pending || !templateId} onClick={removeTemplate}>{t("envelope.template.delete")}</Button>
          </div>
        </div>

        <div className="border-t border-gridline pt-4">
          <Label htmlFor="envelope-template-name">{t("envelope.template.createTitle")}</Label>
          <div className="flex gap-2"><Input id="envelope-template-name" maxLength={100} value={name} onChange={(event) => setName(event.target.value)} placeholder={t("envelope.template.name")} /><Button type="button" variant="secondary" disabled={pending || !name.trim() || items.every((item) => !item.has_row)} onClick={createCurrentPlan}>{t("envelope.template.create")}</Button></div>
        </div>

        {unfunded.length > 0 && <div className="rounded-lg bg-warning/10 p-3 text-sm text-text-primary">{unfunded.map((entry) => <p key={entry.category_id}>{t("envelope.template.unfunded", { amount: formatCurrency(entry.shortfall) })}</p>)}</div>}
        {error && <p className="text-sm text-danger" role="alert">{t(error)}</p>}
        <div className="flex justify-end"><Button type="button" variant="ghost" onClick={onClose}>{t("common.close")}</Button></div>
      </div>
    </Dialog>
  );
}
