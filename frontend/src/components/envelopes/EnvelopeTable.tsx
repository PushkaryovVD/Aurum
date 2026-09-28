import { ArrowLeftRight, Pencil } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { formatCurrency, formatSignedCurrency } from "@/lib/format";
import { getCategoryIcon } from "@/lib/icons";
import { translateCategoryName } from "@/lib/categoryLabels";
import { useTranslation } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { Category, EnvelopeItem } from "@/types";
import { envelopeProgressPercent } from "./envelopeFormLogic";

interface EnvelopeTableProps {
  items: EnvelopeItem[];
  categories?: Category[];
  isClosed: boolean;
  onAssign: (item: EnvelopeItem) => void;
  onMove: (item: EnvelopeItem) => void;
}

export function orderEnvelopeItems(items: EnvelopeItem[], categories: Category[]): Array<{ item: EnvelopeItem; depth: 0 | 1 }> {
  const itemByCategory = new Map(items.map((item) => [item.category_id, item]));
  const categoryById = new Map(categories.map((category) => [category.id, category]));
  const ordered: Array<{ item: EnvelopeItem; depth: 0 | 1 }> = [];
  const seen = new Set<number>();
  const parents = categories
    .filter((category) => category.parent_id === null)
    .sort((left, right) => left.sort_order - right.sort_order || left.id - right.id);

  for (const parent of parents) {
    const parentItem = itemByCategory.get(parent.id);
    if (parentItem) {
      ordered.push({ item: parentItem, depth: 0 });
      seen.add(parent.id);
    }
    const children = categories
      .filter((category) => category.parent_id === parent.id)
      .sort((left, right) => left.sort_order - right.sort_order || left.id - right.id);
    for (const child of children) {
      const childItem = itemByCategory.get(child.id);
      if (childItem) {
        ordered.push({ item: childItem, depth: 1 });
        seen.add(child.id);
      }
    }
  }

  for (const item of items) {
    if (!seen.has(item.category_id)) {
      ordered.push({ item, depth: categoryById.get(item.category_id)?.parent_id === null ? 0 : 1 });
    }
  }
  return ordered;
}

function StatusPills({ item }: { item: EnvelopeItem }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap gap-1">
      {item.is_overspent && <span className="rounded-full bg-danger/10 px-2 py-0.5 text-xs text-danger">{t("envelope.status.overspent")}</span>}
      {item.is_unbudgeted && <span className="rounded-full bg-warning/10 px-2 py-0.5 text-xs text-warning">{t("envelope.status.unbudgeted")}</span>}
    </div>
  );
}

function CategoryLabel({ item, depth = 0 }: { item: EnvelopeItem; depth?: 0 | 1 }) {
  const Icon = getCategoryIcon(item.category_icon);
  return (
    <div className={cn("flex min-w-0 items-center gap-2", depth === 1 && "ml-5")}>
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full" style={{ backgroundColor: `${item.category_color}26` }}>
        <Icon size={15} style={{ color: item.category_color }} />
      </span>
      <span className="min-w-0 truncate font-medium text-text-primary">{translateCategoryName(item.category_name)}</span>
    </div>
  );
}

function Progress({ item }: { item: EnvelopeItem }) {
  const percent = envelopeProgressPercent(item.available, item.planned_amount);
  return (
    <span className="mt-2 block h-1.5 overflow-hidden rounded-full bg-surface-2">
      <span className={cn("block h-full rounded-full", item.is_overspent ? "bg-danger" : "bg-success")} style={{ width: `${percent}%` }} />
    </span>
  );
}

