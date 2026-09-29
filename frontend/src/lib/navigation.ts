import {
  Activity,
  ArrowLeftRight,
  Calculator,
  Flag,
  Layers,
  Lightbulb,
  ListChecks,
  LayoutDashboard,
  PieChart,
  Repeat,
  Settings,
  Tags,
  Target,
  TrendingUp,
  Landmark,
  WalletCards,
  type LucideIcon,
} from "lucide-react";

import type { TranslationKey } from "@/lib/i18n";

export interface NavItem {
  labelKey: TranslationKey;
  to: string;
  icon: LucideIcon;
  disabled?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { labelKey: "nav.dashboard", to: "/", icon: LayoutDashboard },
  { labelKey: "nav.netWorth", to: "/net-worth", icon: TrendingUp },
  { labelKey: "nav.investments", to: "/investments", icon: Landmark },
  { labelKey: "nav.roi", to: "/roi", icon: Calculator },
  { labelKey: "nav.transactions", to: "/transactions", icon: ArrowLeftRight },
  { labelKey: "nav.accounts", to: "/accounts", icon: Layers },
  { labelKey: "nav.categories", to: "/categories", icon: Tags },
  // Sits next to Categories on purpose: the rules are what decides which
  // category a transaction lands in, so the two are edited together.
  { labelKey: "nav.rules", to: "/rules", icon: ListChecks },
  { labelKey: "nav.cashFlow", to: "/cash-flow", icon: Activity },
  { labelKey: "nav.reports", to: "/reports", icon: PieChart },
  { labelKey: "nav.budget", to: "/budget", icon: Target },
  { labelKey: "nav.envelopes", to: "/envelopes", icon: WalletCards },
  { labelKey: "nav.recurring", to: "/recurring", icon: Repeat },
  { labelKey: "nav.goals", to: "/goals", icon: Flag },
  { labelKey: "nav.advice", to: "/advice", icon: Lightbulb },
  { labelKey: "nav.settings", to: "/settings", icon: Settings },
];
