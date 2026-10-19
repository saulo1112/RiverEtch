import type { PassStats } from "../../reaches/analysis.ts";
import { CASE_COPY } from "../content.ts";
import { rampRgb } from "../ramp.ts";

/** Props of {@link PassStatsView}. */
export interface PassStatsViewProps {
  /** The selected pass's statistics (null while it loads). */
  readonly stats: PassStats | null;
}

// One 10 m pixel is 100 m².
const PIXEL_KM2 = 100 / 1e6;

function signed(v: number | null | undefined): string {
  if (typeof v !== "number") {
    return "–";
  }
  return `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(3)}`;
}

/**
 * The selected pass at a glance: how much of the corridor's water it saw, what it lost to cloud,
 * glint or missing data and the spread of its NDTI (the gauge's readings are on the water-quality
 * tab).
 *
 * @returns The statistics.
 */
export function PassStatsView({ stats }: PassStatsViewProps) {
  const { pass } = CASE_COPY;
  if (stats === null) {
    return <div className="case-pass" />;
  }
  const usableShare = stats.water === 0 ? 0 : stats.usable / stats.water;
  const peak = Math.max(1, ...stats.histogram);
  return (
    <div className="case-pass">
      <dl className="case-pass__tiles">
        <div>
          <dt>{pass.water}</dt>
          <dd>
            {(stats.water * PIXEL_KM2).toFixed(1)} <span>km²</span>
          </dd>
        </div>
        <div>
          <dt>{pass.usable}</dt>
          <dd>
            {(usableShare * 100).toFixed(0)} <span>%</span>
          </dd>
        </div>
        <div>
          <dt>{pass.clouded}</dt>
          <dd>
            {((1 - usableShare) * 100).toFixed(0)} <span>%</span>
          </dd>
        </div>
        <div className="case-pass__wide">
          <dt>{pass.percentiles}</dt>
          <dd className="case-pass__mono">
            {stats.percentiles === null ? "–" : stats.percentiles.map((v) => signed(v)).join(" · ")}
          </dd>
        </div>
      </dl>
      <figure className="case-pass__histogram">
        <figcaption>{pass.histogram}</figcaption>
        <div className="case-pass__bars" aria-hidden="true">
          {stats.histogram.map((n, k) => {
            const [r, g, b] = rampRgb((k + 0.5) / stats.histogram.length);
            return (
              <span
                key={k}
                style={{
                  height: `${((n / peak) * 100).toFixed(1)}%`,
                  background: `rgb(${String(r)} ${String(g)} ${String(b)})`,
                }}
              />
            );
          })}
        </div>
        <p className="case-pass__ends">
          <span>{CASE_COPY.legendLow}</span>
          <span>{CASE_COPY.legendHigh}</span>
        </p>
      </figure>
    </div>
  );
}
