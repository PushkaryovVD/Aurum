import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import {
  adminDeleteWorkspace,
  changeAdminUser,
  changeAdminWorkspace,
  fetchAdminUsers,
  fetchAdminWorkspaces,
  type AdminRole,
  type AdminUser,
  type AdminUserAction,
  type AdminWorkspace,
} from "@/api/admin";
import { DeleteWorkspaceDialog } from "@/components/workspace/DeleteWorkspaceDialog";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Page, PageHeader } from "@/components/ui/Page";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { getIntlLocale } from "@/lib/format";
import { useTranslation, type TranslationKey } from "@/lib/i18n";
import { cn } from "@/lib/utils";

type Tab = "users" | "workspaces";

const USERS_KEY = ["admin", "users"] as const;
const WORKSPACES_KEY = ["admin", "workspaces"] as const;

const ROLE_KEYS: Record<AdminRole, TranslationKey> = {
  owner: "workspace.role.owner",
  editor: "workspace.role.editor",
  viewer: "workspace.role.viewer",
};

function formatMoment(iso: string): string {
  return new Date(iso).toLocaleString(getIntlLocale(), { dateStyle: "medium", timeStyle: "short" });
}

function errorReason(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** Installation administration: people and spaces, never their finances. */
export function AdminPage() {
  const { t } = useTranslation();
  const workspace = useWorkspace();
  const [tab, setTab] = useState<Tab>("users");

  if (!workspace?.user.is_admin) {
    return <Page><PageHeader title={t("admin.title")} /><p className="text-sm text-text-secondary" role="alert">{t("admin.forbidden")}</p></Page>;
  }

  return <Page>
    <PageHeader title={t("admin.title")} description={t("admin.description")} />
    <div role="tablist" aria-label={t("admin.title")} className="grid grid-cols-2 gap-1 rounded-lg border border-border bg-surface-1 p-1 sm:inline-grid sm:w-auto">
      {(["users", "workspaces"] as const).map((value) => <button
        key={value}
        type="button"
        role="tab"
        aria-selected={tab === value}
        onClick={() => setTab(value)}
        className={cn(
          "min-h-11 rounded-md px-4 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus",
          tab === value ? "bg-surface-2 text-text-primary" : "text-text-muted hover:text-text-primary"
        )}
      >{t(value === "users" ? "admin.tab.users" : "admin.tab.workspaces")}</button>)}
    </div>
    {tab === "users" ? <UsersSection /> : <WorkspacesSection />}
  </Page>;
}

function LoadState({ isLoading, error, onRetry }: { isLoading: boolean; error: unknown; onRetry: () => void }) {
  const { t } = useTranslation();
  if (isLoading) return <p className="text-sm text-text-muted" role="status">{t("common.loading")}</p>;
  if (!error) return null;
  return <div className="flex flex-col gap-3 rounded-lg border border-danger/30 bg-danger/10 p-4 sm:flex-row sm:items-center" role="alert">
    <p className="flex-1 text-sm text-danger">{t("admin.loadError")} {errorReason(error)}</p>
    <Button type="button" variant="secondary" onClick={onRetry}>{t("admin.retry")}</Button>
  </div>;
}

function UsersSection() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const users = useQuery({ queryKey: USERS_KEY, queryFn: fetchAdminUsers });
  const change = useMutation({
    mutationFn: ({ user, action }: { user: AdminUser; action: AdminUserAction }) => changeAdminUser(user.id, action),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin"] }),
  });

  const confirmKeys: Record<AdminUserAction, TranslationKey> = {
    block: "admin.confirm.block",
    unblock: "admin.confirm.unblock",
    "grant-admin": "admin.confirm.grantAdmin",
    "revoke-admin": "admin.confirm.revokeAdmin",
  };
  const run = (user: AdminUser, action: AdminUserAction) => {
    if (window.confirm(t(confirmKeys[action], { name: user.display_name || user.identifier }))) change.mutate({ user, action });
  };

  return <section className="space-y-3" aria-label={t("admin.tab.users")}>
    <LoadState isLoading={users.isLoading} error={users.error} onRetry={() => void users.refetch()} />
    {change.error && <p className="text-sm text-danger" role="alert">{t("admin.actionError", { reason: errorReason(change.error) })}</p>}
    {users.data?.length === 0 && <p className="text-sm text-text-muted">{t("admin.empty")}</p>}
    <ul className="space-y-3">
      {users.data?.map((user) => <li key={user.id}><Card><CardContent className="space-y-3 p-4">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <p className="min-w-0 flex-1 basis-40 truncate font-medium text-text-primary">{user.display_name || user.identifier}</p>
          {user.is_self && <Badge>{t("admin.user.you")}</Badge>}
          {user.is_admin && <Badge className="bg-surface-accent text-text-primary"><ShieldCheck size={12} className="mr-1" />{t("admin.user.admin")}</Badge>}
          <Badge className={user.status === "disabled" ? "bg-danger/15 text-danger" : undefined}>
            {t(user.status === "disabled" ? "admin.user.blocked" : "admin.user.active")}
          </Badge>
        </div>
        <div className="space-y-0.5 text-xs text-text-muted">
          <p className="break-all">{user.identifier}</p>
          <p>{t("admin.user.registered", { date: formatMoment(user.created_at) })}</p>
          <p>{user.last_login_at ? t("admin.user.lastLogin", { date: formatMoment(user.last_login_at) }) : t("admin.user.neverSignedIn")}</p>
        </div>
        <div>
          <p className="text-xs font-medium text-text-secondary">{t("admin.user.spaces")}</p>
          {user.memberships.length === 0 ? <p className="text-xs text-text-muted">{t("admin.user.noSpaces")}</p> :
          <ul className="mt-1 flex flex-wrap gap-1.5">
            {user.memberships.map((membership) => <li key={membership.workspace_id}>
              <Badge className={cn("max-w-full", membership.status === "blocked" && "bg-danger/15 text-danger")}>
                <span className="truncate">{membership.display_name} · {t(ROLE_KEYS[membership.role])}{membership.status === "blocked" ? ` · ${t("workspace.status.blocked")}` : ""}</span>
              </Badge>
            </li>)}
          </ul>}
        </div>
        {user.is_self ? <p className="text-xs text-text-muted">{t("admin.user.selfHint")}</p> :
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
          {user.status === "active"
            ? <Button type="button" variant="danger" disabled={change.isPending} onClick={() => run(user, "block")}>{t("admin.user.block")}</Button>
            : <Button type="button" variant="secondary" disabled={change.isPending} onClick={() => run(user, "unblock")}>{t("admin.user.unblock")}</Button>}
          {user.is_admin
            ? <Button type="button" variant="secondary" disabled={change.isPending} onClick={() => run(user, "revoke-admin")}>{t("admin.user.revokeAdmin")}</Button>
            : user.status === "active" && <Button type="button" variant="secondary" disabled={change.isPending} onClick={() => run(user, "grant-admin")}>{t("admin.user.grantAdmin")}</Button>}
        </div>}
      </CardContent></Card></li>)}
    </ul>
  </section>;
}

