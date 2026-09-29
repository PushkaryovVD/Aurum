import { useId, useState } from "react";
import { ChevronDown, CircleHelp } from "lucide-react";
import { getHelpTopic, localize, type HelpTopicId } from "@/lib/helpContent";
import { useTranslation } from "@/lib/i18n";
import { cn } from "@/lib/utils";

interface ContextualHelpProps {
  topicId: HelpTopicId;
  className?: string;
}

const LABELS = {
  ru: { show: "Как это работает", hide: "Скрыть подсказку", example: "Пример", note: "Важно" },
  en: { show: "How this works", hide: "Hide help", example: "Example", note: "Keep in mind" },
} as const;

export function ContextualHelp({ topicId, className }: ContextualHelpProps) {
  const { language } = useTranslation();
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const topic = getHelpTopic(topicId);
  const labels = LABELS[language];

  return (
    <section className={cn("rounded-xl border border-border bg-surface-1", className)} aria-label={localize(topic.title, language)}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
        className="flex min-h-11 w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm font-medium text-text-secondary hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-text-primary"
      >
        <CircleHelp size={18} className="shrink-0" />
        <span className="min-w-0 flex-1">{open ? labels.hide : labels.show}</span>
        <ChevronDown size={18} className={cn("shrink-0 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div id={panelId} className="space-y-2 border-t border-border px-3 py-3 text-sm leading-6 text-text-secondary">
          <p>{localize(topic.purpose, language)} {localize(topic.whenToUse, language)}</p>
          <p><strong className="font-semibold text-text-primary">{labels.example}:</strong> {localize(topic.example, language)}</p>
          <p><strong className="font-semibold text-text-primary">{labels.note}:</strong> {localize(topic.misunderstanding, language)}</p>
        </div>
      )}
    </section>
  );
}
