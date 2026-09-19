import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, Upload } from "lucide-react";
import { commitStatement, previewStatement } from "@/api/statementImports";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input, Label, Select } from "@/components/ui/Input";
import { useAccounts } from "@/hooks/useAccounts";
import { useCategories } from "@/hooks/useCategories";
import { translateCategoryName } from "@/lib/categoryLabels";
import { CURRENCIES } from "@/lib/currency";
import { useTranslation } from "@/lib/i18n";
import type { StatementCommitResult, StatementPreview, StatementRow, TransactionType } from "@/types";

export function StatementImportPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
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

  const importable = useMemo(() => rows.filter((row) => row.importable), [rows]);
  const currencies = useMemo(
    () => [...new Set(importable.map((row) => row.currency.toUpperCase()))].sort(),
    [importable]
  );
  // The curated ISO list plus whatever the document actually used, so a row's
  // currency can be corrected to something no account holds yet.
  const currencyOptions = useMemo(() => {
    const codes = new Set(CURRENCIES.map((option) => option.code));
    for (const row of rows) codes.add(row.currency.toUpperCase());
    return [...codes].sort();
  }, [rows]);

  function updateRow(index: number, patch: Partial<StatementRow>) {
    setRows((prev) => prev.map((row, current) => (current === index ? { ...row, ...patch } : row)));
  }

  async function choose(file?: File) {
    if (!file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const data = await previewStatement(file);
      setPreview(data);
      setRows(data.rows);
      const defaults: Record<string, number> = {};
      const currenciesInFile = new Set(
        data.rows.filter((row) => row.importable).map((row) => row.currency.toUpperCase())
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
    if (!preview || currencies.some((currency) => !mapping[currency])) return;
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

  const skipped = rows.length - importable.length;

  return (
    <div className="space-y-5">
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
            <input
              className="hidden"
              type="file"
              accept=".xlsx"
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

              {preview.warnings.map((warning) => (
                <p key={warning} className="text-xs text-warning">
                  {warning}
                </p>
              ))}

              <div className="max-h-[520px] overflow-auto rounded-lg border border-border">
                <table className="w-full min-w-[900px] text-sm">
                  <thead className="sticky top-0 bg-surface-2 text-left text-xs text-text-muted">
                    <tr>
                      <th className="p-2">{t("transactions.form.dateLabel")}</th>
                      <th className="p-2">{t("statementImport.operation")}</th>
                      <th className="p-2">{t("transactions.form.amountLabel")}</th>
                      <th className="p-2">{t("transactions.import.currencyColumnLabel")}</th>
                      <th className="p-2">{t("statementImport.type")}</th>
                      <th className="p-2">{t("statementImport.category")}</th>
                      <th className="p-2">{t("statementImport.status")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, index) => (
                      <tr key={index} className="border-t border-border align-top">
                        <td className="p-2">
                          <Input
                            type="date"
                            value={row.date}
                            disabled={!row.importable}
                            onChange={(event) => updateRow(index, { date: event.target.value })}
                          />
                        </td>
                        <td className="p-2">
                          <Input
                            value={row.description}
                            disabled={!row.importable}
                            onChange={(event) => updateRow(index, { description: event.target.value })}
                          />
                          {row.security_symbol && (
                            <span className="mt-1 block text-xs text-text-muted">{row.security_symbol}</span>
                          )}
                        </td>
                        <td className="p-2">
                          <Input
                            type="number"
                            step="0.01"
                            min="0.01"
                            className="w-28"
                            value={row.amount}
                            disabled={!row.importable}
                            onChange={(event) => updateRow(index, { amount: event.target.value })}
                          />
                        </td>
                        <td className="p-2">
                          <Select
                            value={row.currency.toUpperCase()}
                            disabled={!row.importable}
                            onChange={(event) => updateRow(index, { currency: event.target.value })}
                          >
                            {currencyOptions.map((code) => (
                              <option key={code} value={code}>
                                {code}
                              </option>
                            ))}
                          </Select>
                        </td>
                        <td className="p-2">
                          <Select
                            value={row.type}
                            disabled={!row.importable}
                            onChange={(event) =>
                              updateRow(index, { type: event.target.value as TransactionType, category_id: null })
                            }
                          >
                            <option value="income">{t("transactions.form.typeIncome")}</option>
                            <option value="expense">{t("transactions.form.typeExpense")}</option>
                          </Select>
                        </td>
                        <td className="p-2">
                          <Select
                            value={row.category_id ?? ""}
                            disabled={!row.importable}
                            onChange={(event) =>
                              updateRow(index, {
                                category_id: event.target.value ? Number(event.target.value) : null,
                              })
                            }
                          >
                            <option value="">{t("transactions.form.noCategory")}</option>
                            {categories
                              .filter((category) => category.kind === (row.type === "income" ? "income" : "expense"))
                              .map((category) => (
                                <option key={category.id} value={category.id}>
                                  {translateCategoryName(category.name)}
                                </option>
                              ))}
                          </Select>
                        </td>
                        <td className={`p-2 text-xs ${row.importable ? "text-success" : "text-warning"}`}>
                          {row.importable ? t("statementImport.ready") : row.warning}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex justify-end gap-2">
                <Button variant="ghost" onClick={() => navigate("/transactions")}>
                  {t("common.cancel")}
                </Button>
                <Button onClick={save} disabled={busy || currencies.some((currency) => !mapping[currency])}>
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