function WorkspacesSection() {
  const { t } = useTranslation();
  const session = useWorkspace();
  const queryClient = useQueryClient();
  const workspaces = useQuery({ queryKey: WORKSPACES_KEY, queryFn: fetchAdminWorkspaces });
  const [deleting, setDeleting] = useState<AdminWorkspace | null>(null);
  const change = useMutation({
    mutationFn: ({ item, action }: { item: AdminWorkspace; action: "block" | "unblock" }) => changeAdminWorkspace(item.id, action),
    onSuccess: (updated) => {
      // Keep the switcher honest if the admin is a member of that space.
      session?.setWorkspaceStatus(updated.id, updated.status);
      return queryClient.invalidateQueries({ queryKey: ["admin"] });
    },
  });
  const remove = useMutation({
    mutationFn: ({ item, confirmName }: { item: AdminWorkspace; confirmName: string }) => adminDeleteWorkspace(item.id, confirmName),
    onSuccess: async (_value, { item }) => {
      setDeleting(null);
      await queryClient.invalidateQueries({ queryKey: ["admin"] });
      await session?.dropWorkspace(item.id);
    },
  });

  const toggle = (item: AdminWorkspace) => {
    const action = item.status === "active" ? "block" : "unblock";
    const key: TranslationKey = action === "block" ? "admin.confirm.blockWorkspace" : "admin.confirm.unblockWorkspace";
    if (window.confirm(t(key, { name: item.display_name }))) change.mutate({ item, action });
  };

  return <section className="space-y-3" aria-label={t("admin.tab.workspaces")}>
    <LoadState isLoading={workspaces.isLoading} error={workspaces.error} onRetry={() => void workspaces.refetch()} />
    {change.error && <p className="text-sm text-danger" role="alert">{t("admin.actionError", { reason: errorReason(change.error) })}</p>}
    {workspaces.data?.length === 0 && <p className="text-sm text-text-muted">{t("admin.empty")}</p>}
    <ul className="space-y-3">
      {workspaces.data?.map((item) => <li key={item.id}><Card><CardContent className="space-y-3 p-4">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <p className="min-w-0 flex-1 basis-40 truncate font-medium text-text-primary">{item.display_name}</p>
          <Badge>{t(item.kind === "personal" ? "workspace.kind.personal" : "workspace.kind.household")}</Badge>
          {item.status === "blocked" && <Badge className="bg-danger/15 text-danger">{t("workspace.status.blocked")}</Badge>}
        </div>
        <div className="space-y-0.5 text-xs text-text-muted">
          <p>{t("admin.workspace.created", { date: formatMoment(item.created_at) })}</p>
          {item.blocked_at && <p>{t("admin.workspace.blockedSince", { date: formatMoment(item.blocked_at) })}</p>}
        </div>
        <div>
          <p className="text-xs font-medium text-text-secondary">{t("admin.workspace.members")}</p>
          {item.members.length === 0 ? <p className="text-xs text-text-muted">{t("admin.workspace.noMembers")}</p> :
          <ul className="mt-1 space-y-0.5 text-xs text-text-secondary">
            {item.members.map((member) => <li key={member.user_id} className="break-all">
              {member.display_name || member.identifier} · {t(ROLE_KEYS[member.role])}
            </li>)}
          </ul>}
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
          <Button type="button" variant={item.status === "active" ? "secondary" : "primary"} disabled={change.isPending} onClick={() => toggle(item)}>
            {t(item.status === "active" ? "admin.workspace.block" : "admin.workspace.unblock")}
          </Button>
          {item.kind === "household"
            ? <Button type="button" variant="danger" disabled={remove.isPending} onClick={() => { remove.reset(); setDeleting(item); }}>{t("admin.workspace.delete")}</Button>
            : <p className="text-xs text-text-muted">{t("admin.workspace.personalNoDelete")}</p>}
        </div>
      </CardContent></Card></li>)}
    </ul>
    <DeleteWorkspaceDialog
      workspace={deleting}
      pending={remove.isPending}
      error={remove.error ? errorReason(remove.error) : null}
      onClose={() => setDeleting(null)}
      onConfirm={(confirmName) => deleting && remove.mutate({ item: deleting, confirmName })}
    />
  </section>;
}
