// The case map: MapLibre over Sentinel-2 cloudless imagery and Terrarium terrain, with the reach's
// real corridor (geometry.geojson) filled and outlined, and the selected scene's NDTI drawn over
// its water pixel by pixel (maps/<key>.png, colored in the browser). The gauge sits on its window.
// Loaded on demand (loadMap.ts), so MapLibre and its CSS live in their own chunk.
import "maplibre-gl/dist/maplibre-gl.css";

import {
  LngLatBounds,
  MapLibreMap,
  Marker,
  type CanvasSource,
  type ExpressionSpecification,
  type FilterSpecification,
  type RasterDEMSourceSpecification,
  type StyleSpecification,
} from "maplibre-gl";

import { colorize } from "../reaches/colorize.ts";
import type { ReachCase } from "../reaches/catalog.ts";
import type { LngLat, ReachData } from "../reaches/types.ts";
import { IMAGERY, MAP_LOOK, TERRAIN } from "./config.ts";

/** Where the camera starts: the top-down handoff pose, or directly on the final view. */
export type CaseMapStart = "handoff" | "final";

/** Options for {@link createCaseMap}. */
export interface CreateCaseMapOptions {
  /** The case (its centre, pitch and bearing). */
  readonly reachCase: ReachCase;
  /** Its data (the corridor, the maps' index). */
  readonly reach: ReachData;
  /** The NDTI the ramp spans for this reach. */
  readonly domain: readonly [number, number];
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
  /** Added to the fitted zoom (negative where the free area is too short for the reach). */
  readonly zoomOffset: number;
}

/** A screen position in CSS pixels, relative to the map container. */
export interface ScreenPoint {
  /** Pixels from the left edge. */
  readonly x: number;
  /** Pixels from the top edge. */
  readonly y: number;
}

/** What the gauge marker says for the selected scene. */
export interface GaugeLabel {
  /** E.g. "30.5 FNU". */
  readonly value: string;
  /** E.g. "USGS 07374525". */
  readonly caption: string;
}

