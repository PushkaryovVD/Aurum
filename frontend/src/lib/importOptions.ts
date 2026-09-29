import type { TranslationKey } from "@/lib/i18n";

export type ImportOptionId = "kaspi" | "freedom-bank" | "tradernet" | "csv";

export interface ImportOption {
  id: ImportOptionId;
  titleKey: TranslationKey;
  descriptionKey: TranslationKey;
  formatKey: TranslationKey;
  to: string;
}

/**
 * Keep this list aligned with backend/app/importers/registry.py. The PDF
 * readers identify their document content server-side; the entry point only
 * makes the supported formats discoverable before a file is selected.
 */
export const IMPORT_OPTIONS: readonly ImportOption[] = [
  {
    id: "kaspi",
    titleKey: "importHub.kaspi.title",
    descriptionKey: "importHub.kaspi.description",
    formatKey: "importHub.kaspi.format",
    to: "/transactions/import/statements?bank=kaspi",
  },
  {
    id: "freedom-bank",
    titleKey: "importHub.freedomBank.title",
    descriptionKey: "importHub.freedomBank.description",
    formatKey: "importHub.freedomBank.format",
    to: "/transactions/import/statements?bank=freedom-bank",
  },
  {
    id: "tradernet",
    titleKey: "importHub.tradernet.title",
    descriptionKey: "importHub.tradernet.description",
    formatKey: "importHub.tradernet.format",
    to: "/transactions/import/statements?bank=tradernet",
  },
  {
    id: "csv",
    titleKey: "importHub.csv.title",
    descriptionKey: "importHub.csv.description",
    formatKey: "importHub.csv.format",
    to: "/transactions/import/csv",
  },
];
