// Pure validation of the request form (no React), so it can be unit-tested.

/** The form's fields. */
export type RequestField =
  "reachName" | "river" | "location" | "latitude" | "longitude" | "purpose" | "inSitu" | "notes";

/** What the form holds: raw text for every field. */
export type RequestValues = Readonly<Record<RequestField, string>>;

/** An error message per invalid field. */
export type RequestErrors = Partial<Record<RequestField, string>>;

/** Messages {@link validateRequest} uses (REQUEST.errors in content.ts). */
export interface RequestMessages {
  readonly reachName: string;
  readonly river: string;
  readonly latitudeNumber: string;
  readonly longitudeNumber: string;
  readonly latitudeMissing: string;
  readonly longitudeMissing: string;
  readonly purpose: string;
  readonly inSitu: string;
}

/** An empty form. */
export const EMPTY_REQUEST: RequestValues = {
  reachName: "",
  river: "",
  location: "",
  latitude: "",
  longitude: "",
  purpose: "",
  inSitu: "",
  notes: "",
};

const DECIMAL = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/;

/**
 * Reads a decimal coordinate within ±`limit` degrees. A true minus sign (−) counts as "-".
 *
 * @param text - What was typed.
 * @param limit - 90 for a latitude, 180 for a longitude.
 * @returns The number; null for an empty field; NaN when it is not a number in range.
 */
export function parseCoordinate(text: string, limit: number): number | null {
  const trimmed = text.trim().replace("−", "-");
  if (trimmed === "") {
    return null;
  }
  if (!DECIMAL.test(trimmed)) {
    return Number.NaN;
  }
  const value = Number(trimmed);
  return Math.abs(value) <= limit ? value : Number.NaN;
}

/**
 * Checks the request: a reach name and a river are required, as are a purpose from `purposes` and
 * an in-situ answer from `answers`; coordinates are optional, but both or neither, each a decimal
 * number in range.
 *
 * @param values - The form's raw values.
 * @param messages - The message for each kind of error.
 * @param purposes - Allowed purposes.
 * @param answers - Allowed in-situ answers.
 * @returns The errors, in field order; empty when the request is valid.
 */
export function validateRequest(
  values: RequestValues,
  messages: RequestMessages,
  purposes: readonly string[],
  answers: readonly string[],
): RequestErrors {
  const errors: RequestErrors = {};
  if (values.reachName.trim() === "") {
    errors.reachName = messages.reachName;
  }
  if (values.river.trim() === "") {
    errors.river = messages.river;
  }
  const latitude = parseCoordinate(values.latitude, 90);
  const longitude = parseCoordinate(values.longitude, 180);
  // A missing half is reported only against a valid other half.
  const valid = (value: number | null): value is number => value !== null && !Number.isNaN(value);
  if (Number.isNaN(latitude)) {
    errors.latitude = messages.latitudeNumber;
  } else if (latitude === null && valid(longitude)) {
    errors.latitude = messages.latitudeMissing;
  }
  if (Number.isNaN(longitude)) {
    errors.longitude = messages.longitudeNumber;
  } else if (longitude === null && valid(latitude)) {
    errors.longitude = messages.longitudeMissing;
  }
  if (!purposes.includes(values.purpose)) {
    errors.purpose = messages.purpose;
  }
  if (!answers.includes(values.inSitu)) {
    errors.inSitu = messages.inSitu;
  }
  return errors;
}
