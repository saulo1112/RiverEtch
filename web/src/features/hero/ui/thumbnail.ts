// SVG outline of a river reach for the case cards, drawn from the same geometry the case map uses.
import type { LngLat } from "../../reaches/types.ts";

/** Size of the thumbnail's view box, in SVG units. */
export interface ThumbnailBox {
  /** View box width. */
  readonly width: number;
  /** View box height. */
  readonly height: number;
  /** Margin kept free on every side. */
  readonly padding: number;
}

/**
 * Projects a line of `[lng, lat]` points into an SVG path that fits the box, north up. Longitudes
 * shrink by the cosine of the middle latitude (a local equirectangular projection, true to shape at
 * reach scale) and both axes share one scale, centred in the box.
 *
 * @param coordinates - The line, in GeoJSON order.
 * @param box - View box size and margin.
 * @returns An SVG path (`M x,y L x,y …`, one decimal), or "" for fewer than two points.
 */
export function reachThumbnailPath(coordinates: readonly LngLat[], box: ThumbnailBox): string {
  if (coordinates.length < 2) {
    return "";
  }
  let minLng = Number.POSITIVE_INFINITY;
  let maxLng = Number.NEGATIVE_INFINITY;
  let minLat = Number.POSITIVE_INFINITY;
  let maxLat = Number.NEGATIVE_INFINITY;
  for (const [lng, lat] of coordinates) {
    minLng = Math.min(minLng, lng);
    maxLng = Math.max(maxLng, lng);
    minLat = Math.min(minLat, lat);
    maxLat = Math.max(maxLat, lat);
  }
  const xScale = Math.cos((((minLat + maxLat) / 2) * Math.PI) / 180);
  const spanX = (maxLng - minLng) * xScale;
  const spanY = maxLat - minLat;
  const innerWidth = Math.max(0, box.width - 2 * box.padding);
  const innerHeight = Math.max(0, box.height - 2 * box.padding);
  const scale = Math.min(
    spanX > 0 ? innerWidth / spanX : Number.POSITIVE_INFINITY,
    spanY > 0 ? innerHeight / spanY : Number.POSITIVE_INFINITY,
  );
  // A single repeated point has no extent: draw it at the centre.
  const unit = Number.isFinite(scale) ? scale : 0;
  const offsetX = (box.width - spanX * unit) / 2;
  const offsetY = (box.height - spanY * unit) / 2;
  const round = (value: number) => (Math.round(value * 10) / 10).toString();

  return coordinates
    .map(([lng, lat], index) => {
      const x = offsetX + (lng - minLng) * xScale * unit;
      const y = offsetY + (maxLat - lat) * unit;
      return `${index === 0 ? "M" : "L"}${round(x)},${round(y)}`;
    })
    .join(" ");
}
