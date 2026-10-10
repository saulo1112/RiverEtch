// The featured case card's preview: the captured thumbnail of the case view once it exists and has
// loaded, the reach's outline otherwise, so the card never shows a broken image icon.

/** The thumbnail's files in `public/` (scripts/capture-case-thumbnail.mjs writes them). */
export const CASE_THUMBNAIL = {
  full: { path: "cases/magdalena-reference.webp", width: 1920, height: 960 },
  narrow: { path: "cases/magdalena-reference-960.webp", width: 960, height: 480 },
} as const;

/** Where the thumbnail image stands. */
export type PreviewStatus = "pending" | "loaded" | "failed";

/** What the card shows. */
export interface PreviewLayers {
  /** Render the `<img>` (transparent until it has loaded, over the outline). */
  readonly image: boolean;
  /** Show the reach's outline. */
  readonly fallback: boolean;
  /** Show the imagery's attribution (only over the real imagery). */
  readonly credit: boolean;
}

/**
 * Chooses the card's layers. Without the asset no image is requested; while it loads the outline
 * stays underneath; once loaded the outline goes and the attribution shows; if it fails, back to
 * the outline alone.
 *
 * @param assetAvailable - Whether the thumbnail files exist (checked at build time).
 * @param status - The image's loading state.
 * @returns The layers to show.
 */
export function previewLayers(assetAvailable: boolean, status: PreviewStatus): PreviewLayers {
  if (!assetAvailable || status === "failed") {
    return { image: false, fallback: true, credit: false };
  }
  if (status === "pending") {
    return { image: true, fallback: true, credit: false };
  }
  return { image: true, fallback: false, credit: true };
}

/**
 * The `srcset` for the thumbnail, both widths under a base URL.
 *
 * @param baseUrl - The app's base URL (`import.meta.env.BASE_URL`), ending in "/".
 * @returns E.g. "/cases/magdalena-reference-960.webp 960w, /cases/magdalena-reference.webp 1920w".
 */
export function thumbnailSrcSet(baseUrl: string): string {
  const { full, narrow } = CASE_THUMBNAIL;
  return `${baseUrl}${narrow.path} ${String(narrow.width)}w, ${baseUrl}${full.path} ${String(full.width)}w`;
}
