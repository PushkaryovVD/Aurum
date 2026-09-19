import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  applyCategorizationRules,
  createCategorizationRule,
  deleteCategorizationRule,
  fetchCategorizationRules,
  reorderCategorizationRules,
  updateCategorizationRule,
} from "@/api/categorization";
import type { CategorizationRuleInput, CategorizationRuleUpdateInput } from "@/types";

export function useCategorizationRules() {
  return useQuery({ queryKey: ["categorization-rules"], queryFn: fetchCategorizationRules });
}

// Applying rules rewrites transactions, and a category name is denormalized
// into several read models — so a write here has to refresh the same set
// useCategories.ts invalidates after editing a category.
function invalidateRuleConsumers(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: ["categorization-rules"] });
  queryClient.invalidateQueries({ queryKey: ["transactions"] });
  queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
  queryClient.invalidateQueries({ queryKey: ["category-spending-report"] });
  queryClient.invalidateQueries({ queryKey: ["category-ranking"] });
  queryClient.invalidateQueries({ queryKey: ["budgets"] });
  queryClient.invalidateQueries({ queryKey: ["budget-status"] });
}

export function useCreateCategorizationRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CategorizationRuleInput) => createCategorizationRule(input),
    onSuccess: () => invalidateRuleConsumers(queryClient),
  });
}

export function useUpdateCategorizationRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: CategorizationRuleUpdateInput }) =>
      updateCategorizationRule(id, input),
    onSuccess: () => invalidateRuleConsumers(queryClient),
  });
}

export function useDeleteCategorizationRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteCategorizationRule(id),
    onSuccess: () => invalidateRuleConsumers(queryClient),
  });
}

export function useReorderCategorizationRules() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (orderedIds: number[]) => reorderCategorizationRules(orderedIds),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["categorization-rules"] }),
  });
}

export function useApplyCategorizationRules() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (options: { dryRun?: boolean; onlyUncategorized?: boolean }) =>
      applyCategorizationRules(options),
    // A dry run changes nothing, so invalidating after one would only refetch
    // identical data.
    onSuccess: (result) => {
      if (!result.dry_run) invalidateRuleConsumers(queryClient);
    },
  });
}
