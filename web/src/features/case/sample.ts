// ILLUSTRATIVE SAMPLE DATA, NOT MEASURED. A deterministic stand-in for one pipeline output, so the
// case view can be built before the Sentinel-2 / rainfall pipeline exists. The reach is a smooth
// synthetic meander through the placeholder site, not the surveyed course of the Atrato, and every
// number below comes from a seeded generator. The UI labels it "Illustrative sample data".
import { CASE_SITE } from "./site.ts";
import type {
  AnomalySummary,
  CaseData,
  LngLat,
  NdtiScene,
  RainfallDay,
  ReachFeature,
  ReachStats,
} from "./types.ts";

const METRES_PER_DEGREE = 111_320;

// Reach: an axis through the site center, flowing NNW, with two superposed meanders.
const REACH = {
  axisLengthM: 7_650,
  flowBearingDeg: -12,
  meanders: [
    { amplitudeM: 420, wavelengthM: 2_600, phase: 0.4 },
    { amplitudeM: 140, wavelengthM: 1_150, phase: 1.7 },
  ],
  vertices: 121,
} as const;

// Sampling: points along the reach, scenes every 5 days over 60 days, the cloudy ones.
const SAMPLES = 41;
const START_DATE = "2025-01-13";
const SCENE_STEP_DAYS = 5;
const SCENES = 13;
const CLOUDY_SCENES: ReadonlySet<number> = new Set([3, 7]);
// Scene 9 is partly cloudy over this run of samples.
const PARTIAL_CLOUD = { scene: 9, from: 26, to: 33 } as const;

// Turbidity model: a scene-to-scene level, a slight rise downstream, sample noise and, on the last
// two scenes, a plume that starts past the split point and fades slowly downstream.
const NDTI = {
  level: 0.03,
  levelJitter: 0.04,
  downstreamRise: 0.012,
  sampleNoise: 0.005,
  // Extra level on the scene right after the early-February storm (rain explains it).
  stormScene: 5,
  stormLift: 0.03,
  split: 0.46,
  plumeRamp: 0.12,
  // Level and plume amplitude of the anomalous scenes (clear water upstream, a plume downstream),
  // tuned so the last scene reads +2.8 σ over the baseline with ΔNDTI +0.11 and the run starts on
  // the scene before it. Re-check those figures after changing anything here.
  anomalyLevel: 0.0073,
  plume: new Map([
    [11, 0.105],
    [12, 0.1275],
  ]),
} as const;

// Scenes before this index form the baseline the z-scores are measured against.
const BASELINE_SCENES = 10;
// A scene at or above this z-score is anomalous.
const ANOMALY_Z = 2;

// Seeded PRNG (mulberry32): the fixture is identical on every load.
function createRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4_294_967_296;
  };
}

