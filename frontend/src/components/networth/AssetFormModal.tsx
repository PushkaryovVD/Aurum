import { useEffect, useState } from "react";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input, Label, Select } from "@/components/ui/Input";
import { useAddAssetValuation, useCreateAsset, useUpdateAsset } from "@/hooks/useAssets";
import { useTranslation, type TranslationKey } from "@/lib/i18n";
import type { Asset, AssetClass, AssetValuationMode, CapitalRole, RiskLevel } from "@/types";

interface AssetFormModalProps {
  open: boolean;
  onClose: () => void;
  asset?: Asset | null;
}

const ASSET_CLASSES: AssetClass[] = ["investments", "crypto", "real_estate", "vehicles", "precious_metals", "other"];
const CAPITAL_ROLES: CapitalRole[] = ["income", "neutral", "drain"];
const RISK_LEVELS: RiskLevel[] = ["low", "medium", "high"];
const VALUATION_MODES: AssetValuationMode[] = ["manual_only", "straight_line", "annual_percentage"];

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

const EMPTY_FORM = {
  name: "",
  asset_class: "investments" as AssetClass,
  value: "",
  as_of_date: todayIso(),
  notes: "",
  capital_role: "neutral" as CapitalRole,
  monthly_cash_flow: "",
  risk_level: "medium" as RiskLevel,
  acquisition_date: "",
  acquisition_cost: "",
  residual_value: "",
  valuation_mode: "manual_only" as AssetValuationMode,
  useful_life_years: "",
  annual_depreciation_rate: "",
};

type AssetFormState = typeof EMPTY_FORM;
const UNSIGNED_DECIMAL = /^\d+(?:\.\d{1,6})?$/;
const SIGNED_DECIMAL = /^-?\d+(?:\.\d{1,6})?$/;

export function validateAssetForm(form: AssetFormState): TranslationKey | null {
  if (!UNSIGNED_DECIMAL.test(form.value)) return "netWorth.form.validation.money";
  if (form.monthly_cash_flow && !SIGNED_DECIMAL.test(form.monthly_cash_flow)) return "netWorth.form.validation.money";
  if (form.valuation_mode === "manual_only") return null;
  if (!form.acquisition_date) return "netWorth.form.validation.depreciationRequired";
  if (!UNSIGNED_DECIMAL.test(form.acquisition_cost)) return "netWorth.form.validation.money";
  if (form.residual_value && !UNSIGNED_DECIMAL.test(form.residual_value)) return "netWorth.form.validation.money";
  if (Number(form.residual_value || "0") > Number(form.acquisition_cost)) return "netWorth.form.validation.residualValue";
  if (form.valuation_mode === "straight_line") {
    const years = Number(form.useful_life_years);
    if (!Number.isInteger(years) || years < 1 || years > 100) return "netWorth.form.validation.usefulLife";
  } else {
    if (!UNSIGNED_DECIMAL.test(form.annual_depreciation_rate)) return "netWorth.form.validation.annualRate";
    const rate = Number(form.annual_depreciation_rate);
    if (rate <= 0 || rate >= 100) return "netWorth.form.validation.annualRate";
  }
  return null;
}

