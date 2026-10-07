// The case map: MapLibre over Sentinel-2 cloudless imagery and Terrarium terrain, with the river
// reach drawn as a glowing line colored by NDTI. Loaded on demand (loadMap.ts), so MapLibre and its
// CSS live in their own chunk.
import "maplibre-gl/dist/maplibre-gl.css";

import {
  MapLibreMap,
  type ExpressionSpecification,
  type RasterDEMSourceSpecification,
  type StyleSpecification,
} from "maplibre-gl";

import { IMAGERY, MAP_LOOK, TERRAIN } from "./config.ts";
import { NO_DATA, ndtiPosition, rampRgb, rgba, type Rgb } from "./ramp.ts";
import type { CaseData } from "./types.ts";

/** Where the camera starts: the top-down handoff pose, or directly on the final view. */
export type CaseMapStart = "handoff" | "final";

/** Options for {@link createCaseMap}. */
export interface CreateCaseMapOptions {
  /** The case to show. */
  readonly data: CaseData;
  /** Initial camera pose. */
  readonly start: CaseMapStart;
  /** Zoom of the handoff pose (the globe may adjust the site's to fit the viewport). */
  readonly handoffZoom: number;
  /** Development only: draw canvas-generated stub tiles instead of fetching real ones. */
  readonly stubTiles: boolean;
}

/** How the final view fits around the panels. */
export interface FinalFrame {
  /** Insets (CSS px) that center the site in the part of the map the panels leave free. */
  readonly padding: {
    readonly top: number;
    readonly bottom: number;
    readonly left: number;
    readonly right: number;
  };
  /** Added to the site's final zoom (negative where the free area is too short for the reach). */
  readonly zoomOffset: number;
}

/** A screen position in CSS pixels, relative to the map container. */
export interface ScreenPoint {
  /** Pixels from the left edge. */
  readonly x: number;
  /** Pixels from the top edge. */
  readonly y: number;
}

/** Handle returned by {@link createCaseMap}. */
export interface CaseMapHandle {
  /** Resolves on the map's first `idle`, or after `MAP_LOOK.readyTimeoutMs`, whichever is first. */
  readonly ready: Promise<void>;
  /**
   * Eases from the current pose to the site's final zoom, pitch and bearing.
   *
   * @param durationMs - Flight duration.
   * @param easing - Easing of the flight, from 0..1 to 0..1.
   * @param frame - Where to center the site, and a zoom adjustment, for the panels' free area.
   * @returns Resolves when the flight ends or is interrupted.
   */
  readonly flyToFinal: (
    durationMs: number,
    easing: (t: number) => number,
    frame: FinalFrame,
  ) => Promise<void>;
  /**
   * Stops any flight and jumps to the final pose.
   *
   * @param frame - Where to center the site, and a zoom adjustment, for the panels' free area.
   */
  readonly jumpToFinal: (frame: FinalFrame) => void;
  /**
   * Eases back to the top-down handoff pose (site centered, pitch 0, bearing 0, no padding), where
   * the globe takes over on the way back.
   *
   * @param durationMs - Flight duration.
   * @param easing - Easing of the flight, from 0..1 to 0..1.
   * @param zoom - Handoff zoom, matching the globe's top-down view for this viewport.
   * @returns Resolves when the flight ends or is interrupted.
   */
  readonly flyToHandoff: (
    durationMs: number,
    easing: (t: number) => number,
    zoom: number,
  ) => Promise<void>;
  /**
   * Draws the river from upstream to downstream (`to` 1), or retracts it back upstream (`to` 0).
   *
   * @param to - Share of the reach to show at the end, 0..1.
   * @param durationMs - Duration; 0 jumps there at once.
   */
  readonly animateRiver: (to: number, durationMs: number) => void;
  /**
   * Projects a geographic point with the current camera.
   *
   * @param lng - Longitude in degrees.
   * @param lat - Latitude in degrees.
   * @returns Its position in the container.
   */
  readonly project: (lng: number, lat: number) => ScreenPoint;
  /** Camera and loading state, for development QA. */
  readonly stats: () => Record<string, unknown>;
  /** Stops everything and removes the map; safe to call more than once. */
  readonly dispose: () => void;
}

