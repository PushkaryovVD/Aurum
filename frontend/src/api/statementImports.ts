import { api } from "@/api/client";
import type { StatementCommitResult, StatementPreview, StatementRow } from "@/types";

export function previewStatement(file: File) {
  const body = new FormData();
  body.append("file", file);
  return api.postForm<StatementPreview>("/statement-imports/preview", body);
}

/** Sends the rows as the user corrected them, not as the parser read them —
 * the preview is the source of truth for what gets imported. */
export function commitStatement(
  provider: string,
  rows: StatementRow[],
  accountsByCurrency: Record<string, number>
) {
  return api.post<StatementCommitResult>("/statement-imports/commit", {
    provider,
    accounts_by_currency: accountsByCurrency,
    rows,
  });
}
