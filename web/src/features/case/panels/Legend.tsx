import { CASE_COPY } from "../content.ts";
import { rampGradientCss } from "../ramp.ts";

/**
 * Right panel: the map's key. The water's color is each pixel's NDTI, a relative index (low to
 * high within this reach's passes); hatched pixels were unusable on the pass; the dashed outlines
 * are the sub-reaches a record measures and the amber one the gauge's window.
 *
 * @returns The legend panel.
 */
export function Legend() {
  return (
    <aside className="case-panel case-legend case-glass" aria-labelledby="case-legend-title">
      <h2 className="case-legend__title" id="case-legend-title">
        {CASE_COPY.legendTitle}
      </h2>
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
      <ul className="case-legend__keys">
        <li className="case-legend__nodata">
          <span className="case-hatch case-legend__swatch" aria-hidden="true" />
          {CASE_COPY.noData}
        </li>
        <li className="case-legend__nodata">
          <span className="case-legend__swatch case-legend__swatch--parts" aria-hidden="true" />
          {CASE_COPY.parts}
        </li>
        <li className="case-legend__nodata">
          <span className="case-legend__swatch case-legend__swatch--window" aria-hidden="true" />
          {CASE_COPY.window}
        </li>
      </ul>
    </aside>
  );
}
