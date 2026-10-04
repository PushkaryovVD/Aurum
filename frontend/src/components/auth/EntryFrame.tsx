import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, LockKeyhole } from "lucide-react";
import { useTranslation } from "@/lib/i18n";
import { useTheme, type Theme } from "@/lib/theme";

export const entryControl = "min-h-11 rounded-control border border-border bg-surface-1 px-3 text-text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:cursor-not-allowed disabled:opacity-50";
export const entryButton = `${entryControl} font-medium hover:bg-surface-2`;

export function EntryFrame({ children }: { children: ReactNode }) {
  const { t, language, setLanguage } = useTranslation();
  const { theme, setTheme } = useTheme();
  return (
    <div className="min-h-dvh bg-surface-0 text-text-primary">
      <header className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-6 sm:px-8">
        <Link to="/login" className="flex min-h-11 items-center gap-2 text-lg font-semibold tracking-tight focus-visible:outline-2 focus-visible:outline-focus"><span aria-hidden="true" className="flex h-8 w-8 items-center justify-center rounded-lg bg-text-primary text-surface-1">A</span>Aurum</Link>
        <div className="flex flex-wrap gap-3">
          <label className="flex items-center gap-2 text-xs text-text-secondary"><span className="sr-only">{t("entry.language")}</span><select aria-label={t("entry.language")} className={entryControl} value={language} onChange={(event) => setLanguage(event.target.value as "ru" | "en")}><option value="ru">RU</option><option value="en">EN</option></select></label>
          <label className="flex items-center gap-2 text-xs text-text-secondary"><span className="sr-only">{t("entry.theme")}</span><select aria-label={t("entry.theme")} className={entryControl} value={theme} onChange={(event) => setTheme(event.target.value as Theme)}><option value="system">{t("settings.themeSystem")}</option><option value="light">{t("settings.themeLight")}</option><option value="dark">{t("settings.themeDark")}</option></select></label>
        </div>
      </header>
      <main className="mx-auto grid w-full max-w-6xl min-w-0 gap-8 px-5 py-8 sm:px-8 sm:py-16 lg:grid-cols-[1fr_1fr] lg:items-start lg:gap-20">
        <section className="min-w-0 lg:pt-10">
          <p className="mb-5 text-xs font-medium uppercase tracking-[0.16em] text-text-muted">{t("entry.eyebrow")}</p>
          <h1 className="max-w-md text-3xl font-semibold leading-tight tracking-tight sm:text-5xl">{t("entry.tagline")}</h1>
          <p className="mt-5 max-w-md text-base leading-relaxed text-text-secondary">{t("entry.intro")}</p>
          <div className="mt-8 flex items-start gap-3 border-t border-border pt-5 text-xs leading-relaxed text-text-muted"><LockKeyhole size={18} className="shrink-0" aria-hidden="true"/><p className="max-w-sm">{t("entry.privacy")}</p></div>
        </section>
        <section aria-label={t("entry.title")} className="min-w-0 rounded-2xl border border-border bg-surface-1 p-5 shadow-card sm:p-8">{children}</section>
      </main>
    </div>
  );
}

export function AppReturnLink() {
  const { t } = useTranslation();
  return <Link to="/" className="mt-5 inline-flex min-h-11 items-center gap-2 text-sm text-text-secondary underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-focus">{t("entry.back")}<ArrowUpRight size={16} aria-hidden="true"/></Link>;
}
