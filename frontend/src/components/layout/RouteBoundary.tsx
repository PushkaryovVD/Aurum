import { Component, Suspense, type ErrorInfo, type ReactNode } from "react";
import { Button } from "@/components/ui/Button";
import { useTranslation } from "@/lib/i18n";

/** Shown when a route chunk fails to download (offline, or a stale tab after a redeploy). */
function RouteLoadError({ onRetry }: { onRetry: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="space-y-3 rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger" role="alert">
      <p>{t("route.loadFailed")}</p>
      <Button variant="secondary" onClick={onRetry}>
        {t("route.reload")}
      </Button>
    </div>
  );
}

function RouteLoading() {
  const { t } = useTranslation();
  return (
    <p className="py-8 text-center text-sm text-text-muted" role="status">
      {t("common.loading")}
    </p>
  );
}

class RouteErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Route failed to render", error, info.componentStack);
  }

  render() {
    // A failed dynamic import is not retried by React, so a reload is the honest recovery.
    if (this.state.failed) return <RouteLoadError onRetry={() => window.location.reload()} />;
    return this.props.children;
  }
}

/** Suspense + error boundary around lazily loaded routes. Remount via `key` on navigation to clear a prior failure. */
export function RouteBoundary({ children }: { children: ReactNode }) {
  return (
    <RouteErrorBoundary>
      <Suspense fallback={<RouteLoading />}>{children}</Suspense>
    </RouteErrorBoundary>
  );
}