export function EnvelopeTable({ items, categories = [], isClosed, onAssign, onMove }: EnvelopeTableProps) {
  const { t } = useTranslation();
  if (items.length === 0) {
    return <p className="py-8 text-center text-sm text-text-muted">{t("envelope.empty")}</p>;
  }

  const orderedItems = categories.length > 0
    ? orderEnvelopeItems(items, categories)
    : items.map((item) => ({ item, depth: 0 as const }));

  return (
    <div>
      {isClosed && <p className="mb-3 rounded-lg bg-surface-2 p-3 text-sm text-text-secondary">{t("envelope.closed.readOnly")}</p>}

      <ul className="space-y-3 md:hidden">
        {orderedItems.map(({ item, depth }) => (
          <li key={item.category_id} className={cn("rounded-xl border p-3", item.is_overspent ? "border-danger/40" : "border-border")}>
            <div className="flex items-start justify-between gap-2">
              <CategoryLabel item={item} depth={depth} />
              <StatusPills item={item} />
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-sm">
              <div><dt className="text-xs text-text-muted">{t("envelope.column.planned")}</dt><dd className="tabular-nums">{formatCurrency(item.planned_amount)}</dd></div>
              <div><dt className="text-xs text-text-muted">{t("envelope.column.assigned")}</dt><dd className="tabular-nums">{formatCurrency(item.assigned_amount)}</dd></div>
              <div><dt className="text-xs text-text-muted">{t("envelope.column.activity")}</dt><dd className="tabular-nums">{formatSignedCurrency(item.activity)}</dd></div>
              <div><dt className="text-xs text-text-muted">{t("envelope.column.available")}</dt><dd className={cn("font-semibold tabular-nums", item.is_overspent && "text-danger")}>{formatCurrency(item.available)}</dd></div>
            </dl>
            <Progress item={item} />
            <div className="mt-3 grid grid-cols-2 gap-2">
              <Button type="button" variant="secondary" disabled={isClosed} onClick={() => onAssign(item)}><Pencil size={15} />{t("envelope.action.plan")}</Button>
              <Button type="button" variant="ghost" disabled={isClosed || !item.has_row} onClick={() => onMove(item)}><ArrowLeftRight size={15} />{t("envelope.action.move")}</Button>
            </div>
          </li>
        ))}
      </ul>

      <div className="hidden overflow-x-auto md:block">
        <table className="w-full text-sm">
          <thead><tr className="border-b border-gridline text-left text-xs text-text-muted">
            <th className="pb-2 pr-3 font-medium">{t("envelope.column.category")}</th>
            <th className="pb-2 px-3 text-right font-medium">{t("envelope.column.planned")}</th>
            <th className="pb-2 px-3 text-right font-medium">{t("envelope.column.assigned")}</th>
            <th className="pb-2 px-3 text-right font-medium">{t("envelope.column.activity")}</th>
            <th className="pb-2 px-3 text-right font-medium">{t("envelope.column.available")}</th>
            <th className="pb-2 pl-3 text-right font-medium">{t("envelope.column.actions")}</th>
          </tr></thead>
          <tbody className="divide-y divide-gridline">
            {orderedItems.map(({ item, depth }) => (
              <tr key={item.category_id}>
                <td className="py-3 pr-3"><CategoryLabel item={item} depth={depth} /><div className="mt-1 pl-10"><StatusPills item={item} /></div></td>
                <td className="px-3 py-3 text-right tabular-nums">{formatCurrency(item.planned_amount)}</td>
                <td className="px-3 py-3 text-right tabular-nums">{formatCurrency(item.assigned_amount)}</td>
                <td className="px-3 py-3 text-right tabular-nums">{formatSignedCurrency(item.activity)}</td>
                <td className={cn("px-3 py-3 text-right font-semibold tabular-nums", item.is_overspent && "text-danger")}>{formatCurrency(item.available)}<Progress item={item} /></td>
                <td className="py-3 pl-3"><div className="flex justify-end gap-1">
                  <button type="button" disabled={isClosed} aria-label={t("envelope.action.planCategory", { category: translateCategoryName(item.category_name) })} onClick={() => onAssign(item)} className="rounded-md p-2 text-text-muted hover:bg-surface-2 disabled:opacity-40"><Pencil size={15} /></button>
                  <button type="button" disabled={isClosed || !item.has_row} aria-label={t("envelope.action.moveCategory", { category: translateCategoryName(item.category_name) })} onClick={() => onMove(item)} className="rounded-md p-2 text-text-muted hover:bg-surface-2 disabled:opacity-40"><ArrowLeftRight size={15} /></button>
                </div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
