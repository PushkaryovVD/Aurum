import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  applyEnvelopeTemplate,
  closeEnvelopeMonth,
  createEnvelopeTemplate,
  deleteEnvelopeAllocation,
  deleteEnvelopeTemplate,
  fetchEnvelopeAudit,
  fetchEnvelopeMonth,
  fetchEnvelopeMonths,
  fetchEnvelopeTemplates,
  fundEnvelopeMonth,
  fundNextEnvelopeMonth,
  moveEnvelope,
  openEnvelopeMonth,
  reopenEnvelopeMonth,
  setEnvelopeAllocation,
  updateEnvelopeTemplate,
} from "@/api/envelopes";
import type { EnvelopeAllocationInput, EnvelopeFundInput, EnvelopeMoveInput, EnvelopeTemplateInput } from "@/types";

export function previousMonth(year: number, month: number): { year: number; month: number } {
  return month === 1 ? { year: year - 1, month: 12 } : { year, month: month - 1 };
}

export function envelopeInvalidationKeys(year: number, month: number): readonly (readonly unknown[])[] {
  const previous = previousMonth(year, month);
  return [
    ["envelopes"],
    ["envelope-month", year, month],
    ["envelope-month", previous.year, previous.month],
    ["financial-alerts"],
  ];
}

function useInvalidateEnvelopeMonth(year: number, month: number) {
  const queryClient = useQueryClient();
  return () => {
    for (const queryKey of envelopeInvalidationKeys(year, month)) {
      queryClient.invalidateQueries({ queryKey });
    }
    // Rollover continuity can affect every later month, so invalidate the
    // complete month family in addition to the explicit contract keys above.
    queryClient.invalidateQueries({ queryKey: ["envelope-month"] });
    queryClient.invalidateQueries({ queryKey: ["envelope-audit", year, month] });
  };
}

export function useEnvelopeMonths() {
  return useQuery({ queryKey: ["envelopes"], queryFn: fetchEnvelopeMonths });
}

export function useEnvelopeMonth(year: number, month: number) {
  return useQuery({ queryKey: ["envelope-month", year, month], queryFn: () => fetchEnvelopeMonth(year, month) });
}

export function useOpenEnvelopeMonth(year: number, month: number) {
  const invalidate = useInvalidateEnvelopeMonth(year, month);
  return useMutation({ mutationFn: () => openEnvelopeMonth(year, month), onSuccess: invalidate });
}

export function useSetAllocation(year: number, month: number) {
  const invalidate = useInvalidateEnvelopeMonth(year, month);
  return useMutation({
    mutationFn: ({ categoryId, input }: { categoryId: number; input: EnvelopeAllocationInput }) =>
      setEnvelopeAllocation(year, month, categoryId, input),
    onSuccess: invalidate,
  });
}

export function useDeleteAllocation(year: number, month: number) {
  const invalidate = useInvalidateEnvelopeMonth(year, month);
  return useMutation({ mutationFn: (categoryId: number) => deleteEnvelopeAllocation(year, month, categoryId), onSuccess: invalidate });
}

export function useMoveEnvelope(year: number, month: number) {
  const invalidate = useInvalidateEnvelopeMonth(year, month);
  return useMutation({ mutationFn: (input: EnvelopeMoveInput) => moveEnvelope(year, month, input), onSuccess: invalidate });
}

export function useCloseMonth(year: number, month: number) {
  const invalidate = useInvalidateEnvelopeMonth(year, month);
  return useMutation({ mutationFn: () => closeEnvelopeMonth(year, month), onSuccess: invalidate });
}

export function useReopenMonth(year: number, month: number) {
  const invalidate = useInvalidateEnvelopeMonth(year, month);
  return useMutation({ mutationFn: () => reopenEnvelopeMonth(year, month), onSuccess: invalidate });
}

export function useTemplates() {
  return useQuery({ queryKey: ["envelope-templates"], queryFn: fetchEnvelopeTemplates });
}

export function useCreateTemplate() {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: (input: EnvelopeTemplateInput) => createEnvelopeTemplate(input), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["envelope-templates"] }) });
}

export function useUpdateTemplate() {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: ({ id, input }: { id: number; input: EnvelopeTemplateInput }) => updateEnvelopeTemplate(id, input), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["envelope-templates"] }) });
}

export function useDeleteTemplate() {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: deleteEnvelopeTemplate, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["envelope-templates"] }) });
}

export function useApplyTemplate(year: number, month: number) {
  const invalidate = useInvalidateEnvelopeMonth(year, month);
  return useMutation({ mutationFn: (templateId: number) => applyEnvelopeTemplate(year, month, templateId), onSuccess: invalidate });
}

export function useFund(year: number, month: number) {
  const invalidate = useInvalidateEnvelopeMonth(year, month);
  return useMutation({ mutationFn: (input: EnvelopeFundInput) => fundEnvelopeMonth(year, month, input), onSuccess: invalidate });
}

export function useFundNextMonth(year: number, month: number) {
  const invalidate = useInvalidateEnvelopeMonth(year, month);
  return useMutation({ mutationFn: () => fundNextEnvelopeMonth(year, month), onSuccess: invalidate });
}

export function useEnvelopeAudit(year: number, month: number, enabled = true) {
  return useQuery({ queryKey: ["envelope-audit", year, month], queryFn: () => fetchEnvelopeAudit(year, month), enabled });
}
