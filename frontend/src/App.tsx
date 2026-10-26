import { lazy, useEffect, useState } from "react";
import { Route, Routes, useLocation } from "react-router-dom";
import { RouteBoundary } from "@/components/layout/RouteBoundary";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { WorkspaceBlockedNotice } from "@/components/workspace/WorkspaceBlockedNotice";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useLocalStorageState } from "@/hooks/useLocalStorageState";
import { useAppSettings } from "@/hooks/useSettings";
import { setCurrency } from "@/lib/i18n";
const AdminPage = lazy(() => import("@/pages/AdminPage").then((m) => ({ default: m.AdminPage })));
const AccountsPage = lazy(() => import("@/pages/AccountsPage").then((m) => ({ default: m.AccountsPage })));
const AdvicePage = lazy(() => import("@/pages/AdvicePage").then((m) => ({ default: m.AdvicePage })));
const BudgetPage = lazy(() => import("@/pages/BudgetPage").then((m) => ({ default: m.BudgetPage })));
const CashFlowPage = lazy(() => import("@/pages/CashFlowPage").then((m) => ({ default: m.CashFlowPage })));
const CategoriesPage = lazy(() => import("@/pages/CategoriesPage").then((m) => ({ default: m.CategoriesPage })));
const CategorizationRulesPage = lazy(() => import("@/pages/CategorizationRulesPage").then((m) => ({ default: m.CategorizationRulesPage })));
const CryptoPage = lazy(() => import("@/pages/CryptoPage").then((m) => ({ default: m.CryptoPage })));
const CsvImportPage = lazy(() => import("@/pages/CsvImportPage").then((m) => ({ default: m.CsvImportPage })));
import { DashboardPage } from "@/pages/DashboardPage";
const EnvelopePage = lazy(() => import("@/pages/EnvelopePage").then((m) => ({ default: m.EnvelopePage })));
const GoalsPage = lazy(() => import("@/pages/GoalsPage").then((m) => ({ default: m.GoalsPage })));
const HelpPage = lazy(() => import("@/pages/HelpPage").then((m) => ({ default: m.HelpPage })));
const ImportCenterPage = lazy(() => import("@/pages/ImportCenterPage").then((m) => ({ default: m.ImportCenterPage })));
const InvestmentsPage = lazy(() => import("@/pages/InvestmentsPage").then((m) => ({ default: m.InvestmentsPage })));
const NetWorthPage = lazy(() => import("@/pages/NetWorthPage").then((m) => ({ default: m.NetWorthPage })));
const RecurringPage = lazy(() => import("@/pages/RecurringPage").then((m) => ({ default: m.RecurringPage })));
const ReportsPage = lazy(() => import("@/pages/ReportsPage").then((m) => ({ default: m.ReportsPage })));
const RoiPage = lazy(() => import("@/pages/RoiPage").then((m) => ({ default: m.RoiPage })));
const SettingsPage = lazy(() => import("@/pages/SettingsPage").then((m) => ({ default: m.SettingsPage })));
const StatementImportPage = lazy(() => import("@/pages/StatementImportPage").then((m) => ({ default: m.StatementImportPage })));
const TransactionsPage = lazy(() => import("@/pages/TransactionsPage").then((m) => ({ default: m.TransactionsPage })));
import { AppAccessGate } from "@/components/auth/AppAccessGate";

export default function App() {
  // Financial hooks live strictly below the public mode/identity entry boundary.
  return <AppAccessGate><FinancialShell /></AppAccessGate>;
}

function FinancialShell() {
  const [collapsed, setCollapsed] = useLocalStorageState("aurum:sidebar-collapsed", false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const { pathname } = useLocation();
  const workspace = useWorkspace();
  // Administration and help never read the active space's finances.
  const blocked = workspace?.activeWorkspace.status === "blocked" && !["/admin", "/help"].includes(pathname);

  // Primary currency is server-persisted, unlike language — sync the
  // client-side reactive mirror (lib/i18n's getCurrency/formatCurrency)
  // once the setting loads, so it's not stuck on the "USD" fallback default.
  const { data: settings } = useAppSettings();
  useEffect(() => {
    if (settings) setCurrency(settings.currency);
  }, [settings]);

  return (
    <div className="flex min-h-dvh w-full min-w-0 overflow-x-clip bg-surface-0">
      <Sidebar
        collapsed={collapsed}
        onToggleCollapsed={() => setCollapsed(!collapsed)}
        mobileOpen={mobileNavOpen}
        onCloseMobile={() => setMobileNavOpen(false)}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar mobileNavOpen={mobileNavOpen} onOpenMobileNav={() => setMobileNavOpen(true)} />
        {/* No max-width cap — the sidebar can be collapsed to free up space
            (see Sidebar.tsx's collapsed w-[72px] vs expanded w-56), and a
            fixed max-w here would leave that freed space as dead centered
            gutter instead of handing it to the page. Padding alone keeps
            content off the sidebar/viewport edges. */}
        <main className="w-full min-w-0 px-page-inline py-page-block">
          <RouteBoundary key={pathname}>
          {blocked ? <WorkspaceBlockedNotice /> : <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/net-worth" element={<NetWorthPage />} />
            <Route path="/crypto" element={<CryptoPage />} />
            <Route path="/investments" element={<InvestmentsPage />} />
            <Route path="/roi" element={<RoiPage />} />
            <Route path="/accounts" element={<AccountsPage />} />
            <Route path="/categories" element={<CategoriesPage />} />
            <Route path="/rules" element={<CategorizationRulesPage />} />
            <Route path="/cash-flow" element={<CashFlowPage />} />
            <Route path="/transactions" element={<TransactionsPage />} />
            <Route path="/transactions/import" element={<ImportCenterPage />} />
            <Route path="/transactions/import/csv" element={<CsvImportPage />} />
            <Route path="/transactions/import/statements" element={<StatementImportPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/budget" element={<BudgetPage />} />
            <Route path="/envelopes" element={<EnvelopePage />} />
            <Route path="/advice" element={<AdvicePage />} />
            <Route path="/goals" element={<GoalsPage />} />
            <Route path="/recurring" element={<RecurringPage />} />
            <Route path="/help" element={<HelpPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/admin" element={<AdminPage />} />
          </Routes>}
          </RouteBoundary>
        </main>
      </div>
    </div>
  );
}
