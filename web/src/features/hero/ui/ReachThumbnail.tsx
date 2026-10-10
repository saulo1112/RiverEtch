import { useMemo } from "react";

import { REFERENCE_REACH } from "../../case/reachGeometry.ts";
import { reachThumbnailPath, type ThumbnailBox } from "./thumbnail.ts";

/** Props of {@link ReachThumbnail}. */
export interface ReachThumbnailProps {
  /** View box and margin of the drawing. */
  readonly box: ThumbnailBox;
  /** Class of the `<svg>`. */
  readonly className?: string;
}

/**
 * The reference reach's outline as a line, north up, drawn from the same geometry as the case map.
 * Decorative: the card around it names the case.
 *
 * @returns The outline.
 */
export function ReachThumbnail({ box, className }: ReachThumbnailProps) {
  const path = useMemo(() => reachThumbnailPath(REFERENCE_REACH.geometry.coordinates, box), [box]);
  return (
    <svg
      className={className}
      viewBox={`0 0 ${String(box.width)} ${String(box.height)}`}
      preserveAspectRatio="xMidYMid meet"
      aria-hidden="true"
      focusable="false"
    >
      <path d={path} />
    </svg>
  );
}
