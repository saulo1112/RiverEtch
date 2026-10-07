import { CASE_COPY } from "../content.ts";
import { rampGradientCss } from "../ramp.ts";

/**
 * Right panel: the river's NDTI scale (a relative index, low to high) and the cloud / no-data
 * swatch.
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
        <span>{CASE_COPY.legendHigh}</span>
      </p>
      <p className="case-legend__nodata">
        <span className="case-hatch case-legend__swatch" aria-hidden="true" />
        {CASE_COPY.noData}
      </p>
    </aside>
  );
}
