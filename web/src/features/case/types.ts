// Data contract of a case: what the Sentinel-2 / rainfall pipeline will emit for one river reach,
// and what the case view renders. Coordinates follow GeoJSON order ([longitude, latitude]).

/** A `[longitude, latitude]` pair in decimal degrees (GeoJSON order). */
export type LngLat = readonly [number, number];

/** A study site: where the case map looks and how the flythrough frames it. */
export interface SiteConfig {
  /** Stable identifier. */
  readonly id: string;
  /** Display name. */
  readonly name: string;
  /** Map center and dive target, `[lng, lat]`. */
  readonly center: LngLat;
  /** Web Mercator zoom (512 px tiles) at which the globe hands over to the map, looking straight down. */
  readonly handoffZoom: number;
  /** Zoom the map settles on. */
  readonly finalZoom: number;
  /** Final pitch in degrees (0 = straight down). */
  readonly pitch: number;
  /** Final bearing in degrees, clockwise from north. */
  readonly bearing: number;
}

/** The river reach as a GeoJSON LineString feature, ordered from upstream to downstream. */
export interface ReachFeature {
  readonly type: "Feature";
  readonly properties: {
    /** Display name of the reach. */
    readonly name: string;
    /** Length along the line, in metres. */
    readonly lengthM: number;
  };
  readonly geometry: {
    readonly type: "LineString";
    readonly coordinates: readonly LngLat[];
  };
}

/** NDTI (normalized difference turbidity index) along the reach on one Sentinel-2 scene. */
export interface NdtiScene {
  /** Acquisition date, ISO `YYYY-MM-DD`. */
  readonly date: string;
  /**
   * One value per sample point ({@link CaseData.sampleProgress}); `null` where the river was under
   * cloud or had no valid pixels. A fully cloudy scene holds only `null`s.
   */
  readonly values: readonly (number | null)[];
}

/** Rainfall over the upstream catchment on one day. */
export interface RainfallDay {
  /** Day, ISO `YYYY-MM-DD`. */
  readonly date: string;
  /** Accumulated rainfall, in millimetres. */
  readonly mm: number;
}

/**
 * Verdict on the latest scene: no anomaly, an anomaly the rainfall explains, or an anomaly the
 * rainfall does not explain (a candidate for human pressure, to be challenged, never an accusation).
 */
export type CaseClassification = "normal" | "explained_by_climate" | "candidate_human_pressure";

/** Upstream and downstream turbidity on the anomaly scene. */
export interface ReachStats {
  /** Position along the reach (0 = upstream end, 1 = downstream end) that splits the two windows. */
  readonly splitProgress: number;
  /** Mean NDTI of the valid samples upstream of the split. */
  readonly upstreamMeanNdti: number;
  /** Mean NDTI of the valid samples downstream of the split. */
  readonly downstreamMeanNdti: number;
  /** Downstream minus upstream mean NDTI. */
  readonly deltaNdti: number;
}

/** The detected anomaly. */
export interface AnomalySummary {
  /** Downstream mean NDTI on the anomaly scene, in standard deviations from the baseline scenes. */
  readonly zScore: number;
  /** Date of the scene the case is about (the latest scene). */
  readonly sceneDate: string;
  /** Date of the first scene of the anomalous run. */
  readonly onsetDate: string;
}

/** Everything the case view needs for one reach. */
export interface CaseData {
  /** Where the case is. */
  readonly site: SiteConfig;
  /** The river reach the samples run along. */
  readonly reach: ReachFeature;
  /** Position of each sample point along the reach (0 = upstream end, 1 = downstream end). */
  readonly sampleProgress: readonly number[];
  /** NDTI samples per scene, oldest first (scenes are about 5 days apart, some cloudy). */
  readonly samples: readonly NdtiScene[];
  /** Daily upstream rainfall over the same window, oldest first. */
  readonly rainfall: readonly RainfallDay[];
  /** Verdict on the anomaly scene. */
  readonly classification: CaseClassification;
  /** The anomaly being reported. */
  readonly anomaly: AnomalySummary;
  /** Upstream versus downstream on the anomaly scene. */
  readonly stats: ReachStats;
  /** True for illustrative sample data; the UI must say so wherever the data shows. */
  readonly illustrative: boolean;
}
