import type { TranslationKey } from "@/lib/i18n";
import type { TransactionType } from "@/types";

// One place that maps a transaction type to its label — the rules page and its
// form both need it, and a bare string key in each of them would drift.
export const TRANSACTION_TYPE_KEYS: Record<TransactionType, TranslationKey> = {
  income: "transactions.form.typeIncome",
  expense: "transactions.form.typeExpense",
  transfer: "transactions.form.typeTransfer",
};
