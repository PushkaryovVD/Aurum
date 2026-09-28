import { api } from "@/api/client";
import type {
  EnvelopeAllocationInput,
  EnvelopeAuditEvent,
  EnvelopeFundInput,
  EnvelopeFundResult,
  EnvelopeMonth,
  EnvelopeMonthSummary,
  EnvelopeMoveInput,
  EnvelopeTemplate,
  EnvelopeTemplateInput,
} from "@/types";

const monthPath = (year: number, month: number) => `/envelopes/${year}/${month}`;

export const fetchEnvelopeMonths = () => api.get<EnvelopeMonthSummary[]>("/envelopes");
export const fetchEnvelopeMonth = (year: number, month: number) => api.get<EnvelopeMonth>(monthPath(year, month));
export const openEnvelopeMonth = (year: number, month: number) => api.post<EnvelopeMonth>(`${monthPath(year, month)}/open`, {});
export const setEnvelopeAllocation = (year: number, month: number, categoryId: number, input: EnvelopeAllocationInput) =>
  api.put<EnvelopeMonth>(`${monthPath(year, month)}/allocations/${categoryId}`, input);
export const deleteEnvelopeAllocation = (year: number, month: number, categoryId: number) =>
  api.delete<EnvelopeMonth>(`${monthPath(year, month)}/allocations/${categoryId}`);
export const moveEnvelope = (year: number, month: number, input: EnvelopeMoveInput) =>
  api.post<EnvelopeMonth>(`${monthPath(year, month)}/moves`, input);
export const closeEnvelopeMonth = (year: number, month: number) => api.post<EnvelopeMonth>(`${monthPath(year, month)}/close`, {});
export const reopenEnvelopeMonth = (year: number, month: number) => api.post<EnvelopeMonth>(`${monthPath(year, month)}/reopen`, {});
export const fetchEnvelopeAudit = (year: number, month: number) => api.get<EnvelopeAuditEvent[]>(`${monthPath(year, month)}/audit`);
export const fetchEnvelopeTemplates = () => api.get<EnvelopeTemplate[]>("/envelopes/templates");
export const createEnvelopeTemplate = (input: EnvelopeTemplateInput) => api.post<EnvelopeTemplate>("/envelopes/templates", input);
export const updateEnvelopeTemplate = (id: number, input: EnvelopeTemplateInput) => api.patch<EnvelopeTemplate>(`/envelopes/templates/${id}`, input);
export const deleteEnvelopeTemplate = (id: number) => api.delete<void>(`/envelopes/templates/${id}`);
export const applyEnvelopeTemplate = (year: number, month: number, templateId: number) =>
  api.post<EnvelopeMonth>(`${monthPath(year, month)}/apply-template/${templateId}`, {});
export const fundEnvelopeMonth = (year: number, month: number, input: EnvelopeFundInput) =>
  api.post<EnvelopeFundResult>(`${monthPath(year, month)}/fund`, input);
export const fundNextEnvelopeMonth = (year: number, month: number) =>
  api.post<EnvelopeFundResult>(`${monthPath(year, month)}/fund-next-month`, {});
