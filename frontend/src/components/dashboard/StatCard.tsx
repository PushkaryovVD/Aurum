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
      <p className="text-sm font-medium text-text-secondary">{label}</p>
      <p className={cn("mt-3 break-words text-xl font-semibold leading-tight tracking-tight tabular-nums [overflow-wrap:anywhere] sm:text-[28px]", TONE_CLASSES[tone])}>
        {value}
      </p>
      <p className="mt-2 text-xs leading-5 text-text-muted">{caption}</p>
    </Card>
  );
}
