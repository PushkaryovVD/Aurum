import { api } from "./client";

export interface TelegramStatus {
  configured: boolean;
  mini_app_configured: boolean;
  linked: boolean;
  username: string | null;
  /** Where bot quick entries and the Mini App currently land. */
  workspace_name?: string | null;
  account_name?: string | null;
  account_currency?: string | null;
}

export interface TelegramLinkCode {
  code: string;
  expires_in_seconds: number;
}

export const fetchTelegramStatus = () => api.get<TelegramStatus>("/telegram/status");
export const createTelegramLinkCode = () => api.post<TelegramLinkCode>("/telegram/link-code", {});
export const unlinkTelegram = () => api.delete<void>("/telegram/link");
