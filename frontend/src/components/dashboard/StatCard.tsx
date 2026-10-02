import { Card } from "@/components/ui/Card";
import { cn } from "@/lib/utils";

interface StatCardProps {
  label: string;
  value: string;
  caption: string;
  tone?: "default" | "success" | "danger";
}

const TONE_CLASSES: Record<NonNullable<StatCardProps["tone"]>, string> = {
  default: "text-text-primary",
  success: "text-success",
  danger: "text-danger",
};

export function StatCard({ label, value, caption, tone = "default" }: StatCardProps) {
  return (
    <Card className="overflow-hidden p-card">
      <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">{label}</p>
      <p className={cn("mt-1.5 truncate text-xl font-semibold tabular-nums sm:text-[28px]", TONE_CLASSES[tone])}>
        {value}
      </p>
      <p className="mt-1 text-xs text-text-muted">{caption}</p>
    </Card>
  );
}
