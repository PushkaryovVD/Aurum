import { getMonthLabels } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import { cn } from "@/lib/utils";

interface MonthSelectorProps {
  month: number; // 1-12
  onChange: (month: number) => void;
}

export function MonthSelector({ month, onChange }: MonthSelectorProps) {
  const { language } = useTranslation();
  const monthLabels = getMonthLabels(language);

  return (
    <div className="flex gap-2 overflow-x-auto pb-1 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      {monthLabels.map((label, index) => {
        const value = index + 1;
        const active = value === month;
        return (
          <button
            key={label}
            type="button"
            onClick={() => onChange(value)}
            className={cn(
              "min-h-11 shrink-0 rounded-full border px-3.5 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus",
              active
                ? "border-series-6 bg-series-6 text-white"
                : "border-border bg-surface-1 text-text-secondary hover:bg-surface-2"
            )}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}
