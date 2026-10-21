import { Gauge, Satellite } from "lucide-react";
import type { CSSProperties } from "react";

import {
  classEdges,
  classSpan,
  isOutside,
  isUngauged,
  nearestThermal,
  sceneKey,
  thermalValidatedAt,
  turbidity,
} from "../../reaches/scene.ts";
import type { ReachData, SeriesRow } from "../../reaches/types.ts";
import {
  CASE_COPY,
  formatCelsius,
  formatDate,
  formatReading,
  formatValue,
  landsatName,
  LEVEL_LABELS,
} from "../content.ts";
import { leanOfTemperature, leanOfTurbidity, type Lean } from "../reading.ts";

const { reading, kinds } = CASE_COPY;

// Which way an estimate leans, in words ("" when there is no clear lean).
function leanText(lean: Lean): string {
  switch (lean.kind) {
    case "warm":
      return reading.leanWarm(lean.text);
    case "cold":
      return reading.leanCold(lean.text);
    case "high":
      return reading.leanHigh(lean.text);
    case "low":
      return reading.leanLow(lean.text);
    default:
      return "";
  }
}

const joined = (...parts: string[]) => parts.filter((p) => p !== "").join(" · ");

/** Props of {@link WaterQualityView}. */
export interface WaterQualityViewProps {
  readonly reach: ReachData;
  /** Index of the selected Sentinel-2 pass. */
  readonly selected: number;
}

const SPARK = { width: 120, height: 22, pad: 3 };

// A small line of the year's values with the selected one lit. It stretches to its box, so the
// lit point is a zero-length round-capped line with a non-scaling stroke: a dot at any width.
function Sparkline({
  values,
  selected,
  tone,
}: {
  readonly values: readonly (number | null)[];
  readonly selected: number | null;
  readonly tone: "sat" | "thermal" | "gauge";
}) {
  const finite = values.filter((v): v is number => v !== null);
  if (finite.length < 2) {
    return <svg className="case-quality__spark" aria-hidden="true" />;
  }
  const lo = Math.min(...finite);
  const hi = Math.max(...finite);
  const x = (k: number) =>
    SPARK.pad + (k / Math.max(1, values.length - 1)) * (SPARK.width - 2 * SPARK.pad);
  const y = (v: number) =>
    SPARK.pad + (1 - (v - lo) / (hi - lo || 1)) * (SPARK.height - 2 * SPARK.pad);
  const points = values
    .map((v, k) => (v === null ? null : `${x(k).toFixed(1)},${y(v).toFixed(1)}`))
    .filter((p): p is string => p !== null)
    .join(" ");
  const lit = selected === null ? null : values[selected];
  return (
    <svg
      className="case-quality__spark"
      data-tone={tone}
      viewBox={`0 0 ${String(SPARK.width)} ${String(SPARK.height)}`}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <polyline points={points} />
      {lit === null || lit === undefined || selected === null ? null : (
        <line
          className="case-quality__spark-dot"
          x1={x(selected)}
          x2={x(selected)}
          y1={y(lit)}
          y2={y(lit)}
        />
      )}
    </svg>
  );
}

interface Tile {
  readonly id: string;
  readonly title: string;
  readonly source: string;
  readonly value: string | null;
  readonly unit: string;
  readonly detail: string;
  /** A satellite estimate's level, or a gauge value's approval (Provisional, Approved). */
  readonly chip: string | null;
  readonly level?: string;
  readonly approval?: string;
  readonly foot: string;
  readonly spark: { values: readonly (number | null)[]; selected: number | null };
  readonly tone: "sat" | "thermal" | "gauge";
}

// An ungauged reach's tile: the pass's class, never a value; the sparkline steps between classes.
function classTile(reach: ReachData, row: SeriesRow, selected: number): Tile {
  const copy = CASE_COPY.quality;
  const { ungauged } = CASE_COPY;
  const estimate = turbidity(row);
  const cls = estimate?.fnuClass ?? null;
  const error = reach.card?.expectedError;
  const label = isOutside(reach) ? ungauged.outsideLabel : ungauged.label;
  return {
    id: "turbidity",
    title: ungauged.turbidity,
    source: `${copy.sentinel} · ${formatDate(row.date)}`,
    value: cls === null ? null : ungauged.classes[cls],
    unit: "",
    detail: cls === null ? (estimate?.abstainReason ?? label) : label,
    chip: LEVEL_LABELS[estimate?.level ?? "unvalidated"],
    level: estimate?.level ?? "unvalidated",
    foot: error === undefined ? "" : ungauged.agreement(error.classAgreement, error.n),
    spark: {
      values: reach.series.map((r) => {
        const c = turbidity(r)?.fnuClass;
        if (c == null) {
          return null;
        }
        const [low, high] = classSpan(c, classEdges(reach));
        return (low + high) / 2;
      }),
      selected,
    },
    tone: "sat",
  };
}

