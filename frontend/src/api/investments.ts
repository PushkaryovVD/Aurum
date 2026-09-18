import { api } from "@/api/client";
import type { InvestmentPortfolio, SecurityPosition } from "@/types";

export const fetchInvestmentPortfolios = () => api.get<InvestmentPortfolio[]>("/investments/portfolios");
export const fetchInvestmentPositions = () => api.get<SecurityPosition[]>("/investments/positions");
export const createInvestmentPortfolio = (body: { name: string; account_id: number }) =>
  api.post<InvestmentPortfolio>("/investments/portfolios", body);
export const createSecurity = (body: object) => api.post<SecurityPosition>("/investments/securities", body);
export const createSecurityTrade = (assetId: number, body: object) =>
  api.post<SecurityPosition>(`/investments/securities/${assetId}/trades`, body);
export const createSecurityDividend = (assetId: number, body: object) =>
  api.post<SecurityPosition>(`/investments/securities/${assetId}/dividends`, body);
export const setSecurityPrice = (assetId: number, body: object) =>
  api.put<SecurityPosition>(`/investments/securities/${assetId}/price`, body);
export const deleteSecurityTrade = (id: number) => api.delete<SecurityPosition>(`/investments/trades/${id}`);
export const deleteSecurityDividend = (id: number) => api.delete<SecurityPosition>(`/investments/dividends/${id}`);
