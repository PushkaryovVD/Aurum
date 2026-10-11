import { useLocation } from "react-router-dom";
import { Menu } from "lucide-react";
import { NAV_ITEMS } from "@/lib/navigation";
import { useTranslation } from "@/lib/i18n";
import { useWorkspace } from "@/contexts/WorkspaceContext";

interface TopbarProps {
  mobileNavOpen: boolean;
  onOpenMobileNav: () => void;
}

export function Topbar({ mobileNavOpen, onOpenMobileNav }: TopbarProps) {
  const location = useLocation();
  const { t } = useTranslation();
  const workspace = useWorkspace();
  const activeItem = NAV_ITEMS.find((item) => (item.to === "/" ? location.pathname === "/" : location.pathname.startsWith(item.to)));

  return (
    <header className="sticky top-0 z-30 flex min-h-14 items-center gap-3 border-b border-border bg-surface-0/95 px-3 backdrop-blur sm:px-6 lg:px-8">
      <button
        type="button"
        onClick={onOpenMobileNav}
        aria-label={t("topbar.openMenu")}
        aria-controls="mobile-navigation"
        aria-expanded={mobileNavOpen}
        className="flex min-h-11 min-w-11 items-center justify-center rounded-md text-text-secondary hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus lg:hidden"
      >
        <Menu size={20} />
      </button>
      <span className="truncate text-sm font-medium text-text-secondary">{activeItem ? t(activeItem.labelKey) : "Aurum"}</span>
      {workspace && <label className="ml-auto flex min-w-0 items-center gap-2 text-xs text-text-muted">
        <span className="hidden sm:inline">{t("topbar.workspace")}</span>
        <select
          aria-label={t("topbar.workspace")}
          value={workspace.activeWorkspace.id}
          disabled={workspace.switching || workspace.workspaces.length < 2}
          onChange={(event) => void workspace.switchWorkspace(event.target.value)}
          className="min-h-11 max-w-48 truncate rounded-md border border-border bg-surface-1 px-3 text-sm text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus disabled:cursor-default disabled:opacity-80"
        >
          {workspace.workspaces.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}
        </select>
      </label>}
    </header>
  );
}
