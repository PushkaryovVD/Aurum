import { useState } from "react";
import { Plus } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { NetWorthChart } from "@/components/networth/NetWorthChart";
import { AssetAllocationCard } from "@/components/networth/AssetAllocationCard";
import { CapitalRoleSummaryCard } from "@/components/networth/CapitalRoleSummaryCard";
import { RiskAllocationCard } from "@/components/networth/RiskAllocationCard";
import { AssetsTable } from "@/components/networth/AssetsTable";
import { AssetFormModal } from "@/components/networth/AssetFormModal";
import { AlertBanner } from "@/components/insights/AlertBanner";
import { useNetWorthSummary } from "@/hooks/useNetWorth";
import { useAcceptAssetProjection, useAssetRevaluationReminders, useAssets, useDeleteAsset } from "@/hooks/useAssets";
import { formatCurrency, formatTransactionDate } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import type { Asset, AssetRevaluationReminder, NetWorthRange } from "@/types";

interface AssetRevaluationReminderCardProps {
  reminder: AssetRevaluationReminder;
  asset?: Asset;
  isPending: boolean;
  onAccept: (assetId: number) => void;
  onEnterMarketValue: (asset: Asset) => void;
}

export function AssetRevaluationReminderCard({ reminder, asset, isPending, onAccept, onEnterMarketValue }: AssetRevaluationReminderCardProps) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm text-text-primary sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p className="font-medium">{t("netWorth.revaluation.title")}</p>
        <p className="mt-1 text-text-secondary">
          {t("netWorth.revaluation.message", { name: reminder.asset_name, date: formatTransactionDate(reminder.latest_market_value_date) })}
        </p>
      </div>
      <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
        <Button className="w-full sm:w-auto" variant="ghost" onClick={() => asset && onEnterMarketValue(asset)} disabled={!asset}>
          {t("netWorth.revaluation.enterMarketValue")}
        </Button>
        <Button className="w-full sm:w-auto" onClick={() => onAccept(reminder.asset_id)} disabled={isPending}>
          {t("netWorth.revaluation.accept", { value: formatCurrency(reminder.projected_value) })}
        </Button>
      </div>
    </div>
  );
}

export function NetWorthPage() {
  const { t } = useTranslation();
  // Defaults to 5 years: a short window can show a dip whenever spending
  // briefly outpaces recorded income, which reads as decline even though
  // the long-run trend is up — 5y is long enough to make that trend visible.
  const [range, setRange] = useState<NetWorthRange>("5y");
  const { data: summary, isLoading: isSummaryLoading } = useNetWorthSummary(range);
  const { data: assets, isLoading: isAssetsLoading } = useAssets();
  const { data: revaluationReminders } = useAssetRevaluationReminders();
  const deleteAsset = useDeleteAsset();
  const acceptProjection = useAcceptAssetProjection();

  const [modalOpen, setModalOpen] = useState(false);
  const [editingAsset, setEditingAsset] = useState<Asset | null>(null);
  const [recordValuationOnSave, setRecordValuationOnSave] = useState(false);

  function openCreateModal() {
    setEditingAsset(null);
    setRecordValuationOnSave(false);
    setModalOpen(true);
  }

  function openEditModal(asset: Asset) {
    setEditingAsset(asset);
    setRecordValuationOnSave(false);
    setModalOpen(true);
  }

  function openMarketValuationModal(asset: Asset) {
    setEditingAsset(asset);
    setRecordValuationOnSave(true);
    setModalOpen(true);
  }

  function handleDelete(asset: Asset) {
    if (window.confirm(t("netWorth.confirmDeleteAsset", { name: asset.name }))) {
      deleteAsset.mutate(asset.id);
    }
  }

  return (
    <div className="space-y-5">
      <AlertBanner />

      {(revaluationReminders ?? []).map((reminder) => (
        <AssetRevaluationReminderCard
          key={reminder.asset_id}
          reminder={reminder}
          asset={assets?.find((item) => item.id === reminder.asset_id)}
          isPending={acceptProjection.isPending}
          onAccept={(assetId) => acceptProjection.mutate(assetId)}
          onEnterMarketValue={openMarketValuationModal}
        />
      ))}

      <NetWorthChart summary={summary} isLoading={isSummaryLoading} range={range} onRangeChange={setRange} />

      <AssetAllocationCard breakdown={summary?.breakdown ?? []} isLoading={isSummaryLoading} />

      <CapitalRoleSummaryCard roles={summary?.capital_roles ?? []} isLoading={isSummaryLoading} />

      <RiskAllocationCard riskLevels={summary?.risk_levels ?? []} isLoading={isSummaryLoading} />

      <Card>
        <CardHeader>
          <CardTitle>{t("netWorth.myAssetsTitle")}</CardTitle>
          <Button onClick={openCreateModal}>
            <Plus size={16} />
            {t("common.add")}
          </Button>
        </CardHeader>
        <CardContent>
          {isAssetsLoading ? (
            <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : (
            <AssetsTable items={assets ?? []} onEdit={openEditModal} onDelete={handleDelete} />
          )}
        </CardContent>
      </Card>

      <AssetFormModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        asset={editingAsset}
        recordValuationOnSave={recordValuationOnSave}
      />
    </div>
  );
}
