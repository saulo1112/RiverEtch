// Coordinates typed by an analyst, for the reading spot: WGS 84 (EPSG:4326) latitude and longitude
// in decimal degrees, as GPS and Google Maps give them (the map's own system, so nothing is
// converted). A value may carry a degree sign and a hemisphere letter ("29.85° N", "89.99 W"), and a
// pair may be pasted at once ("29.85, -89.99", latitude first, as Google Maps copies it).

/** A point in WGS 84, decimal degrees. */
export interface LatLon {
  readonly lat: number;
  readonly lon: number;
}

// One value: a signed decimal, an optional degree sign, an optional hemisphere letter.
const VALUE = /^\s*([+-]?\d+(?:[.,]\d+)?)\s*°?\s*([NSEWnsew])?\s*$/;

/**
 * One coordinate as typed.
 *
 * @param text - E.g. "29.855", "-89.997", "29.855° N" or "89.997 W".
 * @param axis - Latitude (N/S) or longitude (E/W).
 * @returns The value in decimal degrees (null: not a coordinate of that axis, or out of range).
 */
export function parseCoordinate(text: string, axis: "lat" | "lon"): number | null {
  const match = VALUE.exec(text);
  if (match === null) {
    return null;
  }
  const [, number = "", letter = ""] = match;
  let value = Number(number.replace(",", "."));
  const hemisphere = letter.toUpperCase();
  if (hemisphere !== "") {
    const fits = axis === "lat" ? "NS".includes(hemisphere) : "EW".includes(hemisphere);
    if (!fits || value < 0) {
      return null;
    }
    value = hemisphere === "S" || hemisphere === "W" ? -value : value;
  }
  const limit = axis === "lat" ? 90 : 180;
  return Number.isFinite(value) && Math.abs(value) <= limit ? value : null;
}

/**
 * A latitude and longitude pasted together, latitude first ("29.85, -89.99" or "29.85 N 89.99 W").
 *
 * @param text - The pasted text.
 * @returns The point (null: not a pair).
 */
export function parsePair(text: string): LatLon | null {
  const parts = text
    .trim()
    .split(/\s*[,;]\s*|\s+(?=[+-]?\d)/)
    .filter((p) => p !== "");
  if (parts.length !== 2) {
    return null;
  }
  const lat = parseCoordinate(parts[0] ?? "", "lat");
  const lon = parseCoordinate(parts[1] ?? "", "lon");
  return lat === null || lon === null ? null : { lat, lon };
}

/**
 * A point as the panel writes it: five decimals (about a metre), a true minus sign.
 *
 * @param point - The point.
 * @returns E.g. "29.85512, −89.99731".
 */
export function formatLatLon(point: LatLon): string {
  const one = (v: number) => v.toFixed(5).replace("-", "−");
  return `${one(point.lat)}, ${one(point.lon)}`;
}
