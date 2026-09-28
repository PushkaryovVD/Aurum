import { useEffect, useMemo, useState } from "react";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Input, Label, Select } from "@/components/ui/Input";
import { formatCurrency } from "@/lib/format";
import { translateCategoryName } from "@/lib/categoryLabels";
import { useTranslation, type TranslationKey } from "@/lib/i18n";
import type { Category, EnvelopeAllocationInput, EnvelopeItem } from "@/types";
import { allocationLimit, envelopeErrorKey } from "./envelopeFormLogic";

interface EnvelopeAssignModalProps {
  open: boolean;
  onClose: () => void;
  item: EnvelopeItem | null;
  categories: Category[];
  unavailableCategoryIds: number[];
  availableToAssign: string;
  onSave: (categoryId: number, input: EnvelopeAllocationInput) => Promise<unknown>;
  onDelete: (categoryId: number) => Promise<unknown>;
}

export function EnvelopeAssignModal({
  open,
  onClose,
  item,
  categories,
  unavailableCategoryIds,
  availableToAssign,
  onSave,
  onDelete,
}: EnvelopeAssignModalProps) {
  const { t, language } = useTranslation();
  const options = useMemo(
    () => categories
      .filter((category) => category.kind === "expense" && (item?.category_id === category.id || !unavailableCategoryIds.includes(category.id)))
      .sort((left, right) => translateCategoryName(left.name).localeCompare(translateCategoryName(right.name), language)),
    [categories, item?.category_id, language, unavailableCategoryIds]
  );
  const [categoryId, setCategoryId] = useState("");
  const [planned, setPlanned] = useState("");
  const [assigned, setAssigned] = useState("");
  const [rolloverPositive, setRolloverPositive] = useState(true);
  const [rolloverNegative, setRolloverNegative] = useState(true);
  const [error, setError] = useState<TranslationKey | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setCategoryId(String(item?.category_id ?? options[0]?.id ?? ""));
    setPlanned(item?.planned_amount ?? "0.00");
    setAssigned(item?.assigned_amount ?? "0.00");
    setRolloverPositive(item?.rollover_positive ?? true);
    setRolloverNegative(item?.rollover_negative ?? true);
    setError(null);
  }, [item, open, options]);

  const maximum = allocationLimit(item?.assigned_amount ?? "0.00", availableToAssign) ?? availableToAssign;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const clamped = allocationLimit(item?.assigned_amount ?? "0.00", availableToAssign, assigned);
    const normalizedRequested = allocationLimit(assigned, "0.00");
    if (!clamped || !normalizedRequested) {
      setError("envelope.error.save");
      return;
    }
    if (clamped !== normalizedRequested) {
      setAssigned(clamped);
      setError("envelope.error.available");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave(Number(categoryId), {
        planned_amount: planned,
        assigned_amount: assigned,
        rollover_positive: rolloverPositive,
        rollover_negative: rolloverNegative,
      });
      onClose();
    } catch (caught) {
      setError(envelopeErrorKey(caught instanceof ApiError ? caught : {}));
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (!item || !window.confirm(t("envelope.assign.confirmRelease"))) return;
    setSaving(true);
    try {
      await onDelete(item.category_id);
      onClose();
    } catch (caught) {
      setError(envelopeErrorKey(caught instanceof ApiError ? caught : {}));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={t("envelope.assign.title")}>
      <form onSubmit={submit} className="space-y-4">
        <div>
          <Label htmlFor="envelope-category">{t("envelope.assign.category")}</Label>
          <Select id="envelope-category" disabled={item !== null} value={categoryId} onChange={(event) => setCategoryId(event.target.value)}>
            {options.map((category) => <option key={category.id} value={category.id}>{translateCategoryName(category.name)}</option>)}
          </Select>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div><Label htmlFor="envelope-planned">{t("envelope.assign.planned")}</Label><Input id="envelope-planned" type="number" inputMode="decimal" min="0" step="0.01" required value={planned} onChange={(event) => setPlanned(event.target.value)} /></div>
          <div><Label htmlFor="envelope-assigned">{t("envelope.assign.assigned")}</Label><Input id="envelope-assigned" type="number" inputMode="decimal" min="0" step="0.01" required value={assigned} onChange={(event) => setAssigned(event.target.value)} /><p className="mt-1 text-xs text-text-muted">{t("envelope.assign.maximum", { amount: formatCurrency(maximum) })}</p></div>
        </div>
        <label className="flex items-center gap-2 text-sm text-text-secondary"><input type="checkbox" checked={rolloverPositive} onChange={(event) => setRolloverPositive(event.target.checked)} />{t("envelope.assign.rolloverPositive")}</label>
        <label className="flex items-center gap-2 text-sm text-text-secondary"><input type="checkbox" checked={rolloverNegative} onChange={(event) => setRolloverNegative(event.target.checked)} />{t("envelope.assign.rolloverNegative")}</label>
        {error && <p className="text-sm text-danger" role="alert">{t(error)}</p>}
        <div className="flex flex-wrap justify-between gap-2 pt-2">
          {item?.has_row ? <Button type="button" variant="danger" disabled={saving} onClick={remove}>{t("envelope.assign.release")}</Button> : <span />}
          <div className="flex gap-2"><Button type="button" variant="ghost" onClick={onClose}>{t("common.cancel")}</Button><Button type="submit" disabled={saving || !categoryId}>{saving ? t("common.saving") : t("common.save")}</Button></div>
        </div>
      </form>
    </Dialog>
  );
}
