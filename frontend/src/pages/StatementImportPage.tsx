import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft, Upload } from "lucide-react";
import { commitStatement, previewStatement } from "@/api/statementImports";
import { StatementReview } from "@/components/statements/StatementReview";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { ContextualHelp } from "@/components/help/ContextualHelp";
import { Label, Select } from "@/components/ui/Input";
import { useAccounts } from "@/hooks/useAccounts";
import { useCategories } from "@/hooks/useCategories";
import { useLocalStatementDocument } from "@/hooks/useLocalStatementDocument";
import { CURRENCIES } from "@/lib/currency";
import { IMPORT_OPTIONS } from "@/lib/importOptions";
import { useTranslation } from "@/lib/i18n";
import type { StatementCommitResult, StatementPreview, StatementRow } from "@/types";

export function StatementImportPage() {
  const { t, language } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { data: accounts = [] } = useAccounts();
  const { data: categories = [] } = useCategories();
  const [preview, setPreview] = useState<StatementPreview | null>(null);
  // The editable copy of what the parser read. Every field here can be
  // corrected, and only this list is posted — a row the parser marked not
  // importable stays visible with its reason but is never written.
  const [rows, setRows] = useState<StatementRow[]>([]);
  const [mapping, setMapping] = useState<Record<string, number>>({});
  const [result, setResult] = useState<StatementCommitResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { document, selectDocument, clearDocument } = useLocalStatementDocument();
  const selectedBank = IMPORT_OPTIONS.find((option) => option.id === searchParams.get("bank"));

  const importable = useMemo(() => rows.filter((row) => row.importable), [rows]);
  const currencies = useMemo(
    () => [...new Set(importable.map((row) => row.account_currency.toUpperCase()))].sort(),
    [importable]
  );
  // The curated ISO list plus whatever the document actually used, so a row's
  // currency can be corrected to something no account holds yet.
  const currencyOptions = useMemo(() => {
    const codes = new Set(CURRENCIES.map((option) => option.code));
    for (const row of rows) {
      codes.add(row.account_currency.toUpperCase());
      codes.add(row.currency.toUpperCase());
    }
    return [...codes].sort();
  }, [rows]);

  function updateRow(index: number, patch: Partial<StatementRow>) {
    setRows((prev) => prev.map((row, current) => (current === index ? { ...row, ...patch } : row)));
  }

  function updateAccountAmount(index: number, amount: string) {
    const row = rows[index];
    updateRow(index, {
      amount,
      ...(row.account_currency === row.currency && row.transaction_amount === row.amount
        ? { transaction_amount: amount }
        : {}),
    });
  }

  async function choose(file?: File) {
    if (!file) return;
    selectDocument(file);
    setPreview(null);
    setRows([]);
    setMapping({});
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const data = await previewStatement(file);
      setPreview(data);
      setRows(data.rows);
      const defaults: Record<string, number> = {};
      const currenciesInFile = new Set(
        data.rows.filter((row) => row.importable).map((row) => row.account_currency.toUpperCase())
      );
      for (const currency of currenciesInFile) {
        const account = accounts.find((item) => item.currency.toUpperCase() === currency);
        if (account) defaults[currency] = account.id;
      }
      setMapping(defaults);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!preview || importable.length === 0 || currencies.some((currency) => !mapping[currency])) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await commitStatement(preview.provider, rows, mapping));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  function cancel() {
    clearDocument();
    navigate("/transactions/import");
  }

  const skipped = rows.length - importable.length;

  return (
    <div className="space-y-5">
      <ContextualHelp topicId="statementImport" />
      <Link
        to="/transactions/import"
        className="inline-flex items-center gap-1 text-sm text-text-muted hover:text-text-primary"
      >
        <ArrowLeft size={16} />
        {t("common.back")}
      </Link>
      <Card>
        <CardHeader>
          <CardTitle>{t("statementImport.title")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <label className="flex cursor-pointer flex-col items-center gap-2 rounded-xl border border-dashed border-border p-8 text-center hover:bg-surface-2">
            <Upload size={24} />
            <span className="text-sm font-medium">{busy ? t("common.loading") : t("statementImport.choose")}</span>
            <span className="text-xs text-text-muted">{t("statementImport.formats")}</span>
            {selectedBank && (
              <span className="text-xs text-text-muted">
                {t("statementImport.selectedBank", { bank: t(selectedBank.titleKey) })}
              </span>
            )}
            <input
              className="hidden"
              type="file"
              accept={selectedBank?.accept ?? ".xlsx,.pdf,application/pdf"}
              disabled={busy}
              onChange={(event) => choose(event.target.files?.[0])}
            />
          </label>

          {error && <p className="text-sm text-danger">{error}</p>}

          {preview && (
            <>
              <p className="text-sm text-text-secondary">
                {t("statementImport.recognized", { provider: preview.provider_label, count: rows.length })}
              </p>
              <p className="text-xs text-text-muted">{t("statementImport.editedHint")}</p>
              {preview.requires_row_confirmation && (
                <p className="text-xs text-warning">{t("statementImport.confirmEachOcrRow")}</p>
              )}
              {skipped > 0 && (
                <p className="text-xs text-warning">{t("statementImport.skipped", { count: skipped })}</p>
              )}

              {currencies.length > 0 && (
                <div className="grid gap-3 sm:grid-cols-2">
                  {currencies.map((currency) => (
                    <div key={currency}>
                      <Label>{t("statementImport.accountFor", { currency })}</Label>
                      <Select
                        value={mapping[currency] ?? ""}
                        onChange={(event) =>
                          setMapping((prev) => ({ ...prev, [currency]: Number(event.target.value) }))
                        }
                      >
                        <option value="">{t("transactions.form.selectAccount")}</option>
                        {accounts
                          .filter((account) => account.currency.toUpperCase() === currency)
                          .map((account) => (
                            <option key={account.id} value={account.id}>
                              {account.name} · {account.currency}
                            </option>
                          ))}
                      </Select>
                    </div>
                  ))}
                </div>
              )}

              <StatementReview
                categories={categories}
                currencyOptions={currencyOptions}
                document={document}
                language={language}
                preview={preview}
                rows={rows}
                t={t}
                updateAccountAmount={updateAccountAmount}
                updateRow={updateRow}
              />

              <div className="flex flex-wrap justify-end gap-2">
                <Button className="min-h-11" variant="ghost" onClick={cancel}>
                  {t("common.cancel")}
                </Button>
                <Button
                  className="min-h-11"
                  onClick={save}
                  disabled={busy || importable.length === 0 || currencies.some((currency) => !mapping[currency])}
                >
                  {t("statementImport.import")}
                </Button>
              </div>
            </>
          )}

          {result && (
            <p className="rounded-lg bg-surface-2 p-3 text-sm text-success">
              {t("statementImport.done", {
                created: result.created,
                duplicates: result.duplicates,
                ignored: result.ignored,
              })}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