const SOURCE = { imagery: "imagery", terrain: "terrain", hillshade: "hillshade", river: "river" };
const LAYER = { hillshade: "hillshade", glow: "river-glow", core: "river-core" };

interface RiverStop {
  readonly at: number;
  readonly rgb: Rgb;
  readonly alpha: number;
}

// Colors along the reach, from the anomaly scene's samples.
function riverStops(data: CaseData): RiverStop[] {
  const scene =
    data.samples.find((candidate) => candidate.date === data.anomaly.sceneDate) ??
    data.samples.at(-1);
  return data.sampleProgress.map((at, index) => {
    const value = scene?.values[index] ?? null;
    return value === null
      ? { at, rgb: NO_DATA.rgb, alpha: NO_DATA.alpha }
      : { at, rgb: rampRgb(ndtiPosition(value)), alpha: 1 };
  });
}

// `line-gradient` showing the reach up to `reveal` (0..1), with a short soft leading edge.
function riverGradient(stops: readonly RiverStop[], reveal: number): ExpressionSpecification {
  const pairs: (number | string)[] = [];
  if (reveal >= 1) {
    for (const stop of stops) {
      pairs.push(stop.at, rgba(stop.rgb, stop.alpha));
    }
  } else {
    let head: RiverStop | undefined;
    for (const stop of stops) {
      if (stop.at >= reveal) {
        break;
      }
      pairs.push(stop.at, rgba(stop.rgb, stop.alpha));
      head = stop;
    }
    const edge = head ?? stops[0];
    if (edge === undefined || reveal <= 0) {
      return [
        "interpolate",
        ["linear"],
        ["line-progress"],
        0,
        "rgba(0, 0, 0, 0)",
        1,
        "rgba(0, 0, 0, 0)",
      ];
    }
    pairs.push(reveal, rgba(edge.rgb, edge.alpha));
    pairs.push(Math.min(1, reveal + MAP_LOOK.river.revealFeather), rgba(edge.rgb, 0));
  }
  return ["interpolate", ["linear"], ["line-progress"], ...pairs] as ExpressionSpecification;
}

// A zoom-driven interpolation from flat [zoom, value, zoom, value, ...] pairs.
function byZoom(pairs: readonly number[]): ExpressionSpecification {
  return ["interpolate", ["exponential", 1.4], ["zoom"], ...pairs] as ExpressionSpecification;
}

interface TileUrls {
  readonly imagery: string;
  readonly dem: string;
}

