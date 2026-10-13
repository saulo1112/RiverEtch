import { useId, useMemo } from "react";

import { NDTI_RAMP } from "../../case/ramp.ts";
import type { LngLat } from "../../reaches/types.ts";
import { reachThumbnailPath, type ThumbnailBox } from "./thumbnail.ts";

/** Props of {@link ReachThumbnail}. */
export interface ReachThumbnailProps {
  /** The reach's centreline, upstream first (`[lng, lat]`). */
  readonly coordinates: readonly LngLat[];
  /** View box and margin of the drawing. */
  readonly box: ThumbnailBox;
  /** Class of the `<svg>`. */
  readonly className?: string;
}

/**
 * A reach's centreline as a glowing line on the NDTI ramp, north up, drawn from the same geometry
 * as the case map. Decorative: the card around it names the case.
 *
 * @returns The outline.
 */
export function ReachThumbnail({ coordinates, box, className }: ReachThumbnailProps) {
  const gradientId = useId();
  const path = useMemo(() => reachThumbnailPath(coordinates, box), [coordinates, box]);
  return (
    <svg
      className={className}
      viewBox={`0 0 ${String(box.width)} ${String(box.height)}`}
      preserveAspectRatio="xMidYMid meet"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="0">
          {NDTI_RAMP.map((stop) => (
            <stop key={stop.at} offset={stop.at} stopColor={stop.color} />
          ))}
        </linearGradient>
      </defs>
      <path d={path} stroke={`url(#${gradientId})`} />
    </svg>
  );
}
