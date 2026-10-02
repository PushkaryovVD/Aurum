import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

interface PageProps extends HTMLAttributes<HTMLDivElement> {}

interface PageHeaderProps extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}

export function Page({ className, ...props }: PageProps) {
  return <div data-slot="page" className={cn("min-w-0 space-y-section", className)} {...props} />;
}

export function PageHeader({ title, description, actions, className, ...props }: PageHeaderProps) {
  return (
    <header
      data-slot="page-header"
      className={cn("flex min-w-0 flex-col gap-4 sm:flex-row sm:items-end sm:justify-between", className)}
      {...props}
    >
      <div className="min-w-0">
        <h1 className="text-page-title font-semibold tracking-tight text-text-primary">{title}</h1>
        {description && <p className="mt-1 text-sm leading-6 text-text-secondary">{description}</p>}
      </div>
      {actions && <div className="flex min-w-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}
