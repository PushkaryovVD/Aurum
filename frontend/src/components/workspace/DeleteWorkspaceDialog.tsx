import { useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Input, Label } from "@/components/ui/Input";
import { useTranslation } from "@/lib/i18n";

interface DeleteWorkspaceDialogProps {
  /** The workspace to delete; null keeps the dialog closed. */
  workspace: { id: string; display_name: string } | null;
  pending: boolean;
  error: string | null;
  onClose: () => void;
  onConfirm: (confirmName: string) => void;
}

/**
 * Permanent deletion needs the exact workspace name typed by hand, the same
 * rule the server enforces, so a stray tap can never wipe a family's data.
 */
export function DeleteWorkspaceDialog({ workspace, pending, error, onClose, onConfirm }: DeleteWorkspaceDialogProps) {
  const { t } = useTranslation();
  const [typed, setTyped] = useState("");
  useEffect(() => setTyped(""), [workspace?.id]);
  if (!workspace) return null;
  const matches = typed.trim() === workspace.display_name.trim();
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (matches && !pending) onConfirm(typed);
  };

  return <Dialog open onClose={pending ? () => undefined : onClose} title={t("workspace.delete.title")}>
    <form className="space-y-4" onSubmit={submit}>
      <p className="rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm text-text-primary">
        {t("workspace.delete.warning", { name: workspace.display_name })}
      </p>
      <div className="space-y-1.5">
        <Label htmlFor="delete-workspace-name">{t("workspace.delete.prompt", { name: workspace.display_name })}</Label>
        <Input
          id="delete-workspace-name"
          name="confirm_name"
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
          autoComplete="off"
          autoCapitalize="off"
          spellCheck={false}
          maxLength={100}
          aria-label={t("workspace.delete.inputLabel")}
        />
      </div>
      {error && <p className="text-sm text-danger" role="alert">{t("workspace.delete.error", { reason: error })}</p>}
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button type="button" variant="secondary" disabled={pending} onClick={onClose}>{t("common.cancel")}</Button>
        <Button type="submit" variant="danger" disabled={!matches || pending}>{t("workspace.delete.confirm")}</Button>
      </div>
    </form>
  </Dialog>;
}
