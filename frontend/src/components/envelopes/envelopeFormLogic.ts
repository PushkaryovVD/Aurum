type EnvelopeErrorLike = { status?: number; message?: string };

function parseCents(value: string): bigint | null {
  const normalized = value.trim().replace(",", ".");
  const match = /^(-?)(\d+)(?:\.(\d{0,2}))?$/.exec(normalized);
  if (!match) return null;
  const [, sign, whole, fraction = ""] = match;
  const cents = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"));
  return sign === "-" ? -cents : cents;
}

function formatCents(cents: bigint): string {
  const sign = cents < 0n ? "-" : "";
  const absolute = cents < 0n ? -cents : cents;
  return `${sign}${absolute / 100n}.${(absolute % 100n).toString().padStart(2, "0")}`;
}

export function allocationLimit(
  currentAssigned: string,
  availableToAssign: string,
  requested?: string
): string | null {
  const current = parseCents(currentAssigned);
  const available = parseCents(availableToAssign);
  if (current === null || available === null) return null;
  const limit = current + (available > 0n ? available : 0n);
  if (requested === undefined) return formatCents(limit);
  const desired = parseCents(requested);
  if (desired === null) return null;
  return formatCents(desired > limit ? limit : desired);
}

export function envelopeProgressPercent(available: string, planned: string): number {
  const availableCents = parseCents(available);
  const plannedCents = parseCents(planned);
  if (availableCents === null || plannedCents === null || plannedCents <= 0n || availableCents <= 0n) return 0;
  const percent = (availableCents * 100n) / plannedCents;
  return Number(percent > 100n ? 100n : percent);
}

export function moveValidationKey(
  amount: string,
  sourceAssigned: string,
  fromCategoryId: number,
  toCategoryId: number
): "envelope.move.invalidAmount" | "envelope.move.sameCategory" | "envelope.move.tooMuch" | null {
  const value = parseCents(amount);
  const source = parseCents(sourceAssigned);
  if (value === null || value <= 0n) return "envelope.move.invalidAmount";
  if (fromCategoryId === toCategoryId) return "envelope.move.sameCategory";
  if (source === null || value > source) return "envelope.move.tooMuch";
  return null;
}

export function envelopeErrorKey(
  error: EnvelopeErrorLike
): "envelope.error.closed" | "envelope.error.available" | "envelope.error.save" {
  const message = error.message?.toLowerCase() ?? "";
  if (error.status === 409 || message.includes("closed")) return "envelope.error.closed";
  if (message.includes("available to assign") || message.includes("allocation exceeds")) {
    return "envelope.error.available";
  }
  return "envelope.error.save";
}