function addDays(isoDate: string, days: number): string {
  const date = new Date(`${isoDate}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

const round = (value: number, digits: number) => Number(value.toFixed(digits));

function smoothstep(edge0: number, edge1: number, x: number): number {
  const t = Math.min(1, Math.max(0, (x - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}

function buildReach(): ReachFeature {
  const [lng0, lat0] = CASE_SITE.center;
  const bearing = (REACH.flowBearingDeg * Math.PI) / 180;
  const axis = { east: Math.sin(bearing), north: Math.cos(bearing) };
  const across = { east: axis.north, north: -axis.east };
  const offset = (s: number) =>
    REACH.meanders.reduce(
      (sum, { amplitudeM, wavelengthM, phase }) =>
        sum + amplitudeM * Math.sin((2 * Math.PI * s) / wavelengthM + phase),
      0,
    );
  // Shift the meanders so the line passes exactly through the site center (s = 0).
  const centerOffset = offset(0);
  const metresPerDegreeLng = METRES_PER_DEGREE * Math.cos((lat0 * Math.PI) / 180);

  const coordinates: LngLat[] = [];
  let lengthM = 0;
  let previous: { east: number; north: number } | null = null;
  for (let i = 0; i < REACH.vertices; i += 1) {
    // Upstream (south) to downstream (north).
    const s = (i / (REACH.vertices - 1) - 0.5) * REACH.axisLengthM;
    const w = offset(s) - centerOffset;
    const east = s * axis.east + w * across.east;
    const north = s * axis.north + w * across.north;
    if (previous !== null) {
      lengthM += Math.hypot(east - previous.east, north - previous.north);
    }
    previous = { east, north };
    coordinates.push([
      round(lng0 + east / metresPerDegreeLng, 6),
      round(lat0 + north / METRES_PER_DEGREE, 6),
    ]);
  }
  return {
    type: "Feature",
    properties: {
      name: "Illustrative reach (not the surveyed river course)",
      lengthM: round(lengthM, 0),
    },
    geometry: { type: "LineString", coordinates },
  };
}

function buildScenes(sampleProgress: readonly number[]): NdtiScene[] {
  const random = createRandom(20_250_113);
  const jitter = () => random() * 2 - 1;
  return Array.from({ length: SCENES }, (_, scene): NdtiScene => {
    const date = addDays(START_DATE, scene * SCENE_STEP_DAYS);
    const plume = NDTI.plume.get(scene);
    const sceneJitter = NDTI.levelJitter * jitter();
    const level =
      plume === undefined
        ? NDTI.level + sceneJitter + (scene === NDTI.stormScene ? NDTI.stormLift : 0)
        : NDTI.anomalyLevel;
    const values = sampleProgress.map((p, index) => {
      // Draw the noise even for cloudy samples, so clouds never reshuffle the other scenes.
      const noise = NDTI.sampleNoise * jitter();
      const cloudy =
        CLOUDY_SCENES.has(scene) ||
        (scene === PARTIAL_CLOUD.scene && index >= PARTIAL_CLOUD.from && index <= PARTIAL_CLOUD.to);
      if (cloudy) {
        return null;
      }
      const plumeShape =
        smoothstep(NDTI.split, NDTI.split + NDTI.plumeRamp, p) * (1 - 0.25 * (p - NDTI.split));
      return round(level + NDTI.downstreamRise * p + noise + (plume ?? 0) * plumeShape, 3);
    });
    return { date, values };
  });
}

function buildRainfall(): RainfallDay[] {
  const random = createRandom(5_690);
  const days = (SCENES - 1) * SCENE_STEP_DAYS + 1;
  // An early-February storm (mm per day) a few days before scene 5.
  const storm = new Map([
    [22, 48.6],
    [23, 61.2],
    [24, 29.8],
  ]);
  return Array.from({ length: days }, (_, day): RainfallDay => {
    const wet = random() < 0.62;
    const amount = random();
    let mm = wet ? 3 + 30 * amount ** 2 : 2 * amount;
    mm = storm.get(day) ?? mm;
    // The last day is the one the alert card quotes.
    if (day === days - 1) {
      mm = 12.4;
    }
    return { date: addDays(START_DATE, day), mm: round(mm, 1) };
  });
}

function mean(values: readonly number[]): number {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

// Mean of the valid samples on one side of the split, or null when all are cloudy.
function windowMean(
  scene: NdtiScene,
  sampleProgress: readonly number[],
  side: "upstream" | "downstream",
): number | null {
  const values = scene.values.filter((value, index): value is number => {
    const p = sampleProgress[index] ?? 0;
    const inWindow = side === "upstream" ? p < NDTI.split : p >= NDTI.split;
    return value !== null && inWindow;
  });
  return values.length === 0 ? null : mean(values);
}

function summarize(
  scenes: readonly NdtiScene[],
  sampleProgress: readonly number[],
): { anomaly: AnomalySummary; stats: ReachStats } {
  const downstream = scenes.map((scene) => windowMean(scene, sampleProgress, "downstream"));
  const baseline = downstream
    .slice(0, BASELINE_SCENES)
    .filter((value): value is number => value !== null);
  const baselineMean = mean(baseline);
  const baselineStd = Math.sqrt(mean(baseline.map((value) => (value - baselineMean) ** 2)));
  const zScore = (value: number) => (value - baselineMean) / baselineStd;

  const lastIndex = scenes.length - 1;
  const last = scenes[lastIndex];
  const lastDownstream = downstream[lastIndex];
  const lastUpstream = last === undefined ? null : windowMean(last, sampleProgress, "upstream");
  if (last === undefined || lastDownstream == null || lastUpstream === null) {
    throw new Error("The illustrative fixture needs a clear last scene.");
  }
  // The anomalous run: the trailing scenes at or above the threshold (cloudy scenes end it).
  let onset = lastIndex;
  while (onset > 0) {
    const previous = downstream[onset - 1];
    if (previous == null || zScore(previous) < ANOMALY_Z) {
      break;
    }
    onset -= 1;
  }
  return {
    anomaly: {
      zScore: round(zScore(lastDownstream), 2),
      sceneDate: last.date,
      onsetDate: scenes[onset]?.date ?? last.date,
    },
    stats: {
      splitProgress: NDTI.split,
      upstreamMeanNdti: round(lastUpstream, 3),
      downstreamMeanNdti: round(lastDownstream, 3),
      deltaNdti: round(lastDownstream - lastUpstream, 3),
    },
  };
}

function buildCase(): CaseData {
  const reach = buildReach();
  const sampleProgress = Array.from({ length: SAMPLES }, (_, index) =>
    round(index / (SAMPLES - 1), 4),
  );
  const samples = buildScenes(sampleProgress);
  const { anomaly, stats } = summarize(samples, sampleProgress);
  return {
    site: CASE_SITE,
    reach,
    sampleProgress,
    samples,
    rainfall: buildRainfall(),
    // A strong downstream rise with modest rain upstream: rainfall does not explain it.
    classification: "candidate_human_pressure",
    anomaly,
    stats,
    illustrative: true,
  };
}

/** Illustrative sample case for the placeholder site. Not measured; see the file header. */
export const ILLUSTRATIVE_CASE: CaseData = buildCase();
