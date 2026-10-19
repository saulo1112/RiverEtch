// The files the pipeline writes for the web (docs/water-quality/reach/README.md, "Files for the
// web"), as the case view reads them. Records follow the observation record v2 contract
// (docs/schema/observation-record.v2.schema.json); only the fields the UI uses are typed.

/** A `[longitude, latitude]` pair in decimal degrees (GeoJSON order). */
export type LngLat = readonly [number, number];

/** How far a model's error was established (the v5 levels). */
export type Level = "validated" | "estimated" | "indicative" | "none";

/** A 90 % (or other) interval around an estimate. */
export interface Interval {
  readonly low: number;
  readonly high: number;
  readonly coverage: number;
  readonly method: string;
}

/** One target's estimate in a record. */
export interface Estimate {
  readonly target: string;
  readonly unit: string;
  readonly level: Level;
  readonly value?: number | null;
  readonly interval?: Interval | null;
  readonly relativeClass?: "low" | "medium" | "high" | null;
  readonly abstainReason?: string | null;
  readonly modelId?: string | null;
  readonly modelCardSha256?: string | null;
  readonly rangeMdsa?: number | null;
  readonly basis?: string | null;
}

/** An index's values per sub-reach. */
export interface IndexValues {
  readonly upstream: number | null;
  readonly downstream: number | null;
  readonly reach: number | null;
  readonly delta: number | null;
}

/** One sealed observation record (v2). */
export interface ObservationRecord {
  readonly schemaVersion: 2;
  readonly reachId: string;
  readonly date: string;
  readonly sceneId: string;
  readonly stacItemIds: readonly string[];
  readonly indices: { readonly ndti: IndexValues; readonly nirRed: IndexValues | null };
  readonly verdict: { readonly anomalous: boolean };
  readonly rain: { readonly point: boolean | null };
  readonly estimates: readonly Estimate[];
  readonly provenance: {
    readonly collection: string;
    readonly stacItems: readonly { readonly id: string; readonly url: string }[];
    readonly codeCommit: string;
    readonly processingParamsSha256: string;
    readonly processingBaseline: readonly string[];
  };
  readonly recordSha256: string;
}

/** One row of `series.json`: a record trimmed for a chart. */
export interface SeriesRow {
  readonly date: string;
  readonly sceneId: string;
  readonly file: string;
  readonly recordSha256: string;
  readonly indices: { readonly ndti: IndexValues; readonly nirRed: IndexValues | null };
  readonly estimates: readonly Estimate[];
}

/** `reach.json`: the site, its estimate station and the baseline's period. */
export interface ReachInfo {
  readonly site: string;
  readonly name: string;
  readonly river: string;
  readonly timezone: string;
  readonly station: {
    readonly id: string;
    readonly source: string;
    readonly name: string;
    readonly url?: string;
  };
  readonly targets: readonly string[];
  readonly cards: Readonly<Record<string, string>>;
  readonly baseline: {
    readonly first: string | null;
    readonly last: string | null;
    readonly usableScenes: number;
  };
}

/** The scores of one evaluation in a model card. */
export interface CardMetrics {
  readonly n: number;
  readonly mdsa: number;
  readonly sspb: number;
  readonly null_mdsa: number;
  readonly coverage90: number;
}

/** The parts of a model card the case view shows. */
export interface ModelCard {
  readonly modelId: string;
  readonly unit: string;
  readonly candidate: string;
  readonly basis: string;
  readonly metrics: { readonly lockbox: CardMetrics; readonly inner?: CardMetrics };
  readonly levels: readonly {
    readonly predicted_range: string;
    readonly level: Level;
    readonly mdsa: number | null;
    readonly n: number;
    readonly interval_factor90?: number;
  }[];
  readonly trainingPairs: { readonly site: number; readonly usgs: number };
}

/** One scene of the prospective check (`checks/checks.csv`): the gauge at the overpass. */
export interface GaugeCheck {
  readonly key: string;
  readonly date: string;
  /** The overpass (ISO, UTC; "" in an older file). */
  readonly datetimeUtc: string;
  readonly estimate: number | null;
  readonly value: number | null;
  readonly approval: string;
}

/** `maps.json`: how the per-scene NDTI maps are packed and where they lie. */
export interface MapsIndex {
  readonly width: number;
  readonly height: number;
  /** Top left, top right, bottom right, bottom left. */
  readonly corners: readonly [LngLat, LngLat, LngLat, LngLat];
  readonly encoding: {
    readonly r: {
      readonly ndti: readonly [number, number];
      readonly bytes: readonly [number, number];
    };
    readonly b: Readonly<Record<string, number>>;
  };
  readonly maps: readonly {
    readonly key: string;
    readonly sceneId: string;
    readonly date: string;
    readonly file: string;
    /** The pass in true color over the same box (WebP), when it was drawn. */
    readonly trueColor?: string;
  }[];
}

