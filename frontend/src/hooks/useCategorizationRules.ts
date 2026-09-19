import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  applyCategorizationRules,
  createCategorizationRule,
  deleteCategorizationRule,
  fetchCategorizationRules,
  matchCategorizationRule,
  reorderCategorizationRules,
  updateCategorizationRule,
} from "@/api/categorization";
import type {
  CategorizationMatchQuery,
  CategorizationRuleInput,
  CategorizationRuleUpdateInput,
} from "@/types";

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

// Long enough that a description typed at speed costs one request instead of
// one per keystroke; short enough that the suggestion is there by the time the
// user reaches the category field.
const MATCH_DEBOUNCE_MS = 400;

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

/** Which rule would decide a transaction shaped like the one being typed.
 *
 * The answer is the one the create path acts on, so a category shown while
 * filling the form is the category that would be stored anyway — it simply
 * arrives with the reason attached.
 */
export function useCategorizationMatch(input: CategorizationMatchQuery) {
  const description = useDebounced(input.description, MATCH_DEBOUNCE_MS);
  const enabled =
    description.trim().length > 0 &&
    Number(input.amount) > 0 &&
    Boolean(input.currency) &&
    Boolean(input.account_id) &&
    input.transaction_type !== "transfer";
  return useQuery({
    queryKey: [
      "categorization-match",
      description,
      input.amount,
      input.currency,
      input.account_id,
      input.transaction_type,
    ],
    queryFn: () =>
      matchCategorizationRule({
        description,
        amount: input.amount,
        currency: input.currency,
        account_id: input.account_id!,
        transaction_type: input.transaction_type,
      }),
    enabled,
    // The rule set changes rarely, so a short stale window keeps typing from
    // re-asking the same question.
    staleTime: 30_000,
    retry: false,
  });
}
