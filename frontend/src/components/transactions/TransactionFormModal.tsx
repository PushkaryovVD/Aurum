import { useEffect, useMemo, useState } from "react";
import { Plus, X } from "lucide-react";
import { Link } from "react-router-dom";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input, Label, Select } from "@/components/ui/Input";
import { TagInput } from "@/components/transactions/TagInput";
import { useAccounts } from "@/hooks/useAccounts";
import { useCategories } from "@/hooks/useCategories";
import { useCreateTransaction, useUpdateTransaction } from "@/hooks/useTransactions";
import { useExchangeRate } from "@/hooks/useExchangeRate";
import { useTranslation } from "@/lib/i18n";
import { CURRENCIES } from "@/lib/currency";
import { buildHierarchicalCategories, translateCategoryName } from "@/lib/categoryLabels";
import { formatCurrency } from "@/lib/format";
import { divideDecimal, multiplyDecimal } from "@/lib/decimal";
import type { Tag, Transaction, TransactionInput, TransactionSplitInput, TransactionType } from "@/types";

interface TransactionFormModalProps {
  open: boolean;
  onClose: () => void;
  transaction?: Transaction | null;
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

const EMPTY_FORM = {
  type: "expense" as TransactionType,
  account_id: "",
  category_id: "",
  transfer_account_id: "",
  // `amount` is what the account is actually debited, in the account's own
  // currency — the figure that moves the balance. `transaction_amount` is the
  // same operation expressed in its own `currency`; the two differ only for a
  // foreign-currency purchase, where `rate` links them.
  amount: "",
  currency: "",
  transaction_amount: "",
  rate: "",
  exchange_rate_to_kzt: "",
  transfer_amount: "",
  description: "",
  merchant: "",
  notes: "",
  date: todayIso(),
};

interface SplitRowState {
  key: string;
  category_id: string;
  amount: string;
  note: string;
}

// crypto.randomUUID() only exists in secure contexts (HTTPS/localhost) — on plain
// HTTP (e.g. accessing the app by LAN IP) it's undefined and throws a TypeError.
// This key is only a local React list key, never sent to the backend, so a
// Math.random()-based fallback is fine when the Web Crypto API isn't available.
function generateRowKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `split-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function emptySplitRow(): SplitRowState {
  return { key: generateRowKey(), category_id: "", amount: "", note: "" };
}

// Cents, not floats — a plain Number sum of "0.10" + "0.20" style amounts can
// drift from the transaction total by fractions of a cent, which would
// falsely trip the "must add up exactly" check the backend also enforces.
function toCents(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.round(parsed * 100) : 0;
}

/** The account-currency figure for a foreign-currency amount, or "" while
 * either side is still unknown. */
function debitFor(transactionAmount: string, rate: string): string {
  return transactionAmount && rate ? multiplyDecimal(transactionAmount, rate, 2) ?? "" : "";
}

export function TransactionFormModal({ open, onClose, transaction }: TransactionFormModalProps) {
  const { t, language } = useTranslation();
  const { data: accounts } = useAccounts();
  const { data: categories } = useCategories();
  const createTransaction = useCreateTransaction();
  const updateTransaction = useUpdateTransaction();

  const [form, setForm] = useState(EMPTY_FORM);
  const [tags, setTags] = useState<Tag[]>([]);
  const [splitMode, setSplitMode] = useState(false);
  const [splitRows, setSplitRows] = useState<SplitRowState[]>([emptySplitRow(), emptySplitRow()]);
  const [error, setError] = useState<string | null>(null);
  const [rateEdited, setRateEdited] = useState(false);
  const [amountEdited, setAmountEdited] = useState(false);

  useEffect(() => {
    if (!open) return;
    if (transaction) {
      const hasSplits = transaction.splits.length > 0;
      // A split's categories always share one parent (see
      // routes/transactions.py's _build_splits) — derive that shared base
      // from whichever split's category is still live. If every split's
      // category was since deleted, there's nothing to derive from; the
      // base field is left blank and the user has to pick one again.
      const baseCategory = hasSplits ? transaction.splits.find((split) => split.category)?.category : null;
      setForm({
        type: transaction.type,
        account_id: String(transaction.account_id),
        category_id: hasSplits
          ? baseCategory
            ? String(baseCategory.parent_id ?? baseCategory.id)
            : ""
          : transaction.category_id
            ? String(transaction.category_id)
            : "",
        transfer_account_id: transaction.transfer_account_id ? String(transaction.transfer_account_id) : "",
        amount: transaction.amount,
        currency: transaction.currency,
        transaction_amount: transaction.transaction_amount,
        // Derived from amount / transaction_amount (or the NBK rate) rather
        // than stored — the form recomputes it on the fly.
        rate: "",
        exchange_rate_to_kzt:
          transaction.exchange_rate_source === "manual" || transaction.exchange_rate_source === "csv"
            ? transaction.exchange_rate_to_kzt ?? ""
            : "",
        transfer_amount: transaction.transfer_amount ?? "",
        description: transaction.description,
        merchant: transaction.merchant ?? "",
        notes: transaction.notes ?? "",
        date: transaction.date,
      });
      setRateEdited(false);
      setAmountEdited(false);
      setTags(transaction.tags);
      setSplitMode(hasSplits);
      setSplitRows(
        hasSplits
          ? transaction.splits.map((split) => ({
              key: String(split.id),
              category_id: split.category_id ? String(split.category_id) : "",
              amount: split.amount,
              note: split.note ?? "",
            }))
          : [emptySplitRow(), emptySplitRow()]
      );
    } else {
      setForm({ ...EMPTY_FORM, account_id: accounts?.[0] ? String(accounts[0].id) : "" });
      setRateEdited(false);
      setAmountEdited(false);
      setTags([]);
      setSplitMode(false);
      setSplitRows([emptySplitRow(), emptySplitRow()]);
    }
    setError(null);
  }, [open, transaction, accounts]);

  const kindCategories = (categories ?? []).filter((category) =>
    form.type === "income" ? category.kind === "income" : category.kind === "expense"
  );
  // Subcategories are listed right under their parent (not scattered by
  // name) so the hierarchy set up on the Categories page reads the same way
  // here.
  const relevantCategories = buildHierarchicalCategories(kindCategories, language);

  const isSaving = createTransaction.isPending || updateTransaction.isPending;
  const selectedAccount = accounts?.find((account) => String(account.id) === form.account_id);
  const destinationAccount = accounts?.find((account) => String(account.id) === form.transfer_account_id);
  const accountCurrency = selectedAccount?.currency.toUpperCase();
  const destinationCurrency = destinationAccount?.currency.toUpperCase();
  const isCrossCurrencyTransfer = form.type === "transfer" && Boolean(
    accountCurrency && destinationCurrency && accountCurrency !== destinationCurrency
  );

  // The transaction's own currency defaults to the account's; the two only
  // come apart for a purchase actually made in another currency.
  const transactionCurrency = (form.currency || accountCurrency || "").toUpperCase();
  const isForeignCurrency = Boolean(
    accountCurrency && transactionCurrency && transactionCurrency !== accountCurrency
  );

  // The full curated ISO list, not just the currencies already in use: a
  // transaction's currency is independent of any account's, so someone whose
  // only account is a KZT one still has to be able to pick USD.
  const currencyOptions = useMemo(() => {
    const codes = new Set(CURRENCIES.map((option) => option.code));
    if (accountCurrency) codes.add(accountCurrency);
    if (transactionCurrency) codes.add(transactionCurrency);
    return Array.from(codes).sort();
  }, [accountCurrency, transactionCurrency]);

  const officialRate = useExchangeRate(form.date, accountCurrency);
  const transactionRate = useExchangeRate(form.date, isForeignCurrency ? transactionCurrency : undefined);
  // Rates are quoted against KZT, so a cross rate (e.g. EUR→USD) goes through
  // KZT: divide the two official rates. KZT itself is the identity.
  const transactionToKzt = transactionCurrency === "KZT" ? "1" : transactionRate.data?.rate_to_kzt ?? "";
  const accountToKzt = accountCurrency === "KZT" ? "1" : officialRate.data?.rate_to_kzt ?? "";
  const suggestedRate =
    isForeignCurrency && transactionToKzt && accountToKzt
      ? divideDecimal(transactionToKzt, accountToKzt, 6) ?? ""
      : "";

  const previewRate = form.exchange_rate_to_kzt || officialRate.data?.rate_to_kzt || (accountCurrency === "KZT" ? "1" : "");
  const kztPreview = form.amount && previewRate ? multiplyDecimal(form.amount, previewRate, 2) : null;
  const transferRate = isCrossCurrencyTransfer && form.amount && form.transfer_amount
    ? divideDecimal(form.transfer_amount, form.amount, 6)
    : null;

  // Fills the rate field from the official NBK rate as soon as it loads, and
  // keeps the account-side debit in step with it — but never overwrites a rate
  // or a debit the user typed themselves.
  useEffect(() => {
    if (!isForeignCurrency || rateEdited || !suggestedRate) return;
    setForm((prev) => ({
      ...prev,
      rate: suggestedRate,
      amount: amountEdited ? prev.amount : debitFor(prev.transaction_amount, suggestedRate),
    }));
  }, [suggestedRate, isForeignCurrency, rateEdited, amountEdited]);

  function updateSplitRow(key: string, patch: Partial<SplitRowState>) {
    setSplitRows((prev) => prev.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  }

  function addSplitRow() {
    setSplitRows((prev) => [...prev, emptySplitRow()]);
  }

  function removeSplitRow(key: string) {
    setSplitRows((prev) => (prev.length <= 2 ? prev : prev.filter((row) => row.key !== key)));
  }

  function handleAccountChange(accountId: string) {
    // Switching accounts resets the currency context: the transaction starts
    // out in the new account's currency, and the rate/debit fields go back to
    // being derived rather than user-entered.
    setForm((prev) => ({
      ...prev,
      account_id: accountId,
      currency: "",
      rate: "",
      transfer_account_id: prev.transfer_account_id === accountId ? "" : prev.transfer_account_id,
      transfer_amount: "",
      exchange_rate_to_kzt: "",
    }));
    setRateEdited(false);
    setAmountEdited(false);
  }

  function handleCurrencyChange(currency: string) {
    setForm((prev) => ({ ...prev, currency, rate: "" }));
    setRateEdited(false);
    setAmountEdited(false);
  }

  function handleTransactionAmountChange(value: string) {
    setForm((prev) => {
      const account = accounts?.find((item) => String(item.id) === prev.account_id);
      const accountCode = account?.currency.toUpperCase() ?? "";
      const code = (prev.currency || accountCode).toUpperCase();
      const foreign = Boolean(accountCode && code && code !== accountCode);
      // Same currency -> the two figures are the same number. Foreign -> the
      // debit follows the amount through the current rate.
      return {
        ...prev,
        transaction_amount: value,
        amount: foreign ? debitFor(value, prev.rate) : value,
      };
    });
  }

  function handleRateChange(value: string) {
    setRateEdited(true);
    setForm((prev) => ({ ...prev, rate: value, amount: debitFor(prev.transaction_amount, value) }));
  }

  function handleDebitChange(value: string) {
    setAmountEdited(true);
    setForm((prev) => {
      const derivedRate =
        prev.transaction_amount && Number(prev.transaction_amount) !== 0
          ? divideDecimal(value, prev.transaction_amount, 6) ?? prev.rate
          : prev.rate;
      return { ...prev, amount: value, rate: derivedRate };
    });
  }

  const isSplitEditingNow = form.type !== "transfer" && splitMode;
  const splitAllocatedCents = splitRows.reduce((sum, row) => sum + toCents(row.amount), 0);
  const splitRemainingCents = toCents(form.amount) - splitAllocatedCents;

  // The category select becomes the split's "base" category while
  // splitting — restricted to top-level categories — and each split row can
  // only pick that base itself or one of its direct children (see
  // routes/transactions.py's _build_splits: a split's categories always
  // share one parent).
  const topLevelCategories = relevantCategories.filter((category) => !category.indented);
  const baseChildCategories = kindCategories.filter((category) => category.parent_id === Number(form.category_id));
  const categorySelectOptions = splitMode ? topLevelCategories : relevantCategories;

  function toggleSplitMode() {
    setSplitMode((prev) => {
      const next = !prev;
      if (next) {
        const current = relevantCategories.find((category) => String(category.id) === form.category_id);
        if (current?.parent_id) {
          setForm((f) => ({ ...f, category_id: String(current.parent_id) }));
        }
        setSplitRows([emptySplitRow(), emptySplitRow()]);
      }
      return next;
    });
  }

  function handleBaseCategoryChange(value: string) {
    setForm((prev) => ({ ...prev, category_id: value }));
    if (splitMode) setSplitRows([emptySplitRow(), emptySplitRow()]);
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    if (!form.account_id) {
      setError(t("transactions.form.errorSelectAccount"));
      return;
    }
    if (form.type === "transfer" && !form.transfer_account_id) {
      setError(t("transactions.form.errorSelectDestination"));
      return;
    }
    if (form.type === "transfer" && form.transfer_account_id === form.account_id) {
      setError(t("transactions.form.errorSameAccount"));
      return;
    }

    // Undefined -> leave the transaction's existing splits untouched on
    // update, and create a normal single-category transaction. [] -> clears
    // splits that used to be there (the user turned split mode off, or
    // switched the transaction to a transfer, which can't carry splits).
    let splits: TransactionSplitInput[] | undefined;
    if (isSplitEditingNow) {
      if (!form.category_id) {
        setError(t("transactions.form.errorSplitNoBaseCategory"));
        return;
      }
      const filledRows = splitRows.filter((row) => row.category_id || row.amount);
      if (filledRows.length < 2) {
        setError(t("transactions.form.errorSplitMinRows"));
        return;
      }
      if (filledRows.some((row) => !row.category_id || !row.amount || Number(row.amount) <= 0)) {
        setError(t("transactions.form.errorSplitIncomplete"));
        return;
      }
      const allocatedCents = filledRows.reduce((sum, row) => sum + toCents(row.amount), 0);
      if (allocatedCents !== toCents(form.amount)) {
        setError(t("transactions.form.errorSplitMismatch"));
        return;
      }
      splits = filledRows.map((row) => ({
        category_id: Number(row.category_id),
        amount: row.amount,
        note: row.note || null,
      }));
    } else if (transaction && transaction.splits.length > 0) {
      splits = [];
    }

    // A same-currency operation has one number, not two — the backend rejects
    // a row whose transaction_amount disagrees with its account debit.
    const submittedAmount = isForeignCurrency ? form.amount : form.transaction_amount;

    const payload: TransactionInput = {
      type: form.type,
      account_id: Number(form.account_id),
      category_id:
        form.type === "transfer" || (splits && splits.length > 0)
          ? null
          : form.category_id
            ? Number(form.category_id)
            : null,
      transfer_account_id: form.type === "transfer" ? Number(form.transfer_account_id) : null,
      amount: submittedAmount,
      currency: isForeignCurrency ? transactionCurrency : null,
      transaction_amount: isForeignCurrency ? form.transaction_amount : null,
      exchange_rate_to_kzt: form.exchange_rate_to_kzt || null,
      exchange_rate_source: form.exchange_rate_to_kzt
        ? rateEdited
          ? "manual"
          : transaction?.exchange_rate_source ?? "manual"
        : null,
      transfer_amount:
        form.type === "transfer"
          ? isCrossCurrencyTransfer
            ? form.transfer_amount || null
            : submittedAmount
          : null,
      description: form.description,
      merchant: form.merchant || null,
      notes: form.notes || null,
      date: form.date,
      tag_ids: tags.map((tag) => tag.id),
      splits,
    };

    try {
      if (transaction) {
        await updateTransaction.mutateAsync({ id: transaction.id, input: payload });
      } else {
        await createTransaction.mutateAsync(payload);
      }
      onClose();
    } catch {
      setError(t("transactions.form.saveError"));
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={transaction ? t("transactions.form.editTitle") : t("transactions.form.newTitle")}
    >
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <Label htmlFor="type">{t("transactions.form.typeLabel")}</Label>
          <Select
            id="type"
            value={form.type}
            onChange={(event) => {
              const nextType = event.target.value as TransactionType;
              setForm((prev) => ({ ...prev, type: nextType, category_id: "" }));
              if (nextType === "transfer") setSplitMode(false);
            }}
          >
            <option value="expense">{t("transactions.form.typeExpense")}</option>
            <option value="income">{t("transactions.form.typeIncome")}</option>
            <option value="transfer">{t("transactions.form.typeTransfer")}</option>
          </Select>
        </div>

        <div>
          <div className="flex items-center justify-between gap-2">
            <Label htmlFor="account">{t("transactions.form.accountLabel")}</Label>
            <Link to="/accounts" onClick={onClose} className="mb-1 text-xs text-series-1 hover:underline">
              {t("transactions.form.createCurrencyAccount")}
            </Link>
          </div>
          <Select
            id="account"
            required
            value={form.account_id}
            onChange={(event) => handleAccountChange(event.target.value)}
          >
            <option value="" disabled>{t("transactions.form.selectAccount")}</option>
            {accounts?.map((account) => (
              <option key={account.id} value={account.id}>{account.name} · {account.currency.toUpperCase()}</option>
            ))}
          </Select>
        </div>

        {form.type === "transfer" && (
          <div>
            <Label htmlFor="transfer_account">{t("transactions.form.transferAccountLabel")}</Label>
            <Select
              id="transfer_account"
              required
              value={form.transfer_account_id}
              onChange={(event) => setForm((prev) => ({ ...prev, transfer_account_id: event.target.value, transfer_amount: "" }))}
            >
              <option value="" disabled>{t("transactions.form.selectAccount")}</option>
              {accounts?.filter((account) => String(account.id) !== form.account_id).map((account) => (
                <option key={account.id} value={account.id}>{account.name} · {account.currency.toUpperCase()}</option>
              ))}
            </Select>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label htmlFor="transaction_amount">
              {form.type === "transfer"
                ? t("transactions.form.sentAmountLabel", { currency: transactionCurrency || "—" })
                : t("transactions.form.transactionAmountLabel", { currency: transactionCurrency || "—" })}
            </Label>
            <Input
              id="transaction_amount"
              type="number"
              step="0.01"
              min="0.01"
              required
              value={form.transaction_amount}
              onChange={(event) => handleTransactionAmountChange(event.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="transaction_currency">{t("transactions.form.currencyLabel")}</Label>
            <Select
              id="transaction_currency"
              value={transactionCurrency}
              onChange={(event) => handleCurrencyChange(event.target.value)}
            >
              {currencyOptions.map((code) => (
                <option key={code} value={code}>{code}</option>
              ))}
            </Select>
          </div>
        </div>

        <div>
          <Label htmlFor="date">{t("transactions.form.dateLabel")}</Label>
          <Input
            id="date"
            type="date"
            required
            value={form.date}
            onChange={(event) => {
              setForm((prev) => ({ ...prev, date: event.target.value, exchange_rate_to_kzt: rateEdited ? prev.exchange_rate_to_kzt : "" }));
            }}
          />
        </div>

        {isForeignCurrency && (
          <div className="rounded-lg border border-border bg-surface-1 p-3">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <Label htmlFor="rate">
                  {t("transactions.form.rateToAccountLabel", {
                    currency: transactionCurrency,
                    accountCurrency: accountCurrency ?? "—",
                  })}
                </Label>
                <Input
                  id="rate"
                  type="number"
                  step="0.0000000001"
                  min="0"
                  placeholder={transactionRate.isLoading ? t("common.loading") : t("transactions.form.ratePlaceholder")}
                  value={form.rate}
                  onChange={(event) => handleRateChange(event.target.value)}
                />
              </div>
              <div>
                <Label htmlFor="amount">
                  {t("transactions.form.debitedAmountLabel", { currency: accountCurrency ?? "—" })}
                </Label>
                <Input
                  id="amount"
                  type="number"
                  step="0.01"
                  min="0.01"
                  required
                  value={form.amount}
                  onChange={(event) => handleDebitChange(event.target.value)}
                />
              </div>
            </div>
            {!form.rate && transactionRate.data && (
              <p className="mt-2 text-xs text-text-muted">
                {t("transactions.form.rateInfo", {
                  rate: suggestedRate || transactionRate.data.rate_to_kzt,
                  currency: transactionCurrency,
                  accountCurrency: accountCurrency ?? "",
                  date: transactionRate.data.effective_date,
                })}
              </p>
            )}
            {!form.rate && transactionRate.isError && (
              <p className="mt-2 text-xs text-warning">{t("transactions.form.nbkRateUnavailable")}</p>
            )}
            {form.rate && rateEdited && <p className="mt-2 text-xs text-text-muted">{t("transactions.form.manualRateInfo")}</p>}
          </div>
        )}

        {isCrossCurrencyTransfer && (
          <div className="rounded-lg border border-border bg-surface-1 p-3">
            <Label htmlFor="transfer_amount">
              {t("transactions.form.receivedAmountLabel", { currency: destinationCurrency ?? "—" })}
            </Label>
            <div className="relative">
              <Input
                id="transfer_amount"
                type="number"
                step="0.01"
                min="0.01"
                required
                className="pr-14"
                value={form.transfer_amount}
                onChange={(event) => setForm((prev) => ({ ...prev, transfer_amount: event.target.value }))}
              />
              {destinationCurrency && <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs font-medium text-text-muted">{destinationCurrency}</span>}
            </div>
            {transferRate && <p className="mt-1.5 text-xs text-text-muted">{t("transactions.form.effectiveTransferRate", { rate: transferRate, source: accountCurrency ?? "", destination: destinationCurrency ?? "" })}</p>}
          </div>
        )}

        {accountCurrency && accountCurrency !== "KZT" && (
          <div className="rounded-lg border border-border p-3">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <Label htmlFor="exchange_rate_to_kzt">{t("transactions.form.exchangeRateCurrencyLabel", { currency: accountCurrency })}</Label>
                <Input
                  id="exchange_rate_to_kzt"
                  type="number"
                  step="0.0000000001"
                  min="0"
                  placeholder={officialRate.isLoading ? t("common.loading") : t("transactions.form.exchangeRatePlaceholder")}
                  value={form.exchange_rate_to_kzt}
                  onChange={(event) => {
                    setRateEdited(true);
                    setForm((prev) => ({ ...prev, exchange_rate_to_kzt: event.target.value }));
                  }}
                />
              </div>
              <div className="rounded-lg bg-surface-2 px-3 py-2 text-sm">
                <span className="text-xs text-text-muted">{t("transactions.form.kztEquivalent")}</span>
                <strong className="block text-text-primary">{kztPreview ? `${kztPreview} KZT` : "—"}</strong>
              </div>
            </div>
            {!form.exchange_rate_to_kzt && officialRate.data && (
              <p className="mt-2 text-xs text-text-muted">{t("transactions.form.nbkRateInfo", { rate: officialRate.data.rate_to_kzt, currency: accountCurrency, date: officialRate.data.effective_date })}</p>
            )}
            {!form.exchange_rate_to_kzt && officialRate.isError && (
              <p className="mt-2 text-xs text-warning">{t("transactions.form.nbkRateUnavailable")}</p>
            )}
            {form.exchange_rate_to_kzt && <p className="mt-2 text-xs text-text-muted">{t("transactions.form.manualRateInfo")}</p>}
          </div>
        )}

        <div>
          <Label htmlFor="description">{t("transactions.form.descriptionLabel")}</Label>
          <Input
            id="description"
            required
            placeholder={t("transactions.form.descriptionPlaceholder")}
            value={form.description}
            onChange={(event) => setForm((prev) => ({ ...prev, description: event.target.value }))}
          />
        </div>

        {form.type !== "transfer" && (
          <div>
            <div className="flex items-center justify-between">
              <Label htmlFor="category">{t("transactions.form.categoryLabel")}</Label>
              <button
                type="button"
                className="mb-1 text-xs text-series-1 hover:underline"
                onClick={toggleSplitMode}
              >
                {splitMode ? t("transactions.form.splitToggleOff") : t("transactions.form.splitToggle")}
              </button>
            </div>

            <Select
              id="category"
              value={form.category_id}
              onChange={(event) => handleBaseCategoryChange(event.target.value)}
            >
              <option value="">{t("transactions.form.noCategory")}</option>
              {categorySelectOptions.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.indented ? `    ↳ ` : ""}
                  {translateCategoryName(category.name)}
                </option>
              ))}
            </Select>

            {splitMode && (
              <div className="mt-2 space-y-2">
                {!form.category_id ? (
                  <p className="text-xs text-text-muted">{t("transactions.form.splitHint")}</p>
                ) : baseChildCategories.length === 0 ? (
                  <p className="text-xs text-text-muted">{t("transactions.form.splitNoChildren")}</p>
                ) : (
                  <p className="text-xs text-text-muted">{t("transactions.form.splitHint")}</p>
                )}
                {splitRows.map((row) => (
                  <div key={row.key} className="space-y-1.5 rounded-lg border border-border bg-surface-1 p-2">
                    <div className="flex flex-col gap-1.5 sm:flex-row sm:items-center sm:gap-2">
                      <Select
                        aria-label={t("transactions.form.splitCategoryPlaceholder")}
                        className="sm:flex-1"
                        value={row.category_id}
                        disabled={!form.category_id}
                        onChange={(event) => updateSplitRow(row.key, { category_id: event.target.value })}
                      >
                        <option value="" disabled>
                          {t("transactions.form.splitCategoryPlaceholder")}
                        </option>
                        {form.category_id && (
                          <option value={form.category_id}>{t("transactions.form.splitDirectOption")}</option>
                        )}
                        {baseChildCategories.map((category) => (
                          <option key={category.id} value={category.id}>
                            {translateCategoryName(category.name)}
                          </option>
                        ))}
                      </Select>
                      <div className="flex items-center gap-1.5">
                        <Input
                          type="number"
                          step="0.01"
                          min="0.01"
                          className="w-24"
                          placeholder={t("transactions.form.amountLabel")}
                          value={row.amount}
                          onChange={(event) => updateSplitRow(row.key, { amount: event.target.value })}
                        />
                        <button
                          type="button"
                          aria-label={t("transactions.form.splitRemoveRow")}
                          onClick={() => removeSplitRow(row.key)}
                          disabled={splitRows.length <= 2}
                          className="shrink-0 rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-danger disabled:opacity-30"
                        >
                          <X size={15} />
                        </button>
                      </div>
                    </div>
                    <Input
                      className="text-xs"
                      placeholder={t("transactions.form.splitNotePlaceholder")}
                      value={row.note}
                      onChange={(event) => updateSplitRow(row.key, { note: event.target.value })}
                    />
                  </div>
                ))}

                <div className="flex items-center justify-between gap-2">
                  <button
                    type="button"
                    onClick={addSplitRow}
                    className="flex items-center gap-1 rounded-md py-1 text-xs text-series-1 hover:underline"
                  >
                    <Plus size={14} />
                    {t("transactions.form.splitAddRow")}
                  </button>
                  <p className={`text-xs ${splitRemainingCents === 0 ? "text-success" : "text-text-muted"}`}>
                    {splitRemainingCents > 0
                      ? t("transactions.form.splitRemainingLabel", {
                          amount: formatCurrency(splitRemainingCents / 100, accountCurrency),
                        })
                      : splitRemainingCents < 0
                        ? t("transactions.form.splitOverAllocatedLabel", {
                            amount: formatCurrency(Math.abs(splitRemainingCents) / 100, accountCurrency),
                          })
                        : t("transactions.form.splitFullyAllocatedLabel")}
                  </p>
                </div>
              </div>
            )}
          </div>
        )}

        <div>
          <Label htmlFor="merchant">{t("transactions.form.merchantLabel")}</Label>
          <Input
            id="merchant"
            value={form.merchant}
            onChange={(event) => setForm((prev) => ({ ...prev, merchant: event.target.value }))}
          />
        </div>

        <div>
          <Label htmlFor="notes">{t("transactions.form.notesLabel")}</Label>
          {/* Matches the server's max_length on notes — without it an overlong
              note only fails on save, as an untranslated 422. */}
          <Input
            id="notes"
            maxLength={2000}
            value={form.notes}
            onChange={(event) => setForm((prev) => ({ ...prev, notes: event.target.value }))}
          />
        </div>

        <div>
          <Label htmlFor="transaction-tags">{t("transactions.form.tagsLabel")}</Label>
          <TagInput value={tags} onChange={setTags} />
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