/** A GeoJSON feature of `geometry.geojson`. */
export interface ReachFeature {
  readonly type: "Feature";
  readonly properties: {
    readonly kind: "river" | "centreline" | "subreach" | "station" | "window";
    readonly name?: string;
    readonly id?: string;
    readonly lengthM?: number;
  };
  readonly geometry:
    | {
        readonly type: "MultiPolygon";
        readonly coordinates: readonly (readonly (readonly LngLat[])[])[];
      }
    | { readonly type: "LineString"; readonly coordinates: readonly LngLat[] }
    | { readonly type: "Point"; readonly coordinates: LngLat };
}

/** `geometry.geojson`. */
export interface ReachGeometry {
  readonly type: "FeatureCollection";
  readonly features: readonly ReachFeature[];
}

/** One water-temperature pass (`thermal/series.json`, preregistration v6). */
export interface ThermalRow {
  readonly date: string;
  readonly sceneId: string;
  readonly file: string;
  readonly recordSha256: string;
  readonly platform: string;
  readonly waterPixels: number;
  readonly estimate: {
    readonly level: Level;
    readonly value?: number | null;
    readonly interval?: Interval | null;
    readonly unit: string;
  };
}

/** One sealed water-temperature record (v1, docs/schema/README.md). */
export interface ThermalRecord {
  readonly schemaVersion: 1;
  readonly kind: "water_temperature";
  readonly reachId: string;
  readonly date: string;
  readonly datetimeUtc: string;
  readonly sceneId: string;
  readonly platform: string;
  readonly window: {
    readonly pixels: number;
    readonly waterPixels: number;
    /** The median surface temperature of the window's clear water, kelvin. */
    readonly surfaceTemperatureK: number;
  };
  readonly estimate: Estimate;
  readonly provenance: {
    readonly collection: string;
    readonly stacItems: readonly { readonly id: string; readonly url: string }[];
    readonly codeCommit: string;
    readonly processingParamsSha256: string;
  };
  readonly recordSha256: string;
}

/** The gauge's water temperature at a Landsat pass (`thermal/checks.csv`). */
export interface ThermalCheck {
  readonly sceneId: string;
  readonly date: string;
  /** The overpass (ISO, UTC; "" in an older file). */
  readonly datetimeUtc: string;
  readonly value: number | null;
  readonly approval: string;
}

/** One of the gauge's own readings at a Sentinel-2 pass (`checks/context.csv`). */
export interface ContextReading {
  readonly key: string;
  readonly parameter: string;
  readonly name: string;
  readonly value: number;
  readonly unit: string;
  readonly approval: string;
}

/** The parts of the water-temperature card the case view shows. */
export interface TemperatureCard {
  readonly modelId: string;
  /** Set when the card was validated at another gauge of the same river (v7.1). */
  readonly validationSite?: string;
  readonly validationSiteName?: string;
  readonly candidate: string;
  readonly halfWidth90: number;
  readonly levels: readonly {
    readonly level: Level;
    readonly mae: number | null;
    readonly n: number;
  }[];
  readonly metrics: {
    readonly lockbox: {
      readonly mae: number;
      readonly bias: number;
      readonly n: number;
      readonly coverage90?: number;
    };
    readonly null_lockbox: { readonly mae: number };
  };
}

/**
 * One line of a demo reach's outcomes ledger (`outcomes/ledger.jsonl`, written by
 * `climate-pipeline reach score` under docs/water-quality/prospective.md): an anchored claim, the
 * gauge's reading at its overpass and whether it fell inside the sealed interval. A first read is
 * never replaced: an approved re-read, or a final "no gauge value", is a new line.
 */
export interface Outcome {
  readonly claimRecordSha256: string;
  readonly claimLedger: string;
  readonly claimLine: number;
  readonly sceneId: string;
  /** "turbidity" or "water_temperature". */
  readonly target: string;
  readonly unit: string;
  /** The sealed estimate (null: the record abstained). */
  readonly estimate: number | null;
  readonly interval: { readonly low: number; readonly high: number } | null;
  readonly overpassUtc: string;
  readonly gauge: {
    readonly station: string;
    readonly parameter: string;
    readonly value: number;
    readonly unit: string;
    readonly approval: string;
    readonly rule: string;
    readonly n: number;
  } | null;
  /** Null when there is nothing to compare (no gauge value, no interval, abstained). */
  readonly inside: boolean | null;
  readonly status: "scored" | "no gauge value" | "abstained";
  readonly final: boolean;
  readonly readUtc: string;
  readonly ruleSha256: string;
}

/** What every year of `climate.json` holds (`reach climate`, docs/water-quality/reach/README.md). */
interface ClimateYearBase {
  readonly year: number;
  /** Days with a value (for the temperature, days from June to September). */
  readonly days: number;
  /** Covered enough to be ranked (never the year of the last value). */
  readonly complete: boolean;
  /** The year of the last value: shown to date, never ranked. */
  readonly toDate: boolean;
  /** Some of its values are still provisional. */
  readonly provisional: boolean;
}

