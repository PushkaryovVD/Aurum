import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as investments from "@/api/investments";

const invalidate = (client: ReturnType<typeof useQueryClient>) => {
  client.invalidateQueries({ queryKey: ["investments"] });
  client.invalidateQueries({ queryKey: ["accounts"] });
  client.invalidateQueries({ queryKey: ["transactions"] });
  client.invalidateQueries({ queryKey: ["dashboard-summary"] });
  client.invalidateQueries({ queryKey: ["cash-flow"] });
  client.invalidateQueries({ queryKey: ["net-worth-summary"] });
};

export const useInvestmentPortfolios = () => useQuery({ queryKey: ["investments", "portfolios"], queryFn: investments.fetchInvestmentPortfolios });
export const useInvestmentPositions = () => useQuery({ queryKey: ["investments", "positions"], queryFn: investments.fetchInvestmentPositions });

function mutation<T>(fn: (body: T) => Promise<unknown>) {
  const client = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => invalidate(client) });
}

export const useCreateInvestmentPortfolio = () => mutation(investments.createInvestmentPortfolio);
export const useCreateSecurity = () => mutation<object>(investments.createSecurity);
export const useCreateSecurityTrade = () => mutation<{ assetId: number; body: object }>(({ assetId, body }) => investments.createSecurityTrade(assetId, body));
export const useCreateSecurityDividend = () => mutation<{ assetId: number; body: object }>(({ assetId, body }) => investments.createSecurityDividend(assetId, body));
export const useSetSecurityPrice = () => mutation<{ assetId: number; body: object }>(({ assetId, body }) => investments.setSecurityPrice(assetId, body));
export const useDeleteSecurityTrade = () => mutation<number>(investments.deleteSecurityTrade);
export const useDeleteSecurityDividend = () => mutation<number>(investments.deleteSecurityDividend);
