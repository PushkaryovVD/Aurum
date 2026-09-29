import { ArrowRight, BookOpen } from "lucide-react";
import { Link } from "react-router-dom";
import { HELP_TOPICS, localize } from "@/lib/helpContent";
import { useTranslation } from "@/lib/i18n";

const COPY = {
  ru: {
    title: "Справка по Aurum",
    intro: "Короткие объяснения помогут выбрать нужный раздел и понять, что изменится после ваших действий.",
    contents: "Разделы справки",
    purpose: "Для чего",
    when: "Когда использовать",
    example: "Пример",
    misunderstanding: "Важно",
    open: "Открыть раздел",
  },
  en: {
    title: "Aurum guide",
    intro: "Short explanations help you choose the right area and understand what your actions will change.",
    contents: "Guide contents",
    purpose: "What it is for",
    when: "When to use it",
    example: "Example",
    misunderstanding: "Keep in mind",
    open: "Open this area",
  },
} as const;

export function HelpPage() {
  const { language } = useTranslation();
  const copy = COPY[language];

  return (
    <div className="mx-auto max-w-5xl space-y-6 overflow-x-hidden">
      <header className="space-y-2">
        <div className="flex items-center gap-2">
          <BookOpen size={22} className="shrink-0 text-text-secondary" />
          <h1 className="text-xl font-semibold text-text-primary sm:text-2xl">{copy.title}</h1>
        </div>
        <p className="max-w-3xl text-sm leading-6 text-text-secondary">{copy.intro}</p>
      </header>

      <nav aria-label={copy.contents} className="flex flex-wrap gap-2 pb-2">
        {HELP_TOPICS.map((topic) => (
          <a key={topic.id} href={`#${topic.id}`} className="min-h-11 shrink-0 rounded-full border border-border bg-surface-1 px-3 py-2.5 text-sm text-text-secondary hover:bg-surface-2">
            {localize(topic.title, language)}
          </a>
        ))}
      </nav>

      <div className="grid gap-4 md:grid-cols-2">
        {HELP_TOPICS.map((topic) => (
          <article id={topic.id} key={topic.id} className="min-w-0 scroll-mt-4 rounded-xl border border-border bg-surface-1 p-4 sm:p-5">
            <h2 className="text-lg font-semibold text-text-primary">{localize(topic.title, language)}</h2>
            <dl className="mt-4 space-y-3 text-sm leading-6">
              <div>
                <dt className="font-semibold text-text-primary">{copy.purpose}</dt>
                <dd className="text-text-secondary">{localize(topic.purpose, language)}</dd>
              </div>
              <div>
                <dt className="font-semibold text-text-primary">{copy.when}</dt>
                <dd className="text-text-secondary">{localize(topic.whenToUse, language)}</dd>
              </div>
              <div>
                <dt className="font-semibold text-text-primary">{copy.example}</dt>
                <dd className="break-words text-text-secondary">{localize(topic.example, language)}</dd>
              </div>
              <div className="rounded-lg bg-surface-2 p-3">
                <dt className="font-semibold text-text-primary">{copy.misunderstanding}</dt>
                <dd className="break-words text-text-secondary">{localize(topic.misunderstanding, language)}</dd>
              </div>
            </dl>
            <Link to={topic.path} className="mt-4 inline-flex min-h-11 items-center gap-1.5 py-2 text-sm font-medium text-text-primary underline-offset-4 hover:underline">
              {copy.open}<ArrowRight size={16} />
            </Link>
          </article>
        ))}
      </div>
    </div>
  );
}
