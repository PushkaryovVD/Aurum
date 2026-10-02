import { useLocation } from "react-router-dom";
import { Menu } from "lucide-react";
import { NAV_ITEMS } from "@/lib/navigation";
import { useTranslation } from "@/lib/i18n";

interface TopbarProps {
  mobileNavOpen: boolean;
  onOpenMobileNav: () => void;
}

export function Topbar({ mobileNavOpen, onOpenMobileNav }: TopbarProps) {
  const location = useLocation();
  const { t } = useTranslation();
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
      <span className="truncate text-lg font-semibold text-text-primary">{activeItem ? t(activeItem.labelKey) : "Aurum"}</span>
    </header>
  );
}
