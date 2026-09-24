import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { addAssetValuation, acceptAssetProjection, createAsset, deleteAsset, fetchAssetRevaluationReminders, fetchAssets, updateAsset } from "@/api/assets";
import { ApiError } from "@/api/client";
import type { AssetInput, AssetUpdateInput, AssetValuationInput } from "@/types";

function useInvalidateNetWorth() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: ["assets"] });
    queryClient.invalidateQueries({ queryKey: ["net-worth-summary"] });
    queryClient.invalidateQueries({ queryKey: ["asset-revaluation-reminders"] });
  };
}

export function useAssets() {
  return useQuery({ queryKey: ["assets"], queryFn: fetchAssets });
}

export function useAssetRevaluationReminders() {
  return useQuery({ queryKey: ["asset-revaluation-reminders"], queryFn: fetchAssetRevaluationReminders });
}

export function useAcceptAssetProjection() {
  const invalidate = useInvalidateNetWorth();
  return useMutation({
    mutationFn: (id: number) => acceptAssetProjection(id),
    onSuccess: () => {
      invalidate();
    },
    onError: (error) => {
      if (error instanceof ApiError && (error.status === 404 || error.status === 409)) invalidate();
    },
  });
}

export function useCreateAsset() {
  const invalidate = useInvalidateNetWorth();
  return useMutation({
    mutationFn: (input: AssetInput) => createAsset(input),
    onSuccess: invalidate,
  });
}

export function useUpdateAsset() {
  const invalidate = useInvalidateNetWorth();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: AssetUpdateInput }) => updateAsset(id, input),
    onSuccess: invalidate,
  });
}

export function useAddAssetValuation() {
  const invalidate = useInvalidateNetWorth();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: AssetValuationInput }) => addAssetValuation(id, input),
    onSuccess: invalidate,
  });
}

export function useDeleteAsset() {
  const invalidate = useInvalidateNetWorth();
  return useMutation({
    mutationFn: (id: number) => deleteAsset(id),
    onSuccess: invalidate,
  });
}
