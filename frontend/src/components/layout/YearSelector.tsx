import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface YearDropdownProps {
  years: number[];
  year: number;
  onChange: (year: number) => void;
}

/** Compact single-year dropdown, most recent year first. Shared building
 * block behind both YearSelector and YearRangeSelector below. */
function YearDropdown({ years, year, onChange }: YearDropdownProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const sortedYears = [...years].sort((a, b) => b - a);

  useEffect(() => {
    if (!open) return;
    function handlePointerDown(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="flex min-h-11 items-center gap-1.5 rounded-lg border border-border bg-surface-1 px-3 text-sm font-medium text-text-primary transition-colors hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
      >
        {year}
        <ChevronDown size={14} className={cn("text-text-muted transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <ul
          role="listbox"
          className="absolute right-0 top-full z-20 mt-1.5 max-h-64 w-24 overflow-y-auto rounded-lg border border-border bg-surface-1 py-1 shadow-lg"
        >
          {sortedYears.map((value) => {
            const active = value === year;
            return (
              <li key={value}>
                <button
                  type="button"
                  role="option"
                  aria-selected={active}
                  onClick={() => {
                    onChange(value);
                    setOpen(false);
                  }}
                  className={cn(
                    "block min-h-11 w-full px-3 py-2 text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus",
                    active ? "bg-surface-2 font-semibold text-text-primary" : "text-text-secondary hover:bg-surface-2"
                  )}
                >
                  {value}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

/** Sits to the right of MonthSelector instead of competing with it as a
 * second row of pills. */
export function YearSelector(props: YearDropdownProps) {
  return <YearDropdown {...props} />;
}

interface YearRangeSelectorProps {
  years: number[];
  fromYear: number;
  toYear: number;
  onChange: (range: { fromYear: number; toYear: number }) => void;
}

/** Two year dropdowns for picking an arbitrary "from year – to year" span
 * (CashFlow/Reports "custom" range preset). Keeps fromYear <= toYear by
 * dragging the other bound along instead of allowing an inverted range. */
export function YearRangeSelector({ years, fromYear, toYear, onChange }: YearRangeSelectorProps) {
  return (
    <div className="flex shrink-0 items-center gap-1.5">
      <YearDropdown years={years} year={fromYear} onChange={(value) => onChange({ fromYear: value, toYear: Math.max(toYear, value) })} />
      <span className="text-sm text-text-muted">–</span>
      <YearDropdown years={years} year={toYear} onChange={(value) => onChange({ fromYear: Math.min(fromYear, value), toYear: value })} />
    </div>
  );
}
