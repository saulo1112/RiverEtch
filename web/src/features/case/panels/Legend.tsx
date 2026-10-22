import { CASE_COPY } from "../content.ts";
import { ALONG_CLASSES, CLASS_COLORS } from "../../reaches/along.ts";
import type { LayerMode } from "../map.ts";
import { rampGradientCss } from "../ramp.ts";

/** Props of {@link Legend}. */
export interface LegendProps {
  /** What the river shows. */
  readonly mode: LayerMode;
  /** The reach has no gauge: the outline is its estimate window. */
  readonly ungauged?: boolean;
  /** The reading spot can be dragged along the river. */
  readonly movable?: boolean;
  /** The reading spot has moved away from the start (the station is then marked on its own). */
  readonly moved?: boolean;
}

/**
 * Right panel: the map's key. The water's color is each pixel's NDTI, a relative index (low to
 * high within this reach's passes); hatched pixels were unusable on the pass; the amber outline is
 * the gauge's window, or the estimate window of a reach with no gauge.
 *
 * @returns The legend panel.
 */
export function Legend({ mode, ungauged = false, movable = false, moved = false }: LegendProps) {
  return (
    <aside
      className="case-panel case-legend case-glass"
      data-frame=""
      aria-labelledby="case-legend-title"
    >
      <h2 className="case-legend__title" id="case-legend-title">
        {mode === "photo"
          ? CASE_COPY.legendPhoto
          : mode === "class"
            ? CASE_COPY.legendClass
            : CASE_COPY.legendTitle}
      </h2>
      {mode === "photo" ? (
        <p className="case-legend__photo">{CASE_COPY.legendPhotoNote}</p>
      ) : mode === "class" ? (
        <ul className="case-legend__classes">
          {ALONG_CLASSES.map((c) => (
            <li key={c}>
              <span
                className="case-legend__class"
                style={{ background: CLASS_COLORS[c] }}
                aria-hidden="true"
              />
              {CASE_COPY.ungauged.classes[c]}
            </li>
          ))}
        </ul>
      ) : (
        <>
          <div
            className="case-legend__ramp"
            style={{ backgroundImage: rampGradientCss() }}
            aria-hidden="true"
          />
          <p className="case-legend__ends">
            <span>{CASE_COPY.legendLow}</span>
            <span className="case-legend__range">{CASE_COPY.legendRange}</span>
            <span>{CASE_COPY.legendHigh}</span>
          </p>
        </>
      )}
      <ul className="case-legend__keys">
        {mode === "ndti" || mode === "class" ? (
          <li className="case-legend__nodata">
            <span className="case-hatch case-legend__swatch" aria-hidden="true" />
            {mode === "class" ? CASE_COPY.legendClassNone : CASE_COPY.noData}
          </li>
        ) : null}
        <li className="case-legend__nodata">
          <span className="case-legend__swatch case-legend__swatch--window" aria-hidden="true" />
          {movable
            ? CASE_COPY.spot.legendSpot
            : ungauged
              ? CASE_COPY.ungauged.legendWindow
              : CASE_COPY.window}
        </li>
        {moved && !ungauged ? (
          <li className="case-legend__nodata">
            <span className="case-legend__swatch case-legend__swatch--station" aria-hidden="true" />
            {CASE_COPY.spot.legendStation}
          </li>
        ) : null}
      </ul>
    </aside>
  );
}
