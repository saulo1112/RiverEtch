// The case map: MapLibre over Sentinel-2 cloudless imagery and Terrarium terrain, with the reach's
// real corridor (geometry.geojson) filled and outlined, and the selected pass drawn over it: its
// NDTI pixel by pixel (maps/<key>.png, colored in the browser) or the pass in true color
// (maps/<key>.rgb.webp). The gauge sits on its window. Once landed the map can be explored, its
// layers switched, a pixel inspected and two passes compared side by side. Loaded on demand
// (loadMap.ts), so MapLibre and its CSS live in their own chunk.
import "maplibre-gl/dist/maplibre-gl.css";

import {
  LngLatBounds,
  MapLibreMap,
  Marker,
  type CanvasSource,
  type ExpressionSpecification,
  type FilterSpecification,
  type ImageSource,
  type RasterDEMSourceSpecification,
  type StyleSpecification,
} from "maplibre-gl";

import { pixelAt, readPixel, type PixelReading } from "../reaches/analysis.ts";
import type { ReachCase } from "../reaches/catalog.ts";
import { Colorizer } from "../reaches/colorize.ts";
import type { LngLat, ReachData } from "../reaches/types.ts";
import { IMAGERY, MAP_LOOK, TERRAIN } from "./config.ts";

/**
 * A marker that asks whether terrain hides it only once the camera settles (`moveend`, and
 * `setOpacity`). MapLibre's own check reads the depth buffer back from the GPU every 100 ms while
 * the camera moves, which stalls the frame (about 0.7 s over the flight onto a reach). At rest the
 * marker fades behind a hill exactly as before.
 */
class SettledMarker extends Marker {
  override _updateOpacity(force = false): void {
    if (force) {
      super._updateOpacity(true);
    }
  }
}

/** Where the camera starts: the top-down handoff pose, or directly on the final view. */
export type CaseMapStart = "handoff" | "final";

/** What the river shows: the pass's NDTI, the pass in true color, or nothing over the basemap. */
export type LayerMode = "ndti" | "photo" | "none";

// The overlays' opacities change at once (the reveal animates them itself, frame by frame). With
// MapLibre's default 300 ms transition, 3D terrain caches the layers drawn on the transition's first
// frame, nearly unchanged, so a switched-off outline stayed on the map until the next zoom.
const NOW = { duration: 0, delay: 0 };

/** The vector overlays that can be switched off. */
export interface Overlays {
  /** The corridor's fill, glow and edge. */
  readonly outline: boolean;
  /** The gauge's window. */
  readonly window: boolean;
}

/** What is under the cursor. */
export interface HoverInfo {
  /** Position in the map container, CSS px. */
  readonly x: number;
  readonly y: number;
  readonly lng: number;
  readonly lat: number;
  /** The pass's pixel there (null off the corridor or before the map is drawn). */
  readonly reading: PixelReading | null;
}

/** Where the camera is. */
export interface CameraState {
  readonly bearing: number;
  readonly pitch: number;
  /** Metres per CSS pixel at the centre. */
  readonly metresPerPixel: number;
}

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
  /** The cursor moved over the map (null: it left). */
  readonly onHover?: (info: HoverInfo | null) => void;
  /** A pass's packed map was decoded (for its profile and statistics). */
  readonly onScene?: (file: string, data: ImageData) => void;
  /** The camera moved (for the compass and the scale bar). */
  readonly onCamera?: (camera: CameraState) => void;
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

