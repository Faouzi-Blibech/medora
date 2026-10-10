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
  unknown_drug: "pharmacy.errUnknownDrug",
};

/** Where the call was made: `conflict` is a prescription version clash for "rx" and a duplicate drug for "drug". */
export type PharmacyErrorContext = "rx" | "drug";

/** The key for a pharmacy error code, or null when `err` is not one. */
export function pharmacyErrorKey(err: unknown, context: PharmacyErrorContext = "rx"): Key | null {
  if (!(err instanceof ApiError)) return null;
  if (context === "drug" && err.code === "conflict") return "pharmacy.errDrugDuplicate";
  return BY_CODE[err.code] ?? null;
}

/** pharmacyErrorKey, else the shared mapping (server unreachable, 403, 404, 422…). */
export function describePharmacyError(err: unknown, context: PharmacyErrorContext = "rx"): Key {
  return pharmacyErrorKey(err, context) ?? describeError(err).key;
}
