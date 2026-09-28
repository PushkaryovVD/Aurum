import { useEffect, useState } from "react";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Input, Label, Select } from "@/components/ui/Input";
import { translateCategoryName } from "@/lib/categoryLabels";
import { useTranslation, type TranslationKey } from "@/lib/i18n";
import type { EnvelopeItem, EnvelopeMoveInput } from "@/types";
import { envelopeErrorKey, moveValidationKey } from "./envelopeFormLogic";

interface EnvelopeMoveModalProps {
  open: boolean;
  onClose: () => void;
  source: EnvelopeItem | null;
  items: EnvelopeItem[];
  onMove: (input: EnvelopeMoveInput) => Promise<unknown>;
}

export function EnvelopeMoveModal({ open, onClose, source, items, onMove }: EnvelopeMoveModalProps) {
  const { t } = useTranslation();
  const destinations = items.filter((item) => item.has_row && item.category_id !== source?.category_id);
  const [toCategoryId, setToCategoryId] = useState("");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<TranslationKey | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setToCategoryId(String(destinations[0]?.category_id ?? ""));
    setAmount("");
    setNote("");
    setError(null);
  }, [open, source?.category_id]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!source) return;
    const destinationId = Number(toCategoryId);
    const validation = moveValidationKey(amount, source.assigned_amount, source.category_id, destinationId);
    if (validation) {
      setError(validation);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onMove({ from_category_id: source.category_id, to_category_id: destinationId, amount, note: note.trim() || null });
      onClose();
    } catch (caught) {
      setError(envelopeErrorKey(caught instanceof ApiError ? caught : {}));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={t("envelope.move.title")}>
      <form onSubmit={submit} className="space-y-4">
        <div><Label>{t("envelope.move.from")}</Label><p className="text-sm text-text-primary">{source ? translateCategoryName(source.category_name) : ""}</p></div>
        <div><Label htmlFor="envelope-move-to">{t("envelope.move.to")}</Label><Select id="envelope-move-to" value={toCategoryId} onChange={(event) => setToCategoryId(event.target.value)}>{destinations.map((item) => <option key={item.category_id} value={item.category_id}>{translateCategoryName(item.category_name)}</option>)}</Select></div>
        <div><Label htmlFor="envelope-move-amount">{t("envelope.move.amount")}</Label><Input id="envelope-move-amount" type="number" inputMode="decimal" min="0.01" step="0.01" required value={amount} onChange={(event) => setAmount(event.target.value)} /></div>
        <div><Label htmlFor="envelope-move-note">{t("envelope.move.note")}</Label><Input id="envelope-move-note" maxLength={500} value={note} onChange={(event) => setNote(event.target.value)} /></div>
        {error && <p className="text-sm text-danger" role="alert">{t(error)}</p>}
        <div className="flex justify-end gap-2"><Button type="button" variant="ghost" onClick={onClose}>{t("common.cancel")}</Button><Button type="submit" disabled={saving || destinations.length === 0}>{saving ? t("common.saving") : t("envelope.action.move")}</Button></div>
      </form>
    </Dialog>
  );
}
