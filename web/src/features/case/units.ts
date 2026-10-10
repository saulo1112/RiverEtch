// Whether a case may show physical units (e.g. NTU). NDTI is a relative index: a value in physical
// units needs an in-situ calibration that passed. No case carries one yet, and the data contract
// has no such field: the check reads it defensively, so it switches on once the pipeline adds one.

/**
 * True only when `source.calibration.status` is exactly `"passed"`.
 *
 * @param source - A case, or any pipeline output, of unknown shape.
 * @returns Whether physical units may be shown.
 */
export function canShowPhysicalUnits(source: unknown): boolean {
  if (typeof source !== "object" || source === null || !("calibration" in source)) {
    return false;
  }
  const { calibration } = source;
  return (
    typeof calibration === "object" &&
    calibration !== null &&
    "status" in calibration &&
    calibration.status === "passed"
  );
}
