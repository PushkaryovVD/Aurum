import { api } from "@/api/client";
import type { StatementCommitResult, StatementPreview } from "@/types";

export function previewStatement(file: File) {
  const body = new FormData();
  body.append("file", file);
  return api.postForm<StatementPreview>("/statement-imports/preview", body);
}

export function commitStatement(preview: StatementPreview, accountsByCurrency: Record<string, number>) {
  return api.post<StatementCommitResult>("/statement-imports/commit", {
    provider: preview.provider,
    accounts_by_currency: accountsByCurrency,
    rows: preview.rows,
  });
}