/** A second pass drawn on a synchronised copy of the map, shown right of a split. */
export interface CompareHandle {
  /**
   * Shows a pass on the compared side.
   *
   * @param file - Its NDTI map.
   * @param photo - Its true-color image.
   */
  readonly setScene: (file: string | null, photo: string | null) => void;
  /**
   * Follows the main map's layer choice.
   *
   * @param mode - What the river shows.
   * @param opacity - The layer's opacity.
   */
  readonly setLayer: (mode: LayerMode, opacity: number) => void;
  /** Removes the copy. */
  readonly dispose: () => void;
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
   * Shows one pass (null: none, the corridor alone).
   *
   * @param file - Its NDTI map (`maps/<key>.png`).
   * @param photo - Its true-color image (`maps/<key>.rgb.webp`), when drawn.
   */
  readonly showScene: (file: string | null, photo: string | null) => void;
  /**
   * Sets what the gauge marker says (null hides its value).
   *
   * @param label - The value and its caption.
   */
  readonly setGauge: (label: GaugeLabel | null) => void;
  /**
   * Lets the user pan, zoom, rotate and tilt (after landing), or not (during flights).
   *
   * @param on - Whether the map takes input.
   */
  readonly setInteractive: (on: boolean) => void;
  /**
   * Chooses what the river shows and how opaque it is.
   *
   * @param mode - NDTI, true color or nothing.
   * @param opacity - 0..1.
   */
  readonly setLayer: (mode: LayerMode, opacity: number) => void;
  /**
   * Switches the vector overlays.
   *
   * @param overlays - Which are shown.
   */
  readonly setOverlays: (overlays: Overlays) => void;
  /**
   * 3D (terrain, tilted) or 2D (flat, top-down).
   *
   * @param on - 3D.
   */
  readonly setTerrain3d: (on: boolean) => void;
  /**
   * Zooms in or out by a step.
   *
   * @param delta - Zoom levels (positive: in).
   */
  readonly zoomBy: (delta: number) => void;
  /**
   * Turns the map back to north (and the case's tilt).
   */
  readonly resetNorth: () => void;
  /**
   * Marks a place along the river (the profile's cursor), or clears it.
   *
   * @param place - 0 at the upstream anchor to 1 at the downstream one (null: none).
   */
  readonly setProbe: (place: number | null) => void;
  /**
   * Draws a second pass on a synchronised copy of the map inside `container` (compare mode).
   *
   * @param container - An element over the map, clipped by the caller.
   * @returns The copy's handle.
   */
  readonly compare: (container: HTMLElement) => CompareHandle;
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
  photo: "photo",
};
const LAYER = {
  hillshade: "hillshade",
  water: "reach-water",
  glow: "reach-glow",
  edge: "reach-edge",
  ndti: "reach-ndti",
  photo: "reach-photo",
  window: "reach-window",
};
const HANDLERS = [
  "scrollZoom",
  "boxZoom",
  "dragRotate",
  "dragPan",
  "keyboard",
  "doubleClickZoom",
  "touchZoomRotate",
  "touchPitch",
] as const;
const KIND = (kind: string): FilterSpecification => ["==", ["get", "kind"], kind];
const EARTH_CIRCUMFERENCE_M = 40_075_016.686;
type Corners = [[number, number], [number, number], [number, number], [number, number]];

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
        data: reach.geometry ?? { type: "FeatureCollection", features: [] },
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
        paint: { "fill-color": corridor.water, "fill-opacity": 0, "fill-opacity-transition": NOW },
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
          "line-opacity-transition": NOW,
        },
      },
      {
        id: LAYER.edge,
        type: "line",
        source: SOURCE.reach,
        filter: KIND("river"),
        layout: { "line-join": "round" },
        paint: {
          "line-color": corridor.edge,
          "line-width": 1,
          "line-opacity": 0,
          "line-opacity-transition": NOW,
        },
      },
      {
        id: LAYER.window,
        type: "line",
        source: SOURCE.reach,
        filter: KIND("window"),
        layout: { "line-join": "round" },
        paint: {
          "line-color": corridor.window,
          "line-width": 1.6,
          "line-opacity": 0,
          "line-opacity-transition": NOW,
        },
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

// The point at a place along the centreline (0..1 of the corridor's length), interpolated.
function centrelinePoint(reach: ReachData, place: number): LngLat | null {
  const features = reach.geometry?.features ?? [];
  const line = features.find((f) => f.properties.kind === "centreline");
  const river = features.find((f) => f.properties.kind === "river");
  const chain = (line?.properties as { chainageM?: readonly number[] } | undefined)?.chainageM;
  if (line?.geometry.type !== "LineString" || chain === undefined) {
    return null;
  }
  const coords = line.geometry.coordinates;
  const target = place * (river?.properties.lengthM ?? chain.at(-1) ?? 0);
  for (let k = 1; k < coords.length; k += 1) {
    const c0 = chain[k - 1] ?? 0;
    const c1 = chain[k] ?? 0;
    const a = coords[k - 1];
    const b = coords[k];
    if (a !== undefined && b !== undefined && target <= c1) {
      const t = c1 === c0 ? 0 : (target - c0) / (c1 - c0);
      return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
    }
  }
  return coords.at(-1) ?? null;
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

// How much of the true-color image's shorter side fades out at each edge.
const PHOTO_FEATHER = 0.06;

/**
 * The true-color image with its edges faded to transparent, so the pass's own photo blends into
 * the base map (a cloudless mosaic of other dates, darker) instead of sitting on it as a
 * hard-edged rectangle. The image's pixels are not changed inside the fade.
 *
 * @param url - The image (`maps/<key>.rgb.webp`).
 * @returns An object URL of the faded image (the caller revokes it), or the URL itself if the
 *   browser cannot draw it.
 */
async function featheredPhoto(url: string): Promise<string> {
  const image = new Image();
  image.decoding = "async";
  image.src = url;
  await image.decode();
  const canvas = document.createElement("canvas");
  const w = (canvas.width = image.naturalWidth);
  const h = (canvas.height = image.naturalHeight);
  const ctx = canvas.getContext("2d");
  if (ctx === null || w === 0 || h === 0) {
    return url;
  }
  ctx.drawImage(image, 0, 0);
  const edge = Math.max(1, Math.round(Math.min(w, h) * PHOTO_FEATHER));
  ctx.globalCompositeOperation = "destination-out";
  // One strip per edge, from fully cut at the border to untouched `edge` pixels in.
  const strip = (x0: number, y0: number, x1: number, y1: number, box: readonly number[]) => {
    const gradient = ctx.createLinearGradient(x0, y0, x1, y1);
    gradient.addColorStop(0, "rgb(0 0 0 / 1)");
    gradient.addColorStop(1, "rgb(0 0 0 / 0)");
    ctx.fillStyle = gradient;
    ctx.fillRect(box[0] ?? 0, box[1] ?? 0, box[2] ?? 0, box[3] ?? 0);
  };
  strip(0, 0, edge, 0, [0, 0, edge, h]);
  strip(w, 0, w - edge, 0, [w - edge, 0, edge, h]);
  strip(0, 0, 0, edge, [0, 0, w, edge]);
  strip(0, h, 0, h - edge, [0, h - edge, w, edge]);
  const blob = await new Promise<Blob | null>((resolve) => {
    canvas.toBlob(resolve, "image/webp", 0.92);
  });
  return blob === null ? url : URL.createObjectURL(blob);
}

/**
 * One map's pass layers: the NDTI canvas (colored up to the reveal) and the true-color image
 * (its edges faded), inserted under the gauge window's outline. Shared by the main map and its
 * compared copy.
 */
class PassLayers {
  readonly canvas = document.createElement("canvas");
  packed: ImageData | null = null;
  reveal: number;
  animating = false;
  /** What the river shows. */
  mode: LayerMode = "ndti";
  private readonly map: MapLibreMap;
  private readonly reach: ReachData;
  private readonly domain: readonly [number, number];
  private colored: ImageData | null = null;
  /** Recolors only what a new reveal changes (the bytes `colorize` would write). */
  private colorizer: Colorizer | null = null;
  private readonly context: CanvasRenderingContext2D | null;
  private opacity = 1;
  private photo: string | null = null;
  /** The faded copy of the photo on the map, and which photo it is. */
  private photoShown: { readonly photo: string; readonly url: string } | null = null;
  private request = 0;
  private file: string | null = null;
  private disposed = false;

  /**
   * Prepares the canvas for a map's passes.
   *
   * @param map - The map.
   * @param reach - The reach (its maps' index).
   * @param domain - The NDTI ramp's domain.
   * @param reveal - Share of the reach shown at first.
   */
  constructor(
    map: MapLibreMap,
    reach: ReachData,
    domain: readonly [number, number],
    reveal: number,
  ) {
    this.map = map;
    this.reach = reach;
    this.domain = domain;
    this.reveal = reveal;
    this.canvas.width = reach.maps?.width ?? 1;
    this.canvas.height = reach.maps?.height ?? 1;
    this.context = this.canvas.getContext("2d");
  }

  private corners(): Corners | null {
    return this.reach.maps === null
      ? null
      : (this.reach.maps.corners.map((c) => [c[0], c[1]]) as Corners);
  }

  /** Adds the NDTI canvas source and layer (once the style is parsed). */
  attach(): void {
    const coordinates = this.corners();
    if (coordinates === null || this.map.getSource(SOURCE.ndti) !== undefined) {
      return;
    }
    this.map.addSource(SOURCE.ndti, {
      type: "canvas",
      canvas: this.canvas,
      coordinates,
      animate: false,
    });
    this.map.addLayer(
      {
        id: LAYER.ndti,
        type: "raster",
        source: SOURCE.ndti,
        paint: { "raster-fade-duration": 0, "raster-resampling": "linear" },
      },
      LAYER.window,
    );
    this.applyLayer();
    this.paint();
  }

  /** Colors the packed map up to the reveal and hands the canvas to MapLibre. */
  paint(): void {
    const { context, packed, reach } = this;
    if (context === null) {
      return;
    }
    if (packed === null || reach.maps === null) {
      context.clearRect(0, 0, this.canvas.width, this.canvas.height);
    } else {
      this.colored ??= context.createImageData(packed.width, packed.height);
      this.colorizer ??= new Colorizer(packed.data, packed.width, this.colored.data, {
        domain: this.domain,
        packed: reach.maps.encoding.r.ndti,
        feather: MAP_LOOK.corridor.revealFeather,
        opacity: MAP_LOOK.corridor.ndtiOpacity,
      });
      const changed = this.colorizer.render(this.reveal);
      if (changed !== null) {
        context.putImageData(
          this.colored,
          0,
          0,
          changed.x,
          changed.y,
          changed.width,
          changed.height,
        );
      }
    }
    const source = this.map.getSource<CanvasSource>(SOURCE.ndti);
    if (source !== undefined) {
      // A static canvas source is read once: a short play makes it pick up the new pixels.
      source.play();
      requestAnimationFrame(() => {
        if (!this.disposed && !this.animating) {
          source.pause();
        }
      });
    }
  }

  /**
   * Loads a pass's NDTI map and true-color image.
   *
   * @param file - The NDTI map.
   * @param photo - The true-color image.
   * @param onData - Called with the decoded NDTI map.
   */
  show(file: string | null, photo: string | null, onData?: (data: ImageData) => void): void {
    if (this.disposed) {
      return;
    }
    if (file !== this.file) {
      this.file = file;
      this.request += 1;
      const request = this.request;
      if (file === null) {
        this.packed = null;
        this.colorizer = null;
        this.paint();
      } else {
        decodeMap(`${this.reach.base}${file}`)
          .then((data) => {
            if (!this.disposed && request === this.request) {
              this.packed = data;
              this.colored = null;
              this.colorizer = null;
              this.paint();
              onData?.(data);
            }
          })
          .catch((error: unknown) => {
            if (import.meta.env.DEV) {
              console.warn(`[case] ${file} could not be drawn.`, error);
            }
          });
      }
    }
    if (photo !== this.photo) {
      this.photo = photo;
      this.showPhoto();
    }
  }

  private showPhoto(): void {
    const coordinates = this.corners();
    const photo = this.photo;
    if (coordinates === null || photo === null || !this.map.isStyleLoaded()) {
      return;
    }
    if (this.photoShown?.photo === photo) {
      this.placePhoto(this.photoShown.url, coordinates);
      return;
    }
    const plain = `${this.reach.base}${photo}`;
    featheredPhoto(plain)
      .catch(() => plain)
      .then((url) => {
        if (this.disposed || this.photo !== photo) {
          if (url !== plain) {
            URL.revokeObjectURL(url);
          }
          return;
        }
        const before = this.photoShown?.url;
        this.photoShown = { photo, url };
        this.placePhoto(url, coordinates);
        if (before?.startsWith("blob:") === true) {
          URL.revokeObjectURL(before);
        }
      })
      .catch(() => undefined);
  }

  // Puts the (faded) photo on the map, under the corridor's fill.
  private placePhoto(url: string, coordinates: Corners): void {
    if (!this.map.isStyleLoaded()) {
      return;
    }
    const source = this.map.getSource<ImageSource>(SOURCE.photo);
    if (source === undefined) {
      this.map.addSource(SOURCE.photo, { type: "image", url, coordinates });
      this.map.addLayer(
        {
          id: LAYER.photo,
          type: "raster",
          source: SOURCE.photo,
          paint: { "raster-fade-duration": 0 },
        },
        LAYER.water,
      );
      this.applyLayer();
    } else {
      void source.updateImage({ url, coordinates });
    }
  }

  /**
   * Chooses the visible layer and its opacity.
   *
   * @param mode - NDTI, true color or none.
   * @param opacity - 0..1.
   */
  setLayer(mode: LayerMode, opacity: number): void {
    this.mode = mode;
    this.opacity = opacity;
    if (mode === "photo") {
      this.showPhoto();
    }
    this.applyLayer();
  }

  private applyLayer(): void {
    const { map } = this;
    if (map.getLayer(LAYER.ndti) !== undefined) {
      map.setLayoutProperty(LAYER.ndti, "visibility", this.mode === "ndti" ? "visible" : "none");
      map.setPaintProperty(LAYER.ndti, "raster-opacity", this.opacity);
    }
    if (map.getLayer(LAYER.photo) !== undefined) {
      map.setLayoutProperty(LAYER.photo, "visibility", this.mode === "photo" ? "visible" : "none");
      map.setPaintProperty(LAYER.photo, "raster-opacity", this.opacity);
    }
  }

  /** Stops painting. */
  dispose(): void {
    this.disposed = true;
    if (this.photoShown?.url.startsWith("blob:") === true) {
      URL.revokeObjectURL(this.photoShown.url);
    }
  }
}

/**
 * Creates the case map inside `container`. During flights the flythrough drives it; once landed
 * {@link CaseMapHandle.setInteractive} lets the user move it. If the elevation tiles fail, it drops
 * the terrain and the hillshade and carries on; if the imagery fails, the dark background, the
 * river and the panels still show.
 *
 * @param container - Element MapLibre takes over; it must already have its final size.
 * @param options - Case, data, starting pose, tile mode and callbacks.
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
    interactive: true,
    attributionControl: false,
    maxZoom: MAP_LOOK.maxZoom,
    maxPitch: 70,
    pixelRatio: Math.min(window.devicePixelRatio, 2),
  });
  // Input waits for the landing (setInteractive).
  for (const name of HANDLERS) {
    map[name].disable();
  }
  let interactive = false;
  let terrain3d = true;

  // The final view: the corridor fitted into the panels' free area, then tilted.
  let lastFrame: FinalFrame = { padding: { top: 0, bottom: 0, left: 0, right: 0 }, zoomOffset: 0 };
  const framed = (frame: FinalFrame) => {
    lastFrame = frame;
    const fitted = map.cameraForBounds(bounds, {
      padding: frame.padding,
      bearing: reachCase.bearing,
      maxZoom: MAP_LOOK.maxZoom,
    });
    const zoom = (fitted?.zoom ?? 11) + frame.zoomOffset - (terrain3d ? MAP_LOOK.pitchZoomLoss : 0);
    return {
      center: fitted?.center ?? center,
      zoom,
      pitch: terrain3d ? reachCase.pitch : 0,
      bearing: reachCase.bearing,
      padding: frame.padding,
    };
  };
  if (start === "final") {
    map.jumpTo(framed(lastFrame));
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

  const layers = new PassLayers(map, reach, domain, start === "final" ? 1 : 0);
  let overlays: Overlays = { outline: true, window: true };
  let revealFrame = 0;
  let shownFile: string | null = null;
  const { corridor } = MAP_LOOK;

  // The corridor's overlays follow the reveal and the user's toggles.
  function paintOverlays(): void {
    if (map.getLayer(LAYER.water) === undefined) {
      return;
    }
    const shown = Math.min(1, layers.reveal * 1.4);
    const on = (flag: boolean) => (flag ? shown : 0);
    // The true-color image shows the water itself: no dark fill over it.
    const water = layers.mode === "photo" ? 0 : corridor.waterOpacity;
    map.setPaintProperty(LAYER.water, "fill-opacity", water * on(overlays.outline));
    map.setPaintProperty(LAYER.glow, "line-opacity", corridor.glowOpacity * on(overlays.outline));
    map.setPaintProperty(LAYER.edge, "line-opacity", corridor.edgeOpacity * on(overlays.outline));
    map.setPaintProperty(LAYER.window, "line-opacity", on(overlays.window));
  }

  function paint(): void {
    layers.paint();
    paintOverlays();
  }

  // With 3D terrain, MapLibre draws these layers into a texture cached per terrain tile, and a
  // paint change alone does not always clear it: a toggle would show only after the next zoom.
  function redraw(): void {
    const terrain = map.terrain as typeof map.terrain | null;
    terrain?.tileManager.freeRtt();
    map.triggerRepaint();
  }

  // The NDTI layer joins as soon as the style is parsed, not on `load` (which waits for every
  // imagery and terrain tile), so the fill shows during the flight.
  map.on("style.load", () => {
    layers.attach();
    paintOverlays();
  });

  // The gauge marker, at the station.
  const gauge = gaugeElement();
  const point = gaugePoint(reach);
  const marker =
    point === null
      ? null
      : // Fully drawn even where MapLibre's terrain check calls it covered: the station sits on
        // the water, and a false "covered" left its label at a fifth of its opacity.
        new SettledMarker({
          element: gauge.root,
          anchor: "center",
          opacity: "1",
          opacityWhenCovered: "1",
        }).setLngLat([point[0], point[1]]);
  marker?.addTo(map);
  gauge.root.dataset.shown = "false";

  // The profile's cursor on the river.
  const probe = document.createElement("div");
  probe.className = "case-probe";
  const probeMarker = new SettledMarker({ element: probe, anchor: "center" });

  // The pixel under the cursor, at most once a frame.
  let hoverFrame = 0;
  map.on("mousemove", (event) => {
    if (!interactive || options.onHover === undefined) {
      return;
    }
    cancelAnimationFrame(hoverFrame);
    hoverFrame = requestAnimationFrame(() => {
      const { lng, lat } = event.lngLat;
      const pixel = reach.maps === null ? null : pixelAt(reach.maps, [lng, lat]);
      const reading =
        pixel === null || layers.packed === null || reach.maps === null
          ? null
          : readPixel(reach.maps, layers.packed.data, pixel.col, pixel.row);
      options.onHover?.({ x: event.point.x, y: event.point.y, lng, lat, reading });
    });
  });
  map.getCanvas().addEventListener("mouseleave", () => {
    cancelAnimationFrame(hoverFrame);
    options.onHover?.(null);
  });
  let cameraFrame = 0;
  map.on("move", () => {
    cancelAnimationFrame(cameraFrame);
    cameraFrame = requestAnimationFrame(() => {
      const lat = (map.getCenter().lat * Math.PI) / 180;
      options.onCamera?.({
        bearing: map.getBearing(),
        pitch: map.getPitch(),
        metresPerPixel: (EARTH_CIRCUMFERENCE_M * Math.cos(lat)) / (512 * 2 ** map.getZoom()),
      });
    });
  });

  let settleFlight: (() => void) | null = null;
  function endFlight(): void {
    const settle = settleFlight;
    settleFlight = null;
    settle?.();
  }
  // Ends the pending flight, whether it completes or is interrupted (`stop`, `jumpTo`).
  map.on("moveend", endFlight);

  const compares = new Set<CompareHandle>();
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
        layers.reveal = target;
        layers.animating = false;
        paint();
        return;
      }
      const from = layers.reveal;
      const startTime = performance.now();
      layers.animating = true;
      const step = (now: number) => {
        const t = Math.min(1, (now - startTime) / durationMs);
        // Ease-out (sine): the fill slows down as it arrives.
        layers.reveal = from + (target - from) * Math.sin((t * Math.PI) / 2);
        layers.animating = t < 1;
        paint();
        if (t < 1) {
          revealFrame = requestAnimationFrame(step);
        }
      };
      revealFrame = requestAnimationFrame(step);
    },
    showScene(file, photo) {
      shownFile = file;
      layers.show(file, photo, (data) => {
        if (file !== null) {
          options.onScene?.(file, data);
        }
      });
    },
    setGauge(label) {
      gauge.value.textContent = label?.value ?? "";
      gauge.caption.textContent = label?.caption ?? "";
      gauge.root.dataset.empty = String(label === null || label.value === "");
    },
    setInteractive(on) {
      interactive = on;
      for (const name of HANDLERS) {
        if (on) {
          map[name].enable();
        } else {
          map[name].disable();
        }
      }
    },
    setLayer(mode, opacity) {
      layers.setLayer(mode, opacity);
      paintOverlays();
      redraw();
      for (const copy of compares) {
        copy.setLayer(mode, opacity);
      }
    },
    setOverlays(next) {
      overlays = next;
      // The station spot is the window's outline and the marker over it (its dot, ring and label).
      gauge.root.dataset.hidden = String(!next.window);
      paintOverlays();
      redraw();
    },
    setTerrain3d(on) {
      terrain3d = on;
      if (terrainEnabled) {
        map.setTerrain(on ? { source: SOURCE.terrain, exaggeration: TERRAIN.exaggeration } : null);
        map.setLayoutProperty(LAYER.hillshade, "visibility", on ? "visible" : "none");
      }
      map.easeTo({ pitch: on ? reachCase.pitch : 0, duration: 600 });
    },
    zoomBy(delta) {
      map.easeTo({ zoom: map.getZoom() + delta, duration: 300 });
    },
    resetNorth() {
      map.easeTo({ ...framed(lastFrame), duration: 700 });
    },
    setProbe(place) {
      const at = place === null ? null : centrelinePoint(reach, place);
      if (at === null) {
        probeMarker.remove();
      } else {
        probeMarker.setLngLat([at[0], at[1]]).addTo(map);
      }
    },
    compare(element) {
      const copy = new MapLibreMap({
        container: element,
        style: buildStyle(reach, tiles),
        interactive: false,
        attributionControl: false,
        maxZoom: MAP_LOOK.maxZoom,
        maxPitch: 70,
        pixelRatio: Math.min(window.devicePixelRatio, 2),
        center: map.getCenter(),
        zoom: map.getZoom(),
        bearing: map.getBearing(),
        pitch: map.getPitch(),
      });
      const sync = () => {
        copy.jumpTo({
          center: map.getCenter(),
          zoom: map.getZoom(),
          bearing: map.getBearing(),
          pitch: map.getPitch(),
          padding: map.getPadding(),
        });
      };
      sync();
      const moving = map.on("move", sync);
      const passes = new PassLayers(copy, reach, domain, 1);
      let pending: { file: string | null; photo: string | null } | null = null;
      let layer: { mode: LayerMode; opacity: number } | null = null;
      copy.on("style.load", () => {
        if (!terrain3d) {
          copy.setTerrain(null);
        }
        passes.attach();
        if (layer !== null) {
          passes.setLayer(layer.mode, layer.opacity);
        }
        if (pending !== null) {
          passes.show(pending.file, pending.photo);
        }
        copy.setPaintProperty(LAYER.water, "fill-opacity", corridor.waterOpacity);
        copy.setPaintProperty(LAYER.edge, "line-opacity", corridor.edgeOpacity);
      });
      const compareHandle: CompareHandle = {
        setScene(file, photo) {
          pending = { file, photo };
          if (copy.isStyleLoaded()) {
            passes.show(file, photo);
          }
        },
        setLayer(mode, opacity) {
          layer = { mode, opacity };
          passes.setLayer(mode, opacity);
        },
        // Once: the main map's own dispose removes its copies before React's cleanup does.
        dispose() {
          if (!compares.delete(compareHandle)) {
            return;
          }
          moving.unsubscribe();
          passes.dispose();
          copy.remove();
        },
      };
      compares.add(compareHandle);
      return compareHandle;
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
        reveal: layers.reveal,
        scene: shownFile,
        ndtiLayer: map.getLayer(LAYER.ndti) !== undefined,
        ndtiDecoded: layers.packed !== null,
        interactive,
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
      cancelAnimationFrame(hoverFrame);
      cancelAnimationFrame(cameraFrame);
      for (const copy of [...compares]) {
        copy.dispose();
      }
      layers.dispose();
      settleReady();
      endFlight();
      marker?.remove();
      probeMarker.remove();
      map.remove();
    },
  };
  return handle;
}
