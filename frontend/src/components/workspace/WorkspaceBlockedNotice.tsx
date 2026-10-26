import { Lock } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useTranslation } from "@/lib/i18n";

/**
 * Replaces finance pages while the active workspace is blocked: an honest
 * explanation plus a way into the spaces that are still open, instead of a
 * page full of failed requests.
 */
export function WorkspaceBlockedNotice() {
  const { t } = useTranslation();
  const workspace = useWorkspace();
  if (!workspace) return null;
  const open = workspace.workspaces.filter((item) => item.status === "active");

  return <Card className="mx-auto max-w-xl">
    <CardContent className="space-y-4 p-5" role="alert">
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-danger/10 text-danger"><Lock size={18} /></span>
        <div className="min-w-0">
          <h1 className="text-base font-semibold text-text-primary">{t("workspace.blocked.title")}</h1>
          <p className="mt-1 text-sm text-text-secondary">{t("workspace.blocked.body", { name: workspace.activeWorkspace.display_name })}</p>
        </div>
      </div>
      {open.length === 0 ? <p className="text-sm text-text-muted">{t("workspace.blocked.none")}</p> :
      <div className="flex flex-col gap-2">
        {open.map((item) => <Button key={item.id} type="button" variant="secondary" className="justify-start text-left" disabled={workspace.switching} onClick={() => void workspace.switchWorkspace(item.id)}>
          <span className="truncate">{t("workspace.blocked.switch", { name: item.display_name })}</span>
        </Button>)}
      </div>}
    </CardContent>
  </Card>;
}