function buildStyle(
  data: CaseData,
  stops: readonly RiverStop[],
  reveal: number,
  tiles: TileUrls,
): StyleSpecification {
  const dem: RasterDEMSourceSpecification = {
    type: "raster-dem",
    tiles: [tiles.dem],
    encoding: TERRAIN.encoding,
    tileSize: TERRAIN.tileSize,
    maxzoom: TERRAIN.maxzoom,
  };
  const { imagery, hillshade, river, sky } = MAP_LOOK;
  const gradient = riverGradient(stops, reveal);
  return {
    version: 8,
    sources: {
      [SOURCE.imagery]: {
        type: "raster",
        tiles: [tiles.imagery],
        tileSize: IMAGERY.tileSize,
        maxzoom: IMAGERY.maxzoom,
      },
      [SOURCE.terrain]: dem,
      [SOURCE.hillshade]: { ...dem },
      [SOURCE.river]: {
        type: "geojson",
        lineMetrics: true,
        data: {
          type: "Feature",
          properties: { name: data.reach.properties.name },
          geometry: {
            type: "LineString",
            coordinates: data.reach.geometry.coordinates.map(([lng, lat]) => [lng, lat]),
          },
        },
      },
    },
    layers: [
      { id: "background", type: "background", paint: { "background-color": MAP_LOOK.background } },
      {
        id: "imagery",
        type: "raster",
        source: SOURCE.imagery,
        paint: {
          "raster-saturation": imagery.saturation,
          "raster-contrast": imagery.contrast,
          "raster-brightness-max": imagery.brightnessMax,
          "raster-fade-duration": imagery.fadeDurationMs,
        },
      },
      {
        id: LAYER.hillshade,
        type: "hillshade",
        source: SOURCE.hillshade,
        paint: {
          "hillshade-exaggeration": hillshade.exaggeration,
          "hillshade-shadow-color": hillshade.shadow,
          "hillshade-highlight-color": hillshade.highlight,
          "hillshade-accent-color": hillshade.accent,
        },
      },
      {
        id: LAYER.glow,
        type: "line",
        source: SOURCE.river,
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-width": byZoom(river.glowWidth),
          "line-blur": byZoom(river.glowBlur),
          "line-opacity": river.glowOpacity,
          "line-gradient": gradient,
        },
      },
      {
        id: LAYER.core,
        type: "line",
        source: SOURCE.river,
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-width": byZoom(river.coreWidth), "line-gradient": gradient },
      },
    ],
    terrain: { source: SOURCE.terrain, exaggeration: TERRAIN.exaggeration },
    sky: {
      "sky-color": sky.sky,
      "horizon-color": sky.horizon,
      "fog-color": sky.fog,
      "sky-horizon-blend": 0.6,
      "horizon-fog-blend": 0.8,
      "fog-ground-blend": 0.7,
      "atmosphere-blend": 0,
    },
  };
}

/**
 * Creates the case map inside `container`. The map is not interactive: the flythrough drives it.
 * If the elevation tiles fail, it drops the terrain and the hillshade and carries on; if the
 * imagery fails, the dark background, the river and the panels still show.
 *
 * @param container - Element MapLibre takes over; it must already have its final size.
 * @param options - Case data, starting pose and tile mode.
 * @returns The map handle.
 */
