import { api } from "@/api/client";
import type { Asset, AssetInput, AssetRevaluationReminder, AssetUpdateInput, AssetValuationInput } from "@/types";

export function fetchAssets() {
  return api.get<Asset[]>("/assets");
}

export function createAsset(input: AssetInput) {
  return api.post<Asset>("/assets", input);
}

export function updateAsset(id: number, input: AssetUpdateInput) {
  return api.patch<Asset>(`/assets/${id}`, input);
}

export function addAssetValuation(id: number, input: AssetValuationInput) {
  return api.post<Asset>(`/assets/${id}/valuations`, input);
}

export function fetchAssetRevaluationReminders() {
  return api.get<AssetRevaluationReminder[]>("/assets/revaluation-reminders");
}

export function acceptAssetProjection(id: number) {
  return api.post<Asset>(`/assets/${id}/revaluation-reminders/accept`, {});
}

export function deleteAsset(id: number) {
  return api.delete<void>(`/assets/${id}`);
}
