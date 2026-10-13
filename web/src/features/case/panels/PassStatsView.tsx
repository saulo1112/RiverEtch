import type { PassStats } from "../../reaches/analysis.ts";
import type { ContextReading, SeriesRow } from "../../reaches/types.ts";
import { CASE_COPY, formatReading } from "../content.ts";
import { rampRgb } from "../ramp.ts";

/** Props of {@link PassStatsView}. */
export interface PassStatsViewProps {
  /** The selected pass's statistics (null while it loads). */
  readonly stats: PassStats | null;
  /** The selected pass. */
  readonly row: SeriesRow | null;
  /** The gauge's own readings at the pass (`checks/context.csv`). */
  readonly context: readonly ContextReading[];
}

// One 10 m pixel is 100 m².
const PIXEL_KM2 = 100 / 1e6;

function signed(v: number | null | undefined): string {
  if (typeof v !== "number") {
    return "–";
  }
  return `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(3)}`;
}

// The gauge's readings at the pass: discharge, stage and, where it measures them, temperature,
// oxygen, conductance and nitrate (USGS values, not the satellite's).
function GaugeReadings({ context }: { readonly context: readonly ContextReading[] }) {
  const copy = CASE_COPY.context;
  const order = Object.keys(copy.names);
  const rank = (c: ContextReading) => {
    const k = order.indexOf(c.parameter);
    return k < 0 ? order.length : k;
  };
  const readings = [...context].sort((a, b) => rank(a) - rank(b));
  const provisional = context.some((c) => c.approval.toLowerCase() !== "approved");
  return (
    <section className="case-pass__gauge" aria-label={copy.title}>
      <p className="case-pass__gauge-title">
        <span className="case-file__gauge-dot" aria-hidden="true" />
        <span>
          {copy.title}
          {context.length === 0 ? null : (
            <span
              className="case-pass__approval"
              title={provisional ? copy.provisional : undefined}
            >
              {" "}
              · {provisional ? copy.provisionalShort : copy.approvedShort}
            </span>
          )}
        </span>
      </p>
      {context.length === 0 ? (
        <p className="case-pass__gauge-note">{copy.none}</p>
      ) : (
        <dl className="case-pass__readings">
          {readings.map((c) => (
            <div key={c.parameter}>
              <dt>{copy.names[c.parameter] ?? c.name}</dt>
              <dd>
                {formatReading(c.value)} <span>{c.unit}</span>
              </dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}

/**
 * The selected pass at a glance: how much of the corridor's water it saw, what it lost to cloud,
 * glint or missing data, the spread of its NDTI, the record's own medians and what the gauge
 * measured at the overpass.
 *
 * @returns The statistics.
 */
export function PassStatsView({ stats, row, context }: PassStatsViewProps) {
  const { pass } = CASE_COPY;
  if (stats === null) {
    return (
      <div className="case-pass">
        <div />
        <div />
        <GaugeReadings context={context} />
      </div>
    );
  }
  const usableShare = stats.water === 0 ? 0 : stats.usable / stats.water;
  const peak = Math.max(1, ...stats.histogram);
  const ndti = row?.indices.ndti;
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
        <div>
          <dt>{pass.percentiles}</dt>
          <dd className="case-pass__mono">
            {stats.percentiles === null ? "–" : stats.percentiles.map((v) => signed(v)).join(" · ")}
          </dd>
        </div>
        <div>
          <dt>{pass.medians}</dt>
          <dd className="case-pass__mono">
            {signed(ndti?.upstream)} · {signed(ndti?.downstream)}
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
      <GaugeReadings context={context} />
    </div>
  );
}
