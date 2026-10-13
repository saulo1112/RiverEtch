// A case card's preview: the captured view of the landed case once it exists and has loaded, the
// reach's outline otherwise, so the card never shows a broken image icon.

/** One size of a thumbnail. */
export interface ThumbnailFile {
  /** Path under `public/`. */
  readonly path: string;
  readonly width: number;
  readonly height: number;
}

/**
 * A case's thumbnail files in `public/cases/` (scripts/capture-case-thumbnail.mjs writes them).
 *
 * @param id - The case's id.
 * @returns The full and the narrow size.
 */
export function caseThumbnail(id: string): { full: ThumbnailFile; narrow: ThumbnailFile } {
  return {
    full: { path: `cases/${id}.webp`, width: 1920, height: 960 },
    narrow: { path: `cases/${id}-960.webp`, width: 960, height: 480 },
  };
}

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
 * The `srcset` for a case's thumbnail, both widths under a base URL.
 *
 * @param baseUrl - The app's base URL (`import.meta.env.BASE_URL`), ending in "/".
 * @param id - The case's id.
 * @returns E.g. "/cases/platte-louisville-960.webp 960w, /cases/platte-louisville.webp 1920w".
 */
export function thumbnailSrcSet(baseUrl: string, id: string): string {
  const { full, narrow } = caseThumbnail(id);
  return `${baseUrl}${narrow.path} ${String(narrow.width)}w, ${baseUrl}${full.path} ${String(full.width)}w`;
}