export async function createCaseMap(
  container: HTMLElement,
  options: CreateCaseMapOptions,
): Promise<CaseMapHandle> {
  const { data, start, handoffZoom } = options;
  // `import.meta.env.DEV` is a build-time constant: production drops the stub branch entirely.
  const stubTiles = import.meta.env.DEV && options.stubTiles;
  let tiles: TileUrls = { imagery: IMAGERY.tiles, dem: TERRAIN.tiles };
  if (stubTiles) {
    const { registerStubTiles } = await import("./stubTiles.ts");
    registerStubTiles();
    tiles = { imagery: "stub://imagery/{z}/{x}/{y}", dem: "stub://dem/{z}/{x}/{y}" };
  }

  const { site } = data;
  const center: [number, number] = [site.center[0], site.center[1]];
  const final = { center, zoom: site.finalZoom, pitch: site.pitch, bearing: site.bearing };
  const framed = (frame: FinalFrame) => ({
    ...final,
    zoom: final.zoom + frame.zoomOffset,
    padding: frame.padding,
  });
  const stops = riverStops(data);
  let reveal = start === "final" ? 1 : 0;

  const map = new MapLibreMap({
    container,
    style: buildStyle(data, stops, reveal, tiles),
    ...(start === "final" ? final : { center, zoom: handoffZoom, pitch: 0, bearing: 0 }),
    interactive: false,
    attributionControl: false,
    maxZoom: MAP_LOOK.maxZoom,
    maxPitch: 60,
    pixelRatio: Math.min(window.devicePixelRatio, 2),
  });

  let disposed = false;
  let markReady: (() => void) | null = null;
  const ready = new Promise<void>((resolve) => {
    markReady = resolve;
  });
  function settleReady(): void {
    window.clearTimeout(readyTimer);
    markReady?.();
    markReady = null;
  }
  const readyTimer = window.setTimeout(settleReady, MAP_LOOK.readyTimeoutMs);
  const idle = map.on("idle", () => {
    idle.unsubscribe();
    settleReady();
  });

  // Elevation errors drop the terrain and the hillshade; the rest only warn (development).
  let terrainEnabled = true;
  const warned = new Set<string>();
  map.on("error", (event) => {
    const { sourceId, error } = event as unknown as {
      sourceId?: string;
      error?: { message?: string };
    };
    if (terrainEnabled && (sourceId === SOURCE.terrain || sourceId === SOURCE.hillshade)) {
      terrainEnabled = false;
      map.setTerrain(null);
      if (map.getLayer(LAYER.hillshade) !== undefined) {
        map.setLayoutProperty(LAYER.hillshade, "visibility", "none");
      }
    }
    const key = sourceId ?? "map";
    if (import.meta.env.DEV && !warned.has(key)) {
      warned.add(key);
      console.warn(`[case] ${key}: ${error?.message ?? "error"} (further ones muted).`);
    }
  });

  let revealFrame = 0;
  function applyReveal(): void {
    if (map.getLayer(LAYER.core) === undefined) {
      return;
    }
    const gradient = riverGradient(stops, reveal);
    map.setPaintProperty(LAYER.glow, "line-gradient", gradient);
    map.setPaintProperty(LAYER.core, "line-gradient", gradient);
  }
  // A reveal requested before the style loaded is applied on load.
  map.on("load", applyReveal);

  let settleFlight: (() => void) | null = null;
  function endFlight(): void {
    const settle = settleFlight;
    settleFlight = null;
    settle?.();
  }
  // Ends the pending flight, whether it completes or is interrupted (`stop`, `jumpTo`).
  map.on("moveend", endFlight);

  const handle: CaseMapHandle = {
    ready,
    flyToFinal(durationMs, easing, frame) {
      endFlight();
      if (disposed) {
        return Promise.resolve();
      }
      return new Promise<void>((resolve) => {
        settleFlight = resolve;
        // `essential`: the caller already handles reduced motion.
        map.easeTo({ ...framed(frame), duration: durationMs, easing, essential: true });
      });
    },
    jumpToFinal(frame) {
      if (disposed) {
        return;
      }
      map.stop();
      map.jumpTo(framed(frame));
      endFlight();
    },
    flyToHandoff(durationMs, easing, zoom) {
      endFlight();
      if (disposed) {
        return Promise.resolve();
      }
      return new Promise<void>((resolve) => {
        settleFlight = resolve;
        map.easeTo({
          center,
          zoom,
          pitch: 0,
          bearing: 0,
          padding: { top: 0, bottom: 0, left: 0, right: 0 },
          duration: durationMs,
          easing,
          essential: true,
        });
      });
    },
    animateRiver(to, durationMs) {
      cancelAnimationFrame(revealFrame);
      if (disposed) {
        return;
      }
      const target = Math.min(1, Math.max(0, to));
      if (durationMs <= 0) {
        reveal = target;
        applyReveal();
        return;
      }
      const from = reveal;
      const startTime = performance.now();
      const step = (now: number) => {
        const t = Math.min(1, (now - startTime) / durationMs);
        // Ease-out (sine): the line's end slows down as it arrives.
        reveal = from + (target - from) * Math.sin((t * Math.PI) / 2);
        applyReveal();
        if (t < 1) {
          revealFrame = requestAnimationFrame(step);
        }
      };
      revealFrame = requestAnimationFrame(step);
    },
    project(lng, lat) {
      const point = map.project([lng, lat]);
      return { x: point.x, y: point.y };
    },
    stats() {
      const mapCenter = map.getCenter();
      return {
        zoom: map.getZoom(),
        pitch: map.getPitch(),
        bearing: map.getBearing(),
        center: [mapCenter.lng, mapCenter.lat],
        terrain: map.getTerrain() !== null,
        elevationM: map.queryTerrainElevation(center),
        reveal,
        loaded: map.loaded(),
        tilesLoaded: map.areTilesLoaded(),
        moving: map.isMoving(),
      };
    },
    dispose() {
      if (disposed) {
        return;
      }
      disposed = true;
      cancelAnimationFrame(revealFrame);
      settleReady();
      endFlight();
      map.remove();
    },
  };
  return handle;
}