export function AssetFormModal({ open, onClose, asset }: AssetFormModalProps) {
  const { t } = useTranslation();
  const createAsset = useCreateAsset();
  const updateAsset = useUpdateAsset();
  const addValuation = useAddAssetValuation();

  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    if (asset) {
      setForm({
        name: asset.name,
        asset_class: asset.asset_class,
        value: asset.current_value,
        as_of_date: todayIso(),
        notes: asset.notes ?? "",
        capital_role: asset.capital_role,
        monthly_cash_flow: asset.monthly_cash_flow ?? "",
        risk_level: asset.risk_level,
        acquisition_date: asset.acquisition_date ?? "",
        acquisition_cost: asset.acquisition_cost ?? "",
        residual_value: asset.residual_value ?? "",
        valuation_mode: asset.valuation_mode,
        useful_life_years: asset.useful_life_years?.toString() ?? "",
        annual_depreciation_rate: asset.annual_depreciation_rate ?? "",
      });
    } else {
      setForm(EMPTY_FORM);
    }
    setError(null);
  }, [open, asset]);

  const isSaving = createAsset.isPending || updateAsset.isPending || addValuation.isPending;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    const validationError = validateAssetForm(form);
    if (validationError) {
      setError(t(validationError));
      return;
    }

    try {
      if (asset) {
        await updateAsset.mutateAsync({
          id: asset.id,
          input: {
            name: form.name,
            asset_class: form.asset_class,
            notes: form.notes || null,
            capital_role: form.capital_role,
            monthly_cash_flow: form.monthly_cash_flow || null,
            risk_level: form.risk_level,
            acquisition_date: form.acquisition_date || null,
            acquisition_cost: form.acquisition_cost || null,
            residual_value: form.residual_value || null,
            valuation_mode: form.valuation_mode,
            useful_life_years: form.useful_life_years ? Number(form.useful_life_years) : null,
            annual_depreciation_rate: form.annual_depreciation_rate || null,
          },
        });
        if (form.value !== asset.current_value) {
          await addValuation.mutateAsync({ id: asset.id, input: { value: form.value, as_of_date: form.as_of_date } });
        }
      } else {
        await createAsset.mutateAsync({
          name: form.name,
          asset_class: form.asset_class,
          value: form.value,
          as_of_date: form.as_of_date,
          notes: form.notes || null,
          capital_role: form.capital_role,
          monthly_cash_flow: form.monthly_cash_flow || null,
          risk_level: form.risk_level,
          acquisition_date: form.acquisition_date || null,
          acquisition_cost: form.acquisition_cost || null,
          residual_value: form.residual_value || null,
          valuation_mode: form.valuation_mode,
          useful_life_years: form.useful_life_years ? Number(form.useful_life_years) : null,
          annual_depreciation_rate: form.annual_depreciation_rate || null,
        });
      }
      onClose();
    } catch {
      setError(t("netWorth.form.saveError"));
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={asset ? t("netWorth.form.editTitle") : t("netWorth.form.newTitle")}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <Label htmlFor="asset-name">{t("netWorth.form.nameLabel")}</Label>
          <Input
            id="asset-name"
            required
            placeholder={t("netWorth.form.namePlaceholder")}
            value={form.name}
            onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
          />
        </div>

        <div>
          <Label htmlFor="asset-class">{t("netWorth.form.classLabel")}</Label>
          <Select
            id="asset-class"
            value={form.asset_class}
            onChange={(event) => setForm((prev) => ({ ...prev, asset_class: event.target.value as AssetClass }))}
          >
            {ASSET_CLASSES.map((value) => (
              <option key={value} value={value}>
                {t(`netWorth.assetClass.${value}` as TranslationKey)}
              </option>
            ))}
          </Select>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <Label htmlFor="asset-value">
              {asset ? t("netWorth.form.currentValueLabel") : t("netWorth.form.valueLabel")}
            </Label>
            <Input
              id="asset-value"
              type="text"
              inputMode="decimal"
              required
              value={form.value}
              onChange={(event) => setForm((prev) => ({ ...prev, value: event.target.value }))}
            />
          </div>
          <div>
            <Label htmlFor="asset-date">{t("netWorth.form.dateLabel")}</Label>
            <Input
              id="asset-date"
              type="date"
              required
              value={form.as_of_date}
              onChange={(event) => setForm((prev) => ({ ...prev, as_of_date: event.target.value }))}
            />
          </div>
        </div>

        <div>
          <Label htmlFor="asset-valuation-mode">{t("netWorth.form.valuationModeLabel")}</Label>
          <Select id="asset-valuation-mode" value={form.valuation_mode} onChange={(event) => setForm((prev) => ({ ...prev, valuation_mode: event.target.value as AssetValuationMode }))}>
            {VALUATION_MODES.map((value) => <option key={value} value={value}>{t(`netWorth.form.valuationMode.${value}` as TranslationKey)}</option>)}
          </Select>
        </div>

        {form.valuation_mode !== "manual_only" && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <Label htmlFor="asset-acquisition-date">{t("netWorth.form.acquisitionDateLabel")}</Label>
              <Input id="asset-acquisition-date" type="date" required value={form.acquisition_date} onChange={(event) => setForm((prev) => ({ ...prev, acquisition_date: event.target.value }))} />
            </div>
            <div>
              <Label htmlFor="asset-acquisition-cost">{t("netWorth.form.acquisitionCostLabel")}</Label>
              <Input id="asset-acquisition-cost" type="text" inputMode="decimal" required value={form.acquisition_cost} onChange={(event) => setForm((prev) => ({ ...prev, acquisition_cost: event.target.value }))} />
            </div>
            <div>
              <Label htmlFor="asset-residual-value">{t("netWorth.form.residualValueLabel")}</Label>
              <Input id="asset-residual-value" type="text" inputMode="decimal" value={form.residual_value} onChange={(event) => setForm((prev) => ({ ...prev, residual_value: event.target.value }))} />
            </div>
            {form.valuation_mode === "straight_line" ? (
              <div>
                <Label htmlFor="asset-useful-life">{t("netWorth.form.usefulLifeLabel")}</Label>
                <Input id="asset-useful-life" type="number" min="1" max="100" required value={form.useful_life_years} onChange={(event) => setForm((prev) => ({ ...prev, useful_life_years: event.target.value }))} />
              </div>
            ) : (
              <div>
                <Label htmlFor="asset-annual-rate">{t("netWorth.form.annualRateLabel")}</Label>
                <Input id="asset-annual-rate" type="text" inputMode="decimal" required value={form.annual_depreciation_rate} onChange={(event) => setForm((prev) => ({ ...prev, annual_depreciation_rate: event.target.value }))} />
              </div>
            )}
          </div>
        )}

        <div>
          <Label htmlFor="asset-role">{t("netWorth.form.roleLabel")}</Label>
          <Select
            id="asset-role"
            value={form.capital_role}
            onChange={(event) => setForm((prev) => ({ ...prev, capital_role: event.target.value as CapitalRole }))}
          >
            {CAPITAL_ROLES.map((value) => (
              <option key={value} value={value}>
                {t(`netWorth.capitalRole.${value}` as TranslationKey)}
              </option>
            ))}
          </Select>
          <p className="mt-1 text-xs text-text-muted">
            {t(`netWorth.capitalRoleFormHint.${form.capital_role}` as TranslationKey)}
          </p>
        </div>

        <div>
          <Label htmlFor="asset-risk">{t("netWorth.form.riskLevelLabel")}</Label>
          <Select
            id="asset-risk"
            value={form.risk_level}
            onChange={(event) => setForm((prev) => ({ ...prev, risk_level: event.target.value as RiskLevel }))}
          >
            {RISK_LEVELS.map((value) => (
              <option key={value} value={value}>
                {t(`netWorth.riskLevel.${value}` as TranslationKey)}
              </option>
            ))}
          </Select>
          <p className="mt-1 text-xs text-text-muted">
            {t(`netWorth.riskLevelFormHint.${form.risk_level}` as TranslationKey)}
          </p>
        </div>

        <div>
          <Label htmlFor="asset-cash-flow">{t("netWorth.form.cashFlowLabel")}</Label>
          <Input
            id="asset-cash-flow"
            type="text"
            inputMode="decimal"
            placeholder={t("netWorth.form.cashFlowPlaceholder")}
            value={form.monthly_cash_flow}
            onChange={(event) => setForm((prev) => ({ ...prev, monthly_cash_flow: event.target.value }))}
          />
          <p className="mt-1 text-xs text-text-muted">{t("netWorth.form.cashFlowHint")}</p>
        </div>

        <div>
          <Label htmlFor="asset-notes">{t("netWorth.form.notesLabel")}</Label>
          <Input
            id="asset-notes"
            maxLength={2000}
            value={form.notes}
            onChange={(event) => setForm((prev) => ({ ...prev, notes: event.target.value }))}
          />
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
