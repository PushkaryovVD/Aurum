import { api } from "@/api/client";
import type {
  CategorizationMatch,
  CategorizationMatchInput,
  CategorizationRule,
  CategorizationRuleInput,
  CategorizationRuleUpdateInput,
  RuleApplyResult,
} from "@/types";

export function fetchCategorizationRules() {
  return api.get<CategorizationRule[]>("/categorization-rules");
}

export function createCategorizationRule(input: CategorizationRuleInput) {
  return api.post<CategorizationRule>("/categorization-rules", input);
}

export function updateCategorizationRule(id: number, input: CategorizationRuleUpdateInput) {
  return api.patch<CategorizationRule>(`/categorization-rules/${id}`, input);
}

export function deleteCategorizationRule(id: number) {
  return api.delete<void>(`/categorization-rules/${id}`);
}

/** The complete order, top to bottom — the backend refuses a partial one. */
export function reorderCategorizationRules(orderedIds: number[]) {
  return api.post<CategorizationRule[]>("/categorization-rules/reorder", { ordered_ids: orderedIds });
}

/** `dryRun` defaults to true: rewriting the category on transactions that
 * already exist is something the caller has to ask for explicitly. */
export function applyCategorizationRules(
  options: { dryRun?: boolean; onlyUncategorized?: boolean } = {}
) {
  const params = new URLSearchParams({
    dry_run: String(options.dryRun ?? true),
    only_uncategorized: String(options.onlyUncategorized ?? true),
  });
  return api.post<RuleApplyResult>(`/categorization-rules/apply?${params.toString()}`, undefined);
}

/** Which rule would decide a transaction shaped like this one.
 *
 * The same answer the create path acts on, so a suggestion shown here is the
 * category that would be stored anyway. */
export function matchCategorizationRule(input: CategorizationMatchInput) {
  return api.post<CategorizationMatch>("/categorization-rules/match", input);
}
