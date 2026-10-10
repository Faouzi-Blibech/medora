// Pharmacy error codes (spec §5) → localized message keys. Only for pharmacy calls: `conflict` and
// `bad_status` mean other things on the accounts screens, which keep lib/accountsUi.ts.
import type { Key } from "@/i18n/messages";
import { describeError } from "./accountsUi";
import { ApiError } from "./api";

const BY_CODE: Partial<Record<string, Key>> = {
  override_required: "pharmacy.errOverrideRequired",
  ack_required: "pharmacy.errAckRequired",
  bad_status: "pharmacy.errBadStatus",
  conflict: "pharmacy.errRxConflict",
};

/** The key for a pharmacy error code, or null when `err` is not one. */
export function pharmacyErrorKey(err: unknown): Key | null {
  return err instanceof ApiError ? (BY_CODE[err.code] ?? null) : null;
}

/** pharmacyErrorKey, else the shared mapping (server unreachable, 403, 404, 422…). */
export function describePharmacyError(err: unknown): Key {
  return pharmacyErrorKey(err) ?? describeError(err).key;
}