// A z-score as the tile writes it: one decimal, a true minus sign.
const zText = (z: number | null | undefined) =>
  z == null ? "–" : `${z < 0 ? "\u2212" : z > 0 ? "+" : ""}${Math.abs(z).toFixed(1)}`;

// A no-station reach's second satellite tile: the pass's NDTI against the reach's own earlier
// passes, as rule D0 judged it in the sealed record (unusual at 3 or more robust spreads), with
// the year's downstream z-scores as its line. Relative: no unit, no level.
function ownPastTile(reach: ReachData, row: SeriesRow, selected: number): Tile {
  const copy = CASE_COPY.quality;
  const z = row.indices.ndti.zScore;
  const signals = row.verdict?.signals ?? [];
  const strongest = signals
    .map((s) => (z === undefined ? null : (z[s as keyof typeof z] ?? null)))
    .filter((v): v is number => v !== null)
    .sort((a, b) => Math.abs(b) - Math.abs(a))[0];
  const value =
    z === undefined || row.verdict === undefined
      ? null
      : !row.verdict.anomalous
        ? copy.usual
        : (strongest ?? 0) < 0
          ? copy.low
          : copy.high;
  return {
    id: "own-past",
    title: copy.own,
    source: copy.ownSource,
    value,
    unit: "",
    detail: z === undefined ? copy.ownNone : copy.ownDetail(zText(z.upstream), zText(z.downstream)),
    chip: null,
    level: "none",
    foot: "",
    spark: {
      values: reach.series.map((r) => r.indices.ndti.zScore?.downstream ?? null),
      selected,
    },
    tone: "sat",
  };
}

function turbidityTile(reach: ReachData, row: SeriesRow, selected: number): Tile {
  if (isUngauged(reach)) {
    return classTile(reach, row, selected);
  }
  const copy = CASE_COPY.quality;
  const estimate = turbidity(row);
  const value = typeof estimate?.value === "number" ? estimate.value : null;
  const interval = estimate?.interval ?? null;
  const lock = reach.card?.metrics?.lockbox;
  return {
    id: "turbidity",
    title: copy.turbidity,
    source: `${copy.sentinel} · ${formatDate(row.date)}`,
    value: value === null ? null : formatValue(value),
    unit: estimate?.unit ?? "FNU",
    detail:
      interval === null
        ? (estimate?.abstainReason ?? CASE_COPY.rangeWithoutLevel)
        : `${reading.expectedRange} ${formatValue(interval.low)}–${formatValue(interval.high)}`,
    chip: LEVEL_LABELS[estimate?.level ?? "none"],
    level: estimate?.level ?? "none",
    foot:
      lock === undefined
        ? ""
        : joined(
            reading.tileMedian(lock.mdsa.toFixed(1), lock.n),
            leanText(leanOfTurbidity(lock.sspb)),
          ),
    spark: {
      values: reach.series.map((r) => {
        const v = turbidity(r)?.value;
        return typeof v === "number" ? v : null;
      }),
      selected,
    },
    tone: "sat",
  };
}

function temperatureTile(reach: ReachData, row: SeriesRow): Tile | null {
  const thermal = reach.thermal;
  if (thermal === null || thermal.series.length === 0) {
    return null;
  }
  const copy = CASE_COPY.quality;
  const index = nearestThermal(thermal.series, row.date);
  const pass = index === null ? null : thermal.series[index];
  const value = typeof pass?.estimate.value === "number" ? pass.estimate.value : null;
  const interval = pass?.estimate.interval ?? null;
  const card = thermal.card;
  const upstream = thermalValidatedAt(reach);
  return {
    id: "temperature",
    title: copy.temperature,
    source:
      pass === undefined || pass === null
        ? copy.landsat
        : `${landsatName(pass.platform)} · ${formatDate(pass.date)}`,
    value: value === null ? null : formatCelsius(value),
    unit: "°C",
    detail:
      value === null || interval === null
        ? copy.noLandsat
        : `${reading.expectedRange} ± ${((interval.high - interval.low) / 2).toFixed(1)} °C`,
    chip: LEVEL_LABELS[pass?.estimate.level ?? "none"],
    level: pass?.estimate.level ?? "none",
    foot:
      card === null
        ? ""
        : joined(
            reading.tileMean(card.metrics.lockbox.mae.toFixed(2), card.metrics.lockbox.n),
            leanText(leanOfTemperature(card.metrics.lockbox.bias)),
            upstream === null ? "" : `${copy.validatedAt} ${upstream}`,
          ),
    spark: {
      values: thermal.series.map((r) =>
        typeof r.estimate.value === "number" ? r.estimate.value : null,
      ),
      selected: index,
    },
    tone: "thermal",
  };
}

