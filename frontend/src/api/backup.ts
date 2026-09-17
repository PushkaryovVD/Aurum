import { api } from "@/api/client";
import { t } from "@/lib/i18n";

export async function exportBackup(): Promise<void> {
  // Raw fetch (not api/client.ts's request()) because the response is a
  // file. The browser supplies the origin's Basic Auth credentials.
  const response = await fetch("/api/backup/export");
  if (!response.ok) {
    throw new Error(await response.text());
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const date = new Date().toISOString().slice(0, 10);

  const link = document.createElement("a");
  link.href = url;
  link.download = `aurum-backup-${date}.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export async function importBackup(file: File): Promise<void> {
  const text = await file.text();
  let payload: unknown;
  try {
    payload = JSON.parse(text);
  } catch {
    throw new Error(t("backup.invalidFile"));
  }
  await api.post<{ status: string }>("/backup/import", payload);
}
