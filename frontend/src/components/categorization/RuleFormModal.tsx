import { useEffect, useState } from "react";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input, Label, Select } from "@/components/ui/Input";
import { useAccounts } from "@/hooks/useAccounts";
import { useCategories } from "@/hooks/useCategories";
import {
  useCreateCategorizationRule,
  useUpdateCategorizationRule,
} from "@/hooks/useCategorizationRules";
import { translateCategoryName } from "@/lib/categoryLabels";
import { CURRENCIES } from "@/lib/currency";
import { TRANSACTION_TYPE_KEYS } from "@/lib/transactionLabels";
import { useTranslation } from "@/lib/i18n";
import type { CategorizationRule, RuleMatchType, TransactionType } from "@/types";

interface RuleFormModalProps {
  open: boolean;
  onClose: () => void;
  rule?: CategorizationRule | null;
}

const MATCH_TYPES: RuleMatchType[] = ["contains", "regex"];
const TRANSACTION_TYPES: TransactionType[] = ["income", "expense", "transfer"];

function emptyForm() {
  return {
    name: "",
    match_type: "contains" as RuleMatchType,
    pattern: "",
    category_id: "",
    amount_min: "",
    amount_max: "",
    currency: "",
    account_id: "",
    transaction_type: "",
    is_enabled: true,
  };
}

export function RuleFormModal({ open, onClose, rule }: RuleFormModalProps) {
  const { t } = useTranslation();
  const { data: accounts = [] } = useAccounts();
  const { data: categories = [] } = useCategories();
  const createRule = useCreateCategorizationRule();
  const updateRule = useUpdateCategorizationRule();

  const [form, setForm] = useState(emptyForm());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setForm(
      rule
        ? {
            name: rule.name,
            match_type: rule.match_type,
            pattern: rule.pattern,
            category_id: String(rule.category_id),
            amount_min: rule.amount_min ?? "",
            amount_max: rule.amount_max ?? "",
            currency: rule.currency ?? "",
            account_id: rule.account_id === null ? "" : String(rule.account_id),
            transaction_type: rule.transaction_type ?? "",
            is_enabled: rule.is_enabled,
          }
        : emptyForm()
    );
    setError(null);
  }, [open, rule]);

  const isSaving = createRule.isPending || updateRule.isPending;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    // An empty optional field means "don't care", which the API expresses as
    // null — never as a zero bound or an empty-string currency, both of which
    // would silently narrow the rule instead of widening it.
    const input = {
      name: form.name,
      match_type: form.match_type,
      pattern: form.pattern,
      category_id: Number(form.category_id),
      amount_min: form.amount_min === "" ? null : form.amount_min,
      amount_max: form.amount_max === "" ? null : form.amount_max,
      currency: form.currency === "" ? null : form.currency,
      account_id: form.account_id === "" ? null : Number(form.account_id),
      transaction_type: form.transaction_type === "" ? null : (form.transaction_type as TransactionType),
      is_enabled: form.is_enabled,
    };

    try {
      if (rule) {
        await updateRule.mutateAsync({ id: rule.id, input });
      } else {
        await createRule.mutateAsync(input);
      }
      onClose();
    } catch (cause) {
      // The backend validates the regex and the amount bounds, and its message
      // says which one was wrong — more useful than a generic failure line.
      setError(cause instanceof Error ? cause.message : t("rules.saveFailed"));
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={rule ? t("rules.edit") : t("rules.add")}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <Label htmlFor="rule-name">{t("rules.name")}</Label>
          <Input
            id="rule-name"
            required
            placeholder={t("rules.namePlaceholder")}
            value={form.name}
            onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
          />
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <Label htmlFor="rule-match-type">{t("rules.matchType")}</Label>
            <Select
              id="rule-match-type"
              value={form.match_type}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, match_type: event.target.value as RuleMatchType }))
              }
            >
              {MATCH_TYPES.map((matchType) => (
                <option key={matchType} value={matchType}>
                  {matchType === "contains" ? t("rules.matchContains") : t("rules.matchRegex")}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label htmlFor="rule-pattern">{t("rules.pattern")}</Label>
            <Input
              id="rule-pattern"
              required
              placeholder={t("rules.patternPlaceholder")}
              value={form.pattern}
              onChange={(event) => setForm((prev) => ({ ...prev, pattern: event.target.value }))}
            />
          </div>
        </div>

        <div>
          <Label htmlFor="rule-category">{t("rules.category")}</Label>
          <Select
            id="rule-category"
            required
            value={form.category_id}
            onChange={(event) => setForm((prev) => ({ ...prev, category_id: event.target.value }))}
          >
            <option value="">{t("transactions.form.noCategory")}</option>
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {translateCategoryName(category.name)}
              </option>
            ))}
          </Select>
        </div>

        <fieldset className="space-y-3 rounded-lg border border-border p-3">
          <legend className="px-1 text-xs font-medium text-text-secondary">{t("rules.conditions")}</legend>
          <p className="text-xs text-text-muted">{t("rules.conditionsHint")}</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <Label htmlFor="rule-amount-min">{t("rules.amountFrom")}</Label>
              <Input
                id="rule-amount-min"
                type="number"
                step="0.01"
                min="0"
                value={form.amount_min}
                onChange={(event) => setForm((prev) => ({ ...prev, amount_min: event.target.value }))}
              />
            </div>
            <div>
              <Label htmlFor="rule-amount-max">{t("rules.amountTo")}</Label>
              <Input
                id="rule-amount-max"
                type="number"
                step="0.01"
                min="0"
                value={form.amount_max}
                onChange={(event) => setForm((prev) => ({ ...prev, amount_max: event.target.value }))}
              />
            </div>
            <div>
              <Label htmlFor="rule-currency">{t("rules.currency")}</Label>
              <Select
                id="rule-currency"
                value={form.currency}
                onChange={(event) => setForm((prev) => ({ ...prev, currency: event.target.value }))}
              >
                <option value="">{t("rules.anyCurrency")}</option>
                {CURRENCIES.map((option) => (
                  <option key={option.code} value={option.code}>
                    {option.code}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <Label htmlFor="rule-account">{t("rules.account")}</Label>
              <Select
                id="rule-account"
                value={form.account_id}
                onChange={(event) => setForm((prev) => ({ ...prev, account_id: event.target.value }))}
              >
                <option value="">{t("rules.anyAccount")}</option>
                {accounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.name}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <Label htmlFor="rule-transaction-type">{t("rules.type")}</Label>
              <Select
                id="rule-transaction-type"
                value={form.transaction_type}
                onChange={(event) => setForm((prev) => ({ ...prev, transaction_type: event.target.value }))}
              >
                <option value="">{t("rules.anyType")}</option>
                {TRANSACTION_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {t(TRANSACTION_TYPE_KEYS[type])}
                  </option>
                ))}
              </Select>
            </div>
          </div>
        </fieldset>

        <label className="flex items-center gap-2 text-sm text-text-secondary">
          <input
            type="checkbox"
            checked={form.is_enabled}
            onChange={(event) => setForm((prev) => ({ ...prev, is_enabled: event.target.checked }))}
          />
          {t("rules.enabled")}
        </label>

        {error && <p className="text-sm text-danger">{error}</p>}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" disabled={isSaving}>
            {isSaving ? t("common.saving") : t("common.save")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
