import { CASE_COPY } from "../content.ts";
import type { LayerMode } from "../map.ts";
import { rampGradientCss } from "../ramp.ts";

/** Props of {@link Legend}. */
export interface LegendProps {
  /** What the river shows. */
  readonly mode: LayerMode;
}

/**
 * Right panel: the map's key. The water's color is each pixel's NDTI, a relative index (low to
 * high within this reach's passes); hatched pixels were unusable on the pass; the amber outline is
 * the gauge's window.
 *
 * @returns The legend panel.
 */
export function Legend({ mode }: LegendProps) {
  return (
    <aside
      className="case-panel case-legend case-glass"
      data-frame=""
      aria-labelledby="case-legend-title"
    >
      <h2 className="case-legend__title" id="case-legend-title">
        {mode === "photo" ? CASE_COPY.legendPhoto : CASE_COPY.legendTitle}
      </h2>
      {mode === "photo" ? (
        <p className="case-legend__photo">{CASE_COPY.legendPhotoNote}</p>
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
        {mode === "ndti" ? (
          <li className="case-legend__nodata">
            <span className="case-hatch case-legend__swatch" aria-hidden="true" />
            {CASE_COPY.noData}
          </li>
        ) : null}
        <li className="case-legend__nodata">
          <span className="case-legend__swatch case-legend__swatch--window" aria-hidden="true" />
          {CASE_COPY.window}
        </li>
      </ul>
    </aside>
  );
}