function gaugeTiles(reach: ReachData, row: SeriesRow, selected: number): Tile[] {
  const copy = CASE_COPY.context;
  const order = Object.keys(copy.names);
  const key = sceneKey(row);
  const keys = reach.series.map((r) => sceneKey(r));
  const rank = (parameter: string) =>
    order.includes(parameter) ? order.indexOf(parameter) : order.length;
  const parameters = [...new Set(reach.context.map((c) => c.parameter))].sort(
    (a, b) => rank(a) - rank(b),
  );
  return parameters.map((parameter) => {
    const readings = reach.context.filter((c) => c.parameter === parameter);
    const here = readings.find((c) => c.key === key);
    const sample = readings[0];
    return {
      id: parameter,
      title: copy.names[parameter] ?? sample?.name ?? parameter,
      source: "",
      value: here === undefined ? null : formatReading(here.value),
      unit: sample?.unit ?? "",
      detail: here === undefined ? copy.none : "",
      chip:
        here === undefined
          ? null
          : here.approval === "Approved"
            ? kinds.approved
            : kinds.provisional,
      approval: here?.approval,
      foot: "",
      spark: {
        values: keys.map((k) => readings.find((c) => c.key === k)?.value ?? null),
        selected,
      },
      tone: "gauge",
    };
  });
}

/**
 * The selected pass's water quality at a glance: what the satellite estimates (turbidity from
 * Sentinel-2, water temperature from the nearest Landsat pass), each with its interval, its level
 * and its locked-test error beside the error without the satellite; then what the USGS gauge
 * measured at the overpass. Each tile carries the year's values as a small line. The two groups
 * share the panel's width by their tile counts (a satellite tile counts double); where they do not
 * fit side by side, the gauge's group goes under the satellite's and tiles wrap, never sideways.
 *
 * @returns The view.
 */
export function WaterQualityView({ reach, selected }: WaterQualityViewProps) {
  const row = reach.series[selected];
  if (row === undefined) {
    return <div className="case-quality" />;
  }
  const copy = CASE_COPY.quality;
  const satellite = [
    turbidityTile(reach, row, selected),
    isUngauged(reach) ? ownPastTile(reach, row, selected) : null,
    temperatureTile(reach, row),
  ].filter((t): t is Tile => t !== null);
  const gauge = gaugeTiles(reach, row, selected);
  // The tile's parts are placed by CSS grid areas: the line gets its own row when the panel is
  // tall, or sits beside the value when it is short.
  const tile = (t: Tile) => (
    <li key={t.id} className="case-quality__tile" data-tone={t.tone}>
      <p className="case-quality__head">
        <span className="case-quality__title" title={t.title}>
          {t.title}
        </span>
        {t.source === "" ? null : <span className="case-quality__source">{t.source}</span>}
      </p>
      <p className="case-quality__value">
        {t.value === null ? (
          <span className="case-quality__none">–</span>
        ) : (
          <>
            {t.value}
            <span className="case-quality__unit"> {t.unit}</span>
          </>
        )}
      </p>
      {t.chip === null ? null : t.tone === "gauge" ? (
        <span
          className="case-chip case-quality__chip"
          data-approval={t.approval}
          title={t.approval === "Approved" ? kinds.approvedHelp : kinds.provisionalHelp}
        >
          {t.chip}
        </span>
      ) : (
        <span className="case-chip case-chip--level case-quality__chip" data-level={t.level}>
          {t.chip}
        </span>
      )}
      {t.detail === "" ? null : <p className="case-quality__detail">{t.detail}</p>}
      <Sparkline values={t.spark.values} selected={t.spark.selected} tone={t.tone} />
      {t.foot === "" ? null : <p className="case-quality__foot">{t.foot}</p>}
    </li>
  );
  return (
    <div className="case-quality">
      <section
        className="case-quality__group"
        data-kind="sat"
        aria-label={copy.satellite}
        style={{ "--count": satellite.length } as CSSProperties}
      >
        <p className="case-quality__label">
          <Satellite size={13} strokeWidth={1.9} aria-hidden="true" />
          {copy.satellite}
        </p>
        <ul className="case-quality__tiles">{satellite.map(tile)}</ul>
      </section>
      {gauge.length === 0 ? null : (
        <section
          className="case-quality__group"
          data-kind="gauge"
          aria-label={copy.gauge}
          style={{ "--count": gauge.length } as CSSProperties}
        >
          <p className="case-quality__label">
            <Gauge size={13} strokeWidth={1.9} aria-hidden="true" />
            {copy.gauge} · {formatDate(row.date, true)}
          </p>
          <ul className="case-quality__tiles">{gauge.map(tile)}</ul>
        </section>
      )}
    </div>
  );
}
