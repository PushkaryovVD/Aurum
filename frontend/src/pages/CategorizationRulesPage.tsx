import { useState } from "react";
import { ArrowDown, ArrowUp, Pencil, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { RuleFormModal } from "@/components/categorization/RuleFormModal";
import { useAccounts } from "@/hooks/useAccounts";
import {
  useApplyCategorizationRules,
  useCategorizationRules,
  useDeleteCategorizationRule,
  useReorderCategorizationRules,
  useUpdateCategorizationRule,
} from "@/hooks/useCategorizationRules";
import { translateCategoryName } from "@/lib/categoryLabels";
import { useTranslation } from "@/lib/i18n";
import { TRANSACTION_TYPE_KEYS } from "@/lib/transactionLabels";
import { cn } from "@/lib/utils";
import type { CategorizationRule, RuleApplyResult } from "@/types";

export function CategorizationRulesPage() {
  const { t } = useTranslation();
  const { data: rules = [], isLoading } = useCategorizationRules();
  const { data: accounts = [] } = useAccounts();
  const updateRule = useUpdateCategorizationRule();
  const deleteRule = useDeleteCategorizationRule();
  const reorder = useReorderCategorizationRules();
  const apply = useApplyCategorizationRules();

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<CategorizationRule | null>(null);
  const [effect, setEffect] = useState<RuleApplyResult | null>(null);

  function openCreate() {
    setEditing(null);
    setModalOpen(true);
  }

  function openEdit(rule: CategorizationRule) {
    setEditing(rule);
    setModalOpen(true);
  }

  /** Swaps this rule with its neighbour and posts the complete new order —
   * the API refuses a partial one, so the whole list goes every time. */
  async function move(rule: CategorizationRule, offset: -1 | 1) {
    const index = rules.findIndex((item) => item.id === rule.id);
    const target = index + offset;
    if (index < 0 || target < 0 || target >= rules.length) return;
    const ordered = rules.map((item) => item.id);
    [ordered[index], ordered[target]] = [ordered[target], ordered[index]];
    await reorder.mutateAsync(ordered);
  }

  async function toggle(rule: CategorizationRule) {
    await updateRule.mutateAsync({ id: rule.id, input: { is_enabled: !rule.is_enabled } });
  }

  async function remove(rule: CategorizationRule) {
    if (!window.confirm(t("rules.deleteConfirm", { name: rule.name }))) return;
    await deleteRule.mutateAsync(rule.id);
  }

  /** Only ever a report — the same call with dryRun=false is what writes, and
   * that one asks first. */
  async function check() {
    setEffect(await apply.mutateAsync({ dryRun: true }));
  }

  async function runApply() {
    if (!window.confirm(t("rules.applyConfirm"))) return;
    setEffect(await apply.mutateAsync({ dryRun: false }));
  }

  function conditionsOf(rule: CategorizationRule): string[] {
    const parts: string[] = [];
    if (rule.amount_min !== null || rule.amount_max !== null) {
      const from = rule.amount_min ?? "0";
      parts.push(
        rule.amount_max === null
          ? `${t("rules.amountFrom")} ${from}`
          : `${from}–${rule.amount_max}`
      );
    }
    if (rule.currency) parts.push(rule.currency);
    if (rule.account_id !== null) {
      const account = accounts.find((item) => item.id === rule.account_id);
      if (account) parts.push(account.name);
    }
    if (rule.transaction_type) parts.push(t(TRANSACTION_TYPE_KEYS[rule.transaction_type]));
    return parts;
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>{t("rules.title")}</CardTitle>
          <Button onClick={openCreate}>
            <Plus size={16} />
            {t("common.add")}
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-text-secondary">{t("rules.subtitle")}</p>

          {isLoading ? (
            <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : rules.length === 0 ? (
            <p className="py-10 text-center text-sm text-text-muted">{t("rules.empty")}</p>
          ) : (
            <ul className="rounded-lg border border-border px-3">
              {rules.map((rule, index) => {
                const conditions = conditionsOf(rule);
                return (
                  <li
                    key={rule.id}
                    className="flex flex-col gap-3 border-b border-border py-3 last:border-b-0 sm:flex-row sm:items-start"
                  >
                    <div className="flex shrink-0 items-center gap-1">
                      <button
                        type="button"
                        title={t("rules.moveUp")}
                        aria-label={t("rules.moveUp")}
                        disabled={index === 0}
                        onClick={() => move(rule, -1)}
                        className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-30"
                      >
                        <ArrowUp size={16} />
                      </button>
                      <button
                        type="button"
                        title={t("rules.moveDown")}
                        aria-label={t("rules.moveDown")}
                        disabled={index === rules.length - 1}
                        onClick={() => move(rule, 1)}
                        className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-30"
                      >
                        <ArrowDown size={16} />
                      </button>
                      <span className="w-5 text-center text-xs text-text-muted">{index + 1}</span>
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className={cn(
                            "text-sm font-medium text-text-primary",
                            !rule.is_enabled && "text-text-muted line-through"
                          )}
                        >
                          {rule.name}
                        </span>
                        <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-text-secondary">
                          {rule.match_type === "contains" ? t("rules.matchContains") : t("rules.matchRegex")}
                          {": "}
                          {rule.pattern}
                        </span>
                        {!rule.is_enabled && (
                          <span className="text-xs text-warning">{t("rules.disable")}</span>
                        )}
                      </div>
                      <p className="mt-1 flex items-center gap-1.5 text-sm text-text-secondary">
                        <span
                          className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
                          style={{ backgroundColor: rule.category_color ?? "#888888" }}
                        />
                        {rule.category_name ? translateCategoryName(rule.category_name) : ""}
                      </p>
                      {conditions.length > 0 && (
                        <p className="mt-1 flex flex-wrap gap-1.5">
                          {conditions.map((condition) => (
                            <span
                              key={condition}
                              className="rounded bg-surface-2 px-1.5 py-0.5 text-xs text-text-muted"
                            >
                              {condition}
                            </span>
                          ))}
                        </p>
                      )}
                    </div>

                    <div className="flex shrink-0 items-center gap-1">
                      <Button variant="ghost" onClick={() => toggle(rule)}>
                        {rule.is_enabled ? t("rules.disable") : t("rules.enable")}
                      </Button>
                      <button
                        type="button"
                        title={t("rules.edit")}
                        aria-label={t("rules.edit")}
                        onClick={() => openEdit(rule)}
                        className="rounded-md p-1.5 text-text-muted hover:bg-surface-2"
                      >
                        <Pencil size={16} />
                      </button>
                      <button
                        type="button"
                        title={t("rules.delete")}
                        aria-label={t("rules.delete")}
                        onClick={() => remove(rule)}
                        className="rounded-md p-1.5 text-danger hover:bg-surface-2"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}

          {rules.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 border-t border-border pt-4">
              <Button variant="secondary" onClick={check} disabled={apply.isPending}>
                {t("rules.preview")}
              </Button>
              <Button onClick={runApply} disabled={apply.isPending}>
                {t("rules.apply")}
              </Button>
              <span className="text-xs text-text-muted">{t("rules.previewHint")}</span>
            </div>
          )}

          {effect && (
            <div className="rounded-lg bg-surface-2 p-3 text-sm">
              <p className="font-medium text-text-primary">
                {t("rules.considered")}: {effect.considered} · {t("rules.matched")}: {effect.matched}
                {!effect.dry_run && ` · ${t("rules.written")}: ${effect.written}`}
              </p>
              <ul className="mt-2 space-y-1">
                {effect.items
                  .filter((item) => item.matched > 0)
                  .map((item) => (
                    <li key={item.rule_id} className="text-xs text-text-secondary">
                      <span className="font-medium">{item.name}</span>
                      {` — ${item.matched}`}
                      {item.samples.length > 0 && (
                        <span className="text-text-muted">
                          {` (${t("rules.samples")}: ${item.samples.join(", ")})`}
                        </span>
                      )}
                    </li>
                  ))}
                {effect.matched === 0 && <li className="text-xs text-text-muted">{t("rules.noMatches")}</li>}
              </ul>
            </div>
          )}
        </CardContent>
      </Card>

      <RuleFormModal open={modalOpen} onClose={() => setModalOpen(false)} rule={editing} />
    </div>
  );
}