/** One calendar year of the gauge's discharge (m³/s). */
export interface ClimateFlowYear extends ClimateYearBase {
  readonly peak: number;
  readonly peakDay: string;
  /** 1 = the highest of the ranked years (null: not ranked). */
  readonly peakRank: number | null;
  /** The lowest mean of 7 consecutive days (null: no full week). */
  readonly low7: number | null;
  /** The last day of that week. */
  readonly low7Day: string | null;
  /** 1 = the lowest of the ranked years. */
  readonly low7Rank: number | null;
}

/** One calendar year of the gauge's water temperature (°C). */
export interface ClimateHeatYear extends ClimateYearBase {
  /** The warmest daily mean from June to September. */
  readonly warmest: number;
  readonly warmestDay: string;
  /** 1 = the warmest of the ranked years. */
  readonly warmestRank: number | null;
}

/** `climate.json`: the gauge's own daily record, year by year (never an estimate). */
export interface ClimateRecord {
  readonly station: { readonly id: string; readonly name: string; readonly url?: string };
  readonly source: string;
  /** The last day with a value. */
  readonly through: string;
  readonly discharge: {
    readonly unit: string;
    /** The first day of the record. */
    readonly first: string;
    readonly rankedYears: number;
    readonly years: readonly ClimateFlowYear[];
  };
  readonly temperature: {
    readonly unit: string;
    readonly first: string;
    readonly rankedYears: number;
    readonly years: readonly ClimateHeatYear[];
  } | null;
  /** The demo reaches' extreme days (rule v1, docs/water-quality/prospective.md, section 5). */
  readonly extremes?: ClimateExtremes;
}

/** One calendar year's extreme days (null: not measured that year, or no satellite record). */
export interface ClimateExtremeYear {
  readonly year: number;
  /** The discharge year is ranked (low and high flow). */
  readonly complete: boolean;
  readonly toDate: boolean;
  readonly low: number;
  readonly high: number;
  readonly warm: number | null;
  /** The summer is ranked (warm water). */
  readonly warmComplete: boolean;
  /** Where "seen" comes from: the v5 inputs (2019-2025), the sealed records (2026), or none. */
  readonly seenFrom: "v5 inputs" | "sealed records" | null;
  /** Usable passes that year. */
  readonly passes: number | null;
  readonly lowSeen: number | null;
  readonly highSeen: number | null;
  readonly warmSeen: number | null;
  /** 1 = the most such days of the ranked years. */
  readonly lowRank: number | null;
  readonly highRank: number | null;
  readonly warmRank: number | null;
}

/** Days of a kind in the satellite era, and how many a usable pass saw. */
export interface ClimateSeen {
  readonly days: number;
  readonly seen: number;
}

/** `climate.json`'s extreme days (`reach climate`, pipeline/src/climate_pipeline/reach/extremes.py). */
export interface ClimateExtremes {
  readonly rule: string;
  readonly thresholds: {
    /** At or below (m³/s). */
    readonly low: number;
    /** At or above (m³/s). */
    readonly high: number;
    /** At or above (°C; null: the gauge has no temperature). */
    readonly warm: number | null;
    readonly flowUnit: string;
    readonly warmUnit: string;
    readonly reference: {
      readonly first: string;
      readonly last: string;
      readonly warmFirstYear: number;
      readonly flowDays: number;
      readonly warmDays: number;
    };
  };
  readonly years: readonly ClimateExtremeYear[];
  readonly rankedYears: { readonly flow: number; readonly warm: number };
  readonly satelliteEra: {
    readonly first: number;
    readonly last: number;
    readonly low: ClimateSeen;
    readonly high: ClimateSeen;
    readonly normal: ClimateSeen;
    readonly warm: ClimateSeen | null;
  };
  /** The lock box's pairs on each kind of day, and the minimum an error comparison needs. */
  readonly lockbox: {
    readonly first: string;
    readonly last: string;
    readonly pairs: number;
    readonly low: number;
    readonly high: number;
    readonly warm: number | null;
    readonly minimum: number;
  };
}

/** Everything the case view loads for one reach, up front. */
export interface ReachData {
  /** Where the files live (ends with a slash). */
  readonly base: string;
  readonly info: ReachInfo;
  readonly series: readonly SeriesRow[];
  readonly card: ModelCard | null;
  readonly checks: readonly GaugeCheck[];
  readonly maps: MapsIndex | null;
  readonly geometry: ReachGeometry | null;
  /** Water temperature (v6): its passes, the gauge at each and its card (null: none here). */
  readonly thermal: {
    readonly series: readonly ThermalRow[];
    readonly checks: readonly ThermalCheck[];
    readonly card: TemperatureCard | null;
  } | null;
  /** The gauge's own readings at each Sentinel-2 pass (v6). */
  readonly context: readonly ContextReading[];
  /** The gauge's whole daily record, year by year: the climate context (null: none yet). */
  readonly climate: ClimateRecord | null;
  /** The prospective outcomes of its anchored claims (demo reaches; empty: none yet). */
  readonly outcomes: readonly Outcome[];
}