/** Handle returned by {@link createCaseMap}. */
export interface CaseMapHandle {
  /** Resolves on the map's first `idle`, or after `MAP_LOOK.readyTimeoutMs`, whichever is first. */
  readonly ready: Promise<void>;
  /**
   * Eases from the current pose to the reach's final view.
   *
   * @param durationMs - Flight duration.
   * @param easing - Easing of the flight, from 0..1 to 0..1.
   * @param frame - The panels' free area and a zoom adjustment.
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
   * @param frame - The panels' free area and a zoom adjustment.
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
   * Fills the river from upstream to downstream (`to` 1), or empties it back upstream (`to` 0).
   *
   * @param to - Share of the reach to show at the end, 0..1.
   * @param durationMs - Duration; 0 jumps there at once.
   */
  readonly animateRiver: (to: number, durationMs: number) => void;
  /**
   * Shows one scene's NDTI map (null: none, the corridor alone).
   *
   * @param file - The map's path in the reach's folder (`maps/<key>.png`).
   */
  readonly showScene: (file: string | null) => void;
  /**
   * Sets what the gauge marker says (null hides its value).
   *
   * @param label - The value and its caption.
   */
  readonly setGauge: (label: GaugeLabel | null) => void;
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

const SOURCE = {
  imagery: "imagery",
  imageryBase: "imagery-base",
  terrain: "terrain",
  hillshade: "hillshade",
  reach: "reach",
  ndti: "ndti",
};
const LAYER = {
  hillshade: "hillshade",
  water: "reach-water",
  glow: "reach-glow",
  edge: "reach-edge",
  ndti: "reach-ndti",
  parts: "reach-parts",
  window: "reach-window",
};
const KIND = (kind: string): FilterSpecification => ["==", ["get", "kind"], kind];

// A zoom-driven interpolation from flat [zoom, value, zoom, value, ...] pairs.
function byZoom(pairs: readonly number[]): ExpressionSpecification {
  return ["interpolate", ["exponential", 1.4], ["zoom"], ...pairs] as ExpressionSpecification;
}

interface TileUrls {
  readonly imagery: string;
  readonly dem: string;
}

function buildStyle(reach: ReachData, tiles: TileUrls): StyleSpecification {
  const dem: RasterDEMSourceSpecification = {
    type: "raster-dem",
    tiles: [tiles.dem],
    encoding: TERRAIN.encoding,
    tileSize: TERRAIN.tileSize,
    maxzoom: TERRAIN.maxzoom,
  };
  const { imagery, hillshade, corridor, sky } = MAP_LOOK;
  const grading = {
    "raster-saturation": imagery.saturation,
    "raster-contrast": imagery.contrast,
    "raster-brightness-max": imagery.brightnessMax,
  };
  return {
    version: 8,
    sources: {
      // First, so its few tiles head the request queue: a tile still loading when the flight
      // moves on is dropped, not cached for the way back.
      [SOURCE.imageryBase]: {
        type: "raster",
        tiles: [tiles.imagery],
        tileSize: IMAGERY.tileSize,
        maxzoom: IMAGERY.underlayMaxzoom,
      },
      [SOURCE.imagery]: {
        type: "raster",
        tiles: [tiles.imagery],
        tileSize: IMAGERY.tileSize,
        maxzoom: IMAGERY.maxzoom,
      },
      [SOURCE.terrain]: dem,
      [SOURCE.hillshade]: { ...dem },
      [SOURCE.reach]: {
        type: "geojson",
        data: reach.geometry ?? {
          type: "FeatureCollection",
          features: [],
        },
      },
    },
    layers: [
      { id: "background", type: "background", paint: { "background-color": MAP_LOOK.background } },
      {
        id: "imagery-base",
        type: "raster",
        source: SOURCE.imageryBase,
        paint: { ...grading, "raster-fade-duration": 0 },
      },
      {
        id: "imagery",
        type: "raster",
        source: SOURCE.imagery,
        paint: { ...grading, "raster-fade-duration": imagery.fadeDurationMs },
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
        id: LAYER.water,
        type: "fill",
        source: SOURCE.reach,
        filter: KIND("river"),
        paint: { "fill-color": corridor.water, "fill-opacity": 0 },
      },
      {
        id: LAYER.glow,
        type: "line",
        source: SOURCE.reach,
        filter: KIND("river"),
        layout: { "line-join": "round" },
        paint: {
          "line-color": corridor.glow,
          "line-width": byZoom(corridor.glowWidth),
          "line-blur": byZoom(corridor.glowBlur),
          "line-opacity": 0,
        },
      },
      {
        id: LAYER.edge,
        type: "line",
        source: SOURCE.reach,
        filter: KIND("river"),
        layout: { "line-join": "round" },
        paint: { "line-color": corridor.edge, "line-width": 1, "line-opacity": 0 },
      },
      {
        id: LAYER.parts,
        type: "line",
        source: SOURCE.reach,
        filter: KIND("subreach"),
        layout: { "line-join": "round" },
        paint: {
          "line-color": corridor.parts,
          "line-width": 1.2,
          "line-dasharray": [2, 2],
          "line-opacity": 0,
        },
      },
      {
        id: LAYER.window,
        type: "line",
        source: SOURCE.reach,
        filter: KIND("window"),
        layout: { "line-join": "round" },
        paint: { "line-color": corridor.window, "line-width": 1.6, "line-opacity": 0 },
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

// The corridor's bounds (the river polygons), else a small box around the case's centre.
function reachBounds(reach: ReachData, center: LngLat): LngLatBounds {
  const bounds = new LngLatBounds();
  for (const feature of reach.geometry?.features ?? []) {
    if (feature.properties.kind === "river" && feature.geometry.type === "MultiPolygon") {
      for (const polygon of feature.geometry.coordinates) {
        for (const point of polygon[0] ?? []) {
          bounds.extend([point[0], point[1]]);
        }
      }
    }
  }
  if (bounds.isEmpty()) {
    bounds.extend([center[0] - 0.05, center[1] - 0.05]);
    bounds.extend([center[0] + 0.05, center[1] + 0.05]);
  }
  return bounds;
}

function gaugePoint(reach: ReachData): LngLat | null {
  const station = reach.geometry?.features.find((f) => f.properties.kind === "station");
  return station?.geometry.type === "Point" ? station.geometry.coordinates : null;
}

// The packed bytes of one map, decoded without color management or premultiplied alpha.
async function decodeMap(url: string): Promise<ImageData> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${url}: ${String(response.status)}`);
  }
  const bitmap = await createImageBitmap(await response.blob(), {
    colorSpaceConversion: "none",
    premultiplyAlpha: "none",
  });
  const canvas = document.createElement("canvas");
  canvas.width = bitmap.width;
  canvas.height = bitmap.height;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (context === null) {
    throw new Error("no 2D canvas");
  }
  context.drawImage(bitmap, 0, 0);
  bitmap.close();
  return context.getImageData(0, 0, canvas.width, canvas.height);
}

function gaugeElement(): { root: HTMLElement; value: HTMLElement; caption: HTMLElement } {
  const root = document.createElement("div");
  root.className = "case-gauge";
  root.innerHTML =
    '<span class="case-gauge__pulse"></span><span class="case-gauge__dot"></span>' +
    '<span class="case-gauge__label"><span class="case-gauge__value"></span>' +
    '<span class="case-gauge__caption"></span></span>';
  const value = root.querySelector<HTMLElement>(".case-gauge__value");
  const caption = root.querySelector<HTMLElement>(".case-gauge__caption");
  if (value === null || caption === null) {
    throw new Error("gauge marker");
  }
  return { root, value, caption };
}

/**
 * Creates the case map inside `container`. The map is not interactive: the flythrough drives it.
 * If the elevation tiles fail, it drops the terrain and the hillshade and carries on; if the
 * imagery fails, the dark background, the river and the panels still show.
 *
 * @param container - Element MapLibre takes over; it must already have its final size.
 * @param options - Case, data, starting pose and tile mode.
 * @returns The map handle.
 */
export async function createCaseMap(
  container: HTMLElement,
  options: CreateCaseMapOptions,
): Promise<CaseMapHandle> {
  const { reachCase, reach, domain, start, handoffZoom } = options;
  // `import.meta.env.DEV` is a build-time constant: production drops the stub branch entirely.
  const stubTiles = import.meta.env.DEV && options.stubTiles;
  let tiles: TileUrls = { imagery: IMAGERY.tiles, dem: TERRAIN.tiles };
  if (stubTiles) {
    const { registerStubTiles } = await import("./stubTiles.ts");
    registerStubTiles();
    tiles = { imagery: "stub://imagery/{z}/{x}/{y}", dem: "stub://dem/{z}/{x}/{y}" };
  }

  const center: [number, number] = [reachCase.center[0], reachCase.center[1]];
  const bounds = reachBounds(reach, reachCase.center);
  const map = new MapLibreMap({
    container,
    style: buildStyle(reach, tiles),
    center,
    zoom: handoffZoom,
    pitch: 0,
    bearing: 0,
    interactive: false,
    attributionControl: false,
    maxZoom: MAP_LOOK.maxZoom,
    maxPitch: 60,
    pixelRatio: Math.min(window.devicePixelRatio, 2),
  });

  // The final view: the corridor fitted into the panels' free area, then tilted.
  const framed = (frame: FinalFrame) => {
    const fitted = map.cameraForBounds(bounds, {
      padding: frame.padding,
      bearing: reachCase.bearing,
      maxZoom: MAP_LOOK.maxZoom,
    });
    const zoom = (fitted?.zoom ?? 11) + frame.zoomOffset - MAP_LOOK.pitchZoomLoss;
    return {
      center: fitted?.center ?? center,
      zoom,
      pitch: reachCase.pitch,
      bearing: reachCase.bearing,
      padding: frame.padding,
    };
  };
  if (start === "final") {
    map.jumpTo(framed({ padding: { top: 0, bottom: 0, left: 0, right: 0 }, zoomOffset: 0 }));
  }

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

  // The NDTI canvas: the packed map of the shown scene, colored up to the reveal.
  const canvas = document.createElement("canvas");
  canvas.width = reach.maps?.width ?? 1;
  canvas.height = reach.maps?.height ?? 1;
  const context = canvas.getContext("2d");
  let packed: ImageData | null = null;
  let colored: ImageData | null = null;
  let reveal = start === "final" ? 1 : 0;
  let shownFile: string | null = null;
  let revealFrame = 0;
  let animating = false;
  let sceneRequest = 0;
  const { corridor } = MAP_LOOK;

  function paint(): void {
    if (context === null) {
      return;
    }
    if (packed === null || reach.maps === null) {
      context.clearRect(0, 0, canvas.width, canvas.height);
    } else {
      colored ??= context.createImageData(packed.width, packed.height);
      colorize(packed.data, packed.width, colored.data, {
        domain,
        packed: reach.maps.encoding.r.ndti,
        reveal,
        feather: corridor.revealFeather,
        opacity: corridor.ndtiOpacity,
      });
      context.putImageData(colored, 0, 0);
    }
    const source = map.getSource<CanvasSource>(SOURCE.ndti);
    if (source !== undefined) {
      // A static canvas source is read once: a short play makes it pick up the new pixels.
      source.play();
      requestAnimationFrame(() => {
        if (!disposed && !animating) {
          source.pause();
        }
      });
    }
    const shown = Math.min(1, reveal * 1.4);
    if (map.getLayer(LAYER.water) !== undefined) {
      map.setPaintProperty(LAYER.water, "fill-opacity", corridor.waterOpacity * shown);
      map.setPaintProperty(LAYER.glow, "line-opacity", corridor.glowOpacity * shown);
      map.setPaintProperty(LAYER.edge, "line-opacity", corridor.edgeOpacity * shown);
      map.setPaintProperty(LAYER.parts, "line-opacity", corridor.partsOpacity * shown);
      map.setPaintProperty(LAYER.window, "line-opacity", shown);
    }
  }

  // The NDTI layer joins as soon as the style is parsed, not on `load` (which waits for every
  // imagery and terrain tile), so the fill shows during the flight.
  map.on("style.load", () => {
    if (reach.maps !== null) {
      const corners = reach.maps.corners.map((c) => [c[0], c[1]]) as [
        [number, number],
        [number, number],
        [number, number],
        [number, number],
      ];
      map.addSource(SOURCE.ndti, { type: "canvas", canvas, coordinates: corners, animate: false });
      map.addLayer(
        {
          id: LAYER.ndti,
          type: "raster",
          source: SOURCE.ndti,
          paint: { "raster-fade-duration": 0, "raster-resampling": "linear" },
        },
        LAYER.parts,
      );
    }
    paint();
  });

  // The gauge marker, at the station.
  const gauge = gaugeElement();
  const point = gaugePoint(reach);
  const marker =
    point === null
      ? null
      : new Marker({ element: gauge.root, anchor: "center" }).setLngLat([point[0], point[1]]);
  marker?.addTo(map);
  gauge.root.dataset.shown = "false";

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
      gauge.root.dataset.shown = String(target > 0);
      if (durationMs <= 0) {
        reveal = target;
        animating = false;
        paint();
        return;
      }
      const from = reveal;
      const startTime = performance.now();
      animating = true;
      const step = (now: number) => {
        const t = Math.min(1, (now - startTime) / durationMs);
        // Ease-out (sine): the fill slows down as it arrives.
        reveal = from + (target - from) * Math.sin((t * Math.PI) / 2);
        animating = t < 1;
        paint();
        if (t < 1) {
          revealFrame = requestAnimationFrame(step);
        }
      };
      revealFrame = requestAnimationFrame(step);
    },
    showScene(file) {
      if (disposed || file === shownFile) {
        return;
      }
      shownFile = file;
      sceneRequest += 1;
      const request = sceneRequest;
      if (file === null) {
        packed = null;
        paint();
        return;
      }
      decodeMap(`${reach.base}${file}`)
        .then((data) => {
          if (!disposed && request === sceneRequest) {
            packed = data;
            colored = null;
            paint();
          }
        })
        .catch((error: unknown) => {
          if (import.meta.env.DEV) {
            console.warn(`[case] ${file} could not be drawn.`, error);
          }
        });
    },
    setGauge(label) {
      gauge.value.textContent = label?.value ?? "";
      gauge.caption.textContent = label?.caption ?? "";
      gauge.root.dataset.empty = String(label === null || label.value === "");
    },
    project(lng, lat) {
      const projected = map.project([lng, lat]);
      return { x: projected.x, y: projected.y };
    },
    stats() {
      const mapCenter = map.getCenter();
      return {
        zoom: map.getZoom(),
        pitch: map.getPitch(),
        bearing: map.getBearing(),
        center: [mapCenter.lng, mapCenter.lat],
        terrain: map.getTerrain() !== null,
        reveal,
        scene: shownFile,
        ndtiLayer: map.getLayer(LAYER.ndti) !== undefined,
        ndtiDecoded: packed !== null,
        styleLoaded: map.isStyleLoaded(),
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
      marker?.remove();
      map.remove();
    },
  };
  return handle;
}
