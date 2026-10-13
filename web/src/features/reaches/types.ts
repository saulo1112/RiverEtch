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
}
