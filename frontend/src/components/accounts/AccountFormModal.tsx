import { useEffect, useState } from "react";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input, Label, Select } from "@/components/ui/Input";
import { useCreateAccount, useUpdateAccount } from "@/hooks/useAccounts";
import { CURRENCIES, getCurrencyLabel } from "@/lib/currency";
import { getCurrency, useTranslation, type TranslationKey } from "@/lib/i18n";
import type { AccountType, AccountWithBalance } from "@/types";

interface AccountFormModalProps {
  open: boolean;
  onClose: () => void;
  /** The Accounts page's shape rather than a bare Account — its
   * transaction_count is what decides whether the currency is still editable. */
  account?: AccountWithBalance | null;
}

const ACCOUNT_TYPES: AccountType[] = ["checking", "debit_card", "savings", "credit_card", "cash", "investment", "other"];

/** A new account starts in the app's primary currency (Settings) — the one the
 * user already thinks in — instead of a hard-coded KZT. */
function emptyForm() {
  return { name: "", type: "checking" as AccountType, currency: getCurrency().toUpperCase() };
}

export function AccountFormModal({ open, onClose, account }: AccountFormModalProps) {
  const { t, language } = useTranslation();
  const createAccount = useCreateAccount();
  const updateAccount = useUpdateAccount();

  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState<string | null>(null);

  // An account whose history is already recorded in one currency can't be
  // re-labelled — every transaction on it stores amounts, a KZT snapshot and
  // its own currency derived from the account's. The backend refuses the change
  // too (see account_service.update_account); this just makes the rule visible
  // instead of letting the user discover it as a failed save.
  const currencyLocked = Boolean(account && account.transaction_count > 0);

  useEffect(() => {
    if (!open) return;
    setForm(
      account
        ? { name: account.name, type: account.type, currency: account.currency.toUpperCase() }
        : emptyForm()
    );
    setError(null);
  }, [open, account]);

  const isSaving = createAccount.isPending || updateAccount.isPending;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    try {
      if (account) {
        await updateAccount.mutateAsync({ id: account.id, input: form });
      } else {
        await createAccount.mutateAsync(form);
      }
      onClose();
    } catch {
      setError(t("account.form.saveError"));
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={account ? t("account.form.editTitle") : t("account.form.newTitle")}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <Label htmlFor="account-name">{t("account.form.nameLabel")}</Label>
          <Input
            id="account-name"
            required
            placeholder={t("account.form.namePlaceholder")}
            value={form.name}
            onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
          />
        </div>

        <div>
          <Label htmlFor="account-type">{t("account.form.typeLabel")}</Label>
          <Select
            id="account-type"
            value={form.type}
            onChange={(event) => setForm((prev) => ({ ...prev, type: event.target.value as AccountType }))}
          >
            {ACCOUNT_TYPES.map((type) => (
              <option key={type} value={type}>
                {t(`account.type.${type}` as TranslationKey)}
              </option>
            ))}
          </Select>
        </div>

        <div>
          <Label htmlFor="account-currency">{t("account.form.currencyLabel")}</Label>
          <Select
            id="account-currency"
            value={form.currency}
            disabled={currencyLocked}
            onChange={(event) => setForm((prev) => ({ ...prev, currency: event.target.value }))}
          >
            {CURRENCIES.map((option) => (
              <option key={option.code} value={option.code}>
                {getCurrencyLabel(option.code, language)}
              </option>
            ))}
            {/* A currency that isn't in the curated list (e.g. one restored from
                a backup) must still be selectable, or editing the account would
                silently move it onto a different currency. */}
            {!CURRENCIES.some((option) => option.code === form.currency) && (
              <option value={form.currency}>{form.currency}</option>
            )}
          </Select>
          {currencyLocked && <p className="mt-1 text-xs text-text-muted">{t("account.form.currencyLocked")}</p>}
        </div>

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
