import { ArrowLeft, Building2, FileSpreadsheet, FileText, Landmark, type LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { IMPORT_OPTIONS, type ImportOptionId } from "@/lib/importOptions";
import { useTranslation } from "@/lib/i18n";

const OPTION_ICONS: Record<ImportOptionId, LucideIcon> = {
  kaspi: Landmark,
  "freedom-bank": Building2,
  tradernet: FileSpreadsheet,
  csv: FileText,
};

export function ImportCenterPage() {
  const { t } = useTranslation();

  return (
    <div className="space-y-5">
      <Link
        to="/transactions"
        className="inline-flex items-center gap-1 text-sm text-text-muted hover:text-text-primary"
      >
        <ArrowLeft size={16} />
        {t("common.back")}
      </Link>

      <div>
        <h1 className="text-lg font-semibold text-text-primary">{t("importHub.title")}</h1>
        <p className="mt-1 text-sm text-text-secondary">{t("importHub.subtitle")}</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {IMPORT_OPTIONS.map((option) => {
          const Icon = OPTION_ICONS[option.id];
          return (
            <Link key={option.id} to={option.to} className="group block focus:outline-none">
              <Card className="h-full transition-colors group-hover:bg-surface-2 group-focus-visible:ring-2 group-focus-visible:ring-accent">
                <CardHeader>
                  <div className="flex items-start gap-3">
                    <div className="rounded-lg bg-surface-2 p-2 text-text-primary">
                      <Icon size={20} />
                    </div>
                    <div>
                      <CardTitle>{t(option.titleKey)}</CardTitle>
                      <p className="mt-1 text-xs font-medium text-text-muted">{t(option.formatKey)}</p>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-text-secondary">{t(option.descriptionKey)}</p>
                  <p className="mt-4 text-sm font-medium text-accent">{t("importHub.open")}</p>
                </CardContent>
              </Card>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
