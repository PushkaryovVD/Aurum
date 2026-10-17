import { AlertThresholdsCard } from "@/components/settings/AlertThresholdsCard";
import { BackupCard } from "@/components/settings/BackupCard";
import { CurrencyCard } from "@/components/settings/CurrencyCard";
import { PreferencesCard } from "@/components/settings/PreferencesCard";
import { WorkspaceCard } from "@/components/settings/WorkspaceCard";
import { TelegramCard } from "@/components/settings/TelegramCard";
import { QueryStateNotice } from "@/components/ui/QueryStateNotice";
import { useAppSettings } from "@/hooks/useSettings";
import { t } from "@/lib/i18n";
import { queryDisplayState } from "@/lib/queryDisplayState";

export function SettingsPage() {
  // The version line is purely informational and simply stays hidden while
  // the request is pending. A failed request without data, however, leaves
  // the currency/threshold cards blank, so it is announced explicitly
  // (those cards also disable their inputs until settings are loaded).
  const { data: appSettings, isLoading, isError } = useAppSettings();
  const displayState = queryDisplayState(appSettings !== undefined, isLoading, isError);

  return (
    <div className="space-y-5">
      {/* A stale settings state is not worth a banner: the cached values are still the saved ones. */}
      {displayState === "unavailable" && (
        <QueryStateNotice state={displayState} unavailableText={t("settings.unavailable")} staleText="" />
      )}
      <PreferencesCard />
      <WorkspaceCard />
      <TelegramCard />
      <CurrencyCard />
      <AlertThresholdsCard />
      <BackupCard />
      {appSettings?.app_version && (
        <p className="text-center text-xs text-text-muted">
          {t("settings.version", { version: appSettings.app_version })}
        </p>
      )}
    </div>
  );
}
