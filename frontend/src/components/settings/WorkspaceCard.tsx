import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  acceptWorkspaceInvitation,
  createWorkspace,
  createWorkspaceInvitation,
  fetchIdentitySession,
  fetchWorkspaceMembers,
  removeWorkspaceMember,
  updateWorkspaceMember,
  type WorkspaceInvitation,
} from "@/api/workspaces";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input, Label, Select } from "@/components/ui/Input";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { parseSession } from "@/lib/authSession";
import { useTranslation } from "@/lib/i18n";

export function WorkspaceCard() {
  const { t } = useTranslation();
  const workspace = useWorkspace();
  const queryClient = useQueryClient();
  const [issued, setIssued] = useState<WorkspaceInvitation | null>(null);
  const active = workspace?.activeWorkspace;
  const canAdminister = active?.kind === "household" && active.role === "owner";
  const members = useQuery({
    queryKey: ["workspace-members", active?.id],
    queryFn: () => fetchWorkspaceMembers(active!.id),
    enabled: Boolean(canAdminister),
  });

  const refreshSession = async () => {
    if (!workspace) return;
    await workspace.replaceSession(parseSession(await fetchIdentitySession()));
  };
  const create = useMutation({ mutationFn: createWorkspace, onSuccess: refreshSession });
  const accept = useMutation({ mutationFn: acceptWorkspaceInvitation, onSuccess: async (value) => workspace?.replaceSession(parseSession(value)) });
  const invite = useMutation({
    mutationFn: ({ recipient, role }: { recipient: string; role: "editor" | "viewer" }) => createWorkspaceInvitation(active!.id, recipient, role),
    onSuccess: setIssued,
  });
  const update = useMutation({
    mutationFn: ({ id, role }: { id: string; role: "editor" | "viewer" }) => updateWorkspaceMember(active!.id, id, role),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["workspace-members", active?.id] }),
  });
  const remove = useMutation({
    mutationFn: (id: string) => removeWorkspaceMember(active!.id, id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["workspace-members", active?.id] }),
  });
  const signOut = useMutation({ mutationFn: () => workspace!.signOut() });

  if (!workspace || !active) return null;
  const submit = (handler: (data: FormData) => void) => (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    handler(new FormData(event.currentTarget));
  };
  const error = create.error || accept.error || invite.error || update.error || remove.error || signOut.error;

  return <Card>
    <CardHeader><CardTitle>{t("workspace.title")}</CardTitle></CardHeader>
    <CardContent className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="min-w-0 flex-1"><p className="truncate font-medium text-text-primary">{workspace.user.display_name || workspace.user.identifier}</p><p className="truncate text-xs text-text-muted">{workspace.user.identifier} · {active.display_name} · {active.kind === "personal" ? t("workspace.kind.personal") : t("workspace.kind.household")} · {active.role === "owner" ? t("workspace.role.owner") : active.role === "editor" ? t("workspace.role.editor") : t("workspace.role.viewer")}</p></div>
        <Button type="button" variant="secondary" disabled={signOut.isPending} onClick={() => signOut.mutate()}>{t("entry.signOut")}</Button>
      </div>

      <form className="grid gap-3 sm:grid-cols-[1fr_auto]" onSubmit={submit((data) => create.mutate(String(data.get("name") ?? "").trim()))}>
        <div><Label htmlFor="workspace-name">{t("workspace.createLabel")}</Label><Input id="workspace-name" name="name" required maxLength={100} /></div>
        <Button className="self-end" disabled={create.isPending}>{t("workspace.create")}</Button>
      </form>

      <form className="grid gap-3 sm:grid-cols-[1fr_auto]" onSubmit={submit((data) => accept.mutate(String(data.get("token") ?? "").trim()))}>
        <div><Label htmlFor="invitation-token">{t("workspace.acceptLabel")}</Label><Input id="invitation-token" name="token" required autoComplete="off" /></div>
        <Button className="self-end" variant="secondary" disabled={accept.isPending}>{t("workspace.accept")}</Button>
      </form>

      {canAdminister && <section className="space-y-4 border-t border-border pt-5">
        <h4 className="font-medium">{t("workspace.members")}</h4>
        {members.isLoading && <p className="text-sm text-text-muted">{t("common.loading")}</p>}
        {members.isError && <p className="text-sm text-danger" role="alert">{t("workspace.loadError")}</p>}
        <ul className="space-y-2">
          {members.data?.map((member) => <li key={member.id} className="flex flex-col gap-2 rounded-lg border border-border p-3 sm:flex-row sm:items-center">
            <div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{member.display_name || member.identifier}</p><p className="truncate text-xs text-text-muted">{member.identifier}</p></div>
            {member.role === "owner" ? <span className="text-xs text-text-muted">{t("workspace.role.owner")}</span> : <>
              <Select aria-label={t("workspace.memberRole")} className="min-h-11 sm:w-32" value={member.role} disabled={update.isPending || remove.isPending} onChange={(event) => update.mutate({ id: member.id, role: event.target.value as "editor" | "viewer" })}><option value="editor">{t("workspace.role.editor")}</option><option value="viewer">{t("workspace.role.viewer")}</option></Select>
              <Button type="button" variant="danger" disabled={remove.isPending} onClick={() => { if (window.confirm(t("workspace.removeConfirm"))) remove.mutate(member.id); }}>{t("workspace.remove")}</Button>
            </>}
          </li>)}
        </ul>
        <form className="grid gap-3 sm:grid-cols-[1fr_9rem_auto]" onSubmit={submit((data) => invite.mutate({ recipient: String(data.get("recipient") ?? "").trim(), role: String(data.get("role")) as "editor" | "viewer" }))}>
          <div><Label htmlFor="invite-recipient">{t("workspace.inviteRecipient")}</Label><Input id="invite-recipient" name="recipient" required maxLength={320} /></div>
          <div><Label htmlFor="invite-role">{t("workspace.memberRole")}</Label><Select id="invite-role" name="role" className="min-h-11"><option value="editor">{t("workspace.role.editor")}</option><option value="viewer">{t("workspace.role.viewer")}</option></Select></div>
          <Button className="self-end" disabled={invite.isPending}>{t("workspace.invite")}</Button>
        </form>
        {issued && <div className="rounded-lg border border-warning/40 bg-warning/10 p-3"><p className="text-sm font-medium">{t("workspace.tokenOnce")}</p><code className="mt-2 block break-all text-xs">{issued.token}</code><Button type="button" variant="secondary" className="mt-3" onClick={() => void navigator.clipboard?.writeText(issued.token)}>{t("workspace.copy")}</Button></div>}
      </section>}
      {error && <p className="text-sm text-danger" role="alert">{t("workspace.actionError")}</p>}
    </CardContent>
  </Card>;
}
