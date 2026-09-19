import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, Upload } from "lucide-react";
import { commitStatement, previewStatement } from "@/api/statementImports";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Label, Select } from "@/components/ui/Input";
import { useAccounts } from "@/hooks/useAccounts";
import { formatCurrency } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import type { StatementCommitResult, StatementPreview } from "@/types";

export function StatementImportPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { data: accounts = [] } = useAccounts();
  const [preview, setPreview] = useState<StatementPreview | null>(null);
  const [mapping, setMapping] = useState<Record<string, number>>({});
  const [result, setResult] = useState<StatementCommitResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const currencies = useMemo(() => [...new Set(preview?.rows.filter(r => r.importable).map(r => r.currency) ?? [])], [preview]);

  async function choose(file?: File) {
    if (!file) return;
    setBusy(true); setError(null); setResult(null);
    try {
      const data = await previewStatement(file);
      setPreview(data);
      const defaults: Record<string, number> = {};
      for (const currency of [...new Set(data.rows.filter(r => r.importable).map(r => r.currency))]) {
        const account = accounts.find(a => a.currency.toUpperCase() === currency);
        if (account) defaults[currency] = account.id;
      }
      setMapping(defaults);
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  }

  async function save() {
    if (!preview || currencies.some(currency => !mapping[currency])) return;
    setBusy(true); setError(null);
    try { setResult(await commitStatement(preview, mapping)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  }

  return <div className="space-y-5">
    <Link to="/transactions/import" className="inline-flex items-center gap-1 text-sm text-text-muted hover:text-text-primary"><ArrowLeft size={16}/>{t("common.back")}</Link>
    <Card><CardHeader><CardTitle>{t("statementImport.title")}</CardTitle></CardHeader><CardContent className="space-y-4">
      <label className="flex cursor-pointer flex-col items-center gap-2 rounded-xl border border-dashed border-border p-8 text-center hover:bg-surface-2">
        <Upload size={24}/><span className="text-sm font-medium">{busy ? t("common.loading") : t("statementImport.choose")}</span>
        <span className="text-xs text-text-muted">{t("statementImport.formats")}</span>
        <input className="hidden" type="file" accept=".xlsx,.pdf" disabled={busy} onChange={e => choose(e.target.files?.[0])}/>
      </label>
      {error && <p className="text-sm text-danger">{error}</p>}
      {preview && <>
        <p className="text-sm text-text-secondary">{t("statementImport.recognized", { provider: preview.provider, count: preview.rows.length })}</p>
        <div className="grid gap-3 sm:grid-cols-2">{currencies.map(currency => <div key={currency}><Label>{t("statementImport.accountFor", { currency })}</Label><Select value={mapping[currency] ?? ""} onChange={e => setMapping(prev => ({...prev,[currency]:Number(e.target.value)}))}><option value="">{t("transactions.form.selectAccount")}</option>{accounts.filter(a => a.currency.toUpperCase() === currency).map(a => <option key={a.id} value={a.id}>{a.name} · {a.currency}</option>)}</Select></div>)}</div>
        {preview.warnings.map((warning, index) => <p key={index} className="text-xs text-warning">{warning}</p>)}
        <div className="max-h-[480px] overflow-auto rounded-lg border border-border"><table className="w-full min-w-[720px] text-sm"><thead className="sticky top-0 bg-surface-2 text-left text-xs text-text-muted"><tr><th className="p-2">{t("transactions.form.dateLabel")}</th><th>{t("statementImport.operation")}</th><th>{t("transactions.form.amountLabel")}</th><th>{t("statementImport.security")}</th><th>{t("statementImport.status")}</th></tr></thead><tbody>{preview.rows.map(row => <tr key={row.external_id} className="border-t border-border"><td className="p-2">{row.date}</td><td><div>{row.description}</div><div className="max-w-md truncate text-xs text-text-muted">{row.details}</div></td><td>{formatCurrency(row.amount,row.currency)}</td><td>{row.security_symbol ?? "—"}</td><td className={row.importable ? "text-success" : "text-warning"}>{row.importable ? t("statementImport.ready") : row.warning}</td></tr>)}</tbody></table></div>
        <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => navigate("/transactions")}>{t("common.cancel")}</Button><Button onClick={save} disabled={busy || currencies.some(c => !mapping[c])}>{t("statementImport.import")}</Button></div>
      </>}
      {result && <p className="rounded-lg bg-surface-2 p-3 text-sm text-success">{t("statementImport.done", result)}</p>}
    </CardContent></Card>
  </div>;
}
