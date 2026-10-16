import { nearestThermal, sceneKey, thermalValidatedAt, turbidity } from "../../reaches/scene.ts";
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

/** Props of {@link WaterQualityView}. */
export interface WaterQualityViewProps {
  readonly reach: ReachData;
  /** Index of the selected Sentinel-2 pass. */
  readonly selected: number;
}

const SPARK = { width: 120, height: 26, pad: 3 };

// A small line of the year's values with the selected one lit.
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
        <circle cx={x(selected)} cy={y(lit)} r={2.6} />
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
  readonly chip: string;
  readonly level?: string;
  readonly foot: string;
  readonly spark: { values: readonly (number | null)[]; selected: number | null };
  readonly tone: "sat" | "thermal" | "gauge";
}

function turbidityTile(reach: ReachData, row: SeriesRow, selected: number): Tile {
  const copy = CASE_COPY.quality;
  const estimate = turbidity(row);
  const value = typeof estimate?.value === "number" ? estimate.value : null;
  const interval = estimate?.interval ?? null;
  const lock = reach.card?.metrics.lockbox;
  return {
    id: "turbidity",
    title: copy.turbidity,
    source: `${copy.sentinel} · ${formatDate(row.date)}`,
    value: value === null ? null : formatValue(value),
    unit: estimate?.unit ?? "FNU",
    detail:
      interval === null
        ? (estimate?.abstainReason ?? CASE_COPY.rangeWithoutLevel)
        : `${formatValue(interval.low)}–${formatValue(interval.high)} · ${CASE_COPY.interval}`,
    chip: LEVEL_LABELS[estimate?.level ?? "none"],
    level: estimate?.level ?? "none",
    foot:
      lock === undefined
        ? ""
        : `${lock.mdsa.toFixed(1)} % ${copy.error} · ${lock.null_mdsa.toFixed(1)} % ${copy.without}`,
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
        : `± ${((interval.high - interval.low) / 2).toFixed(1)} °C · ${CASE_COPY.interval}`,
    chip: LEVEL_LABELS[pass?.estimate.level ?? "none"],
    level: pass?.estimate.level ?? "none",
    foot:
      card === null
        ? ""
        : `${card.metrics.lockbox.mae.toFixed(1)} °C ${copy.error} · ${card.metrics.null_lockbox.mae.toFixed(1)} °C ${copy.without}${upstream === null ? "" : ` · ${copy.validatedAt} ${upstream}`}`,
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
      detail:
        here === undefined
          ? copy.none
          : `${CASE_COPY.quality.measured} · ${here.approval.toLowerCase()}`,
      chip: CASE_COPY.quality.measuredChip,
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
 * measured at the overpass. Each tile carries the year's values as a small line.
 *
 * @returns The view.
 */
export function WaterQualityView({ reach, selected }: WaterQualityViewProps) {
  const row = reach.series[selected];
  if (row === undefined) {
    return <div className="case-quality" />;
  }
  const copy = CASE_COPY.quality;
  const satellite = [turbidityTile(reach, row, selected), temperatureTile(reach, row)].filter(
    (t): t is Tile => t !== null,
  );
  const gauge = gaugeTiles(reach, row, selected);
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
        <span
          className="case-chip case-quality__chip"
          data-level={t.level}
          data-measured={t.tone === "gauge"}
        >
          {t.chip}
        </span>
      </p>
      <p className="case-quality__detail">{t.detail}</p>
      <Sparkline values={t.spark.values} selected={t.spark.selected} tone={t.tone} />
      {t.foot === "" ? null : <p className="case-quality__foot">{t.foot}</p>}
    </li>
  );
  return (
    <div className="case-quality">
      <section className="case-quality__group" aria-label={copy.satellite}>
        <p className="case-quality__label">{copy.satellite}</p>
        <ul className="case-quality__tiles">{satellite.map(tile)}</ul>
      </section>
      {gauge.length === 0 ? null : (
        <section className="case-quality__group" aria-label={copy.gauge}>
          <p className="case-quality__label">
            {copy.gauge} · {formatDate(row.date, true)}
          </p>
          <ul className="case-quality__tiles">{gauge.map(tile)}</ul>
        </section>
      )}
    </div>
  );
}
