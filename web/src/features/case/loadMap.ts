// Loads the case map module (MapLibre and its CSS, in their own chunk) once. Calling it early, e.g.
// when the pointer reaches "Explore the case", prefetches the chunk.

type CaseMapModule = typeof import("./map.ts");

let pending: Promise<CaseMapModule> | null = null;

/**
 * Loads the case map module, at most once (a failed load can be retried).
 *
 * @returns The module, with `createCaseMap`.
 */
export function loadCaseMap(): Promise<CaseMapModule> {
  pending ??= import("./map.ts").catch((error: unknown) => {
    pending = null;
    throw error;
  });
  return pending;
}
