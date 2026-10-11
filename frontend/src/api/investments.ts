import { api } from "@/api/client";
import type { InvestmentPortfolio, SecurityPosition } from "@/types";

export interface TradernetStatus { configured: boolean; mode: "read_only" }
export interface TradernetAccount { currency: string; available_funds: string; exchange_rate: string | null; forecast_in: string | null; forecast_out: string | null }
export interface TradernetPosition { external_position_id: string | null; ticker: string; name: string; currency: string; quantity: string; market_price: string | null; market_value: string | null; book_price: string | null; unrealized_profit: string | null }
export interface TradernetSnapshot { fetched_at: string; accounts: TradernetAccount[]; positions: TradernetPosition[] }

export const fetchInvestmentPortfolios = () => api.get<InvestmentPortfolio[]>("/investments/portfolios");
export const fetchInvestmentPositions = () => api.get<SecurityPosition[]>("/investments/positions");
export const createInvestmentPortfolio = (body: { name: string; account_id: number }) =>
  api.post<InvestmentPortfolio>("/investments/portfolios", body);
export const fetchTradernetStatus = () => api.get<TradernetStatus>("/investments/tradernet/status");
export const fetchTradernetPortfolio = () => api.get<TradernetSnapshot>("/investments/tradernet/portfolio");
export const createSecurity = (body: object) => api.post<SecurityPosition>("/investments/securities", body);
export const createSecurityTrade = (assetId: number, body: object) =>
  api.post<SecurityPosition>(`/investments/securities/${assetId}/trades`, body);
export const createSecurityDividend = (assetId: number, body: object) =>
  api.post<SecurityPosition>(`/investments/securities/${assetId}/dividends`, body);
export const setSecurityPrice = (assetId: number, body: object) =>
  api.put<SecurityPosition>(`/investments/securities/${assetId}/price`, body);
export const deleteSecurityTrade = (id: number) => api.delete<SecurityPosition>(`/investments/trades/${id}`);
export const deleteSecurityDividend = (id: number) => api.delete<SecurityPosition>(`/investments/dividends/${id}`);
