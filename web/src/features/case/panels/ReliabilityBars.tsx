import { History, Satellite } from "lucide-react";

import { CASE_COPY } from "../content.ts";

/** Props of {@link ReliabilityBars}. */
export interface ReliabilityBarsProps {
  /** The satellite's locked-test error. */
  readonly satellite: number;
  /** The error of guessing the river's usual value, in the same unit. */
  readonly baseline: number;
  /** "%" (turbidity, MdSA) or "°C" (temperature, MAE). */
  readonly unit: "%" | "°C";
}

/**
 * The satellite's error beside the error of guessing the river's usual value, as two bars on one
 * scale, each labelled with its value (less is better). The bars are decoration for the eye; the
 * labels carry the numbers, and the two rows differ by their icon and words, not by colour alone.
 *
 * @returns The two rows.
 */
export function ReliabilityBars({ satellite, baseline, unit }: ReliabilityBarsProps) {
  const { reading, kinds } = CASE_COPY;
  const max = Math.max(satellite, baseline, Number.EPSILON);
  const format = (v: number) => (unit === "%" ? `${v.toFixed(1)} %` : `${v.toFixed(2)} °C`);
  const rows = [
    { id: "satellite", label: reading.satellite, kind: kinds.satellite, value: satellite },
    { id: "baseline", label: reading.baseline, kind: kinds.history, value: baseline },
  ] as const;
  return (
    <dl className="case-bars">
      {rows.map((r) => (
        <div key={r.id} className="case-bars__row" data-kind={r.id}>
          <dt className="case-bars__label">
            {r.id === "satellite" ? (
              <Satellite size={13} strokeWidth={1.9} aria-hidden="true" />
            ) : (
              <History size={13} strokeWidth={1.9} aria-hidden="true" />
            )}
            <span>{r.label}</span>
            <span className="case-visually-hidden"> ({r.kind})</span>
          </dt>
          <dd className="case-bars__value">{format(r.value)}</dd>
          <dd className="case-bars__track" aria-hidden="true">
            <span
              className="case-bars__bar"
              style={{ inlineSize: `${((r.value / max) * 100).toFixed(1)}%` }}
            />
          </dd>
        </div>
      ))}
    </dl>
  );
}
