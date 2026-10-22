// The case view: a MapLibre map of the reach under night shades, with the case file, legend,
// record and timeline panels, the map's toolbar and controls, and the optional wallet in the
// corner. In a flythrough it mounts hidden at the top-down handoff pose, crossfades in over the
// globe on `go`, tilts onto the reach, fills the river and slides the panels in. Once landed the
// map can be explored like a satellite viewer's: layers, a pixel inspector, the profile along the
// river, the pass's statistics, a time-lapse of the year and two passes compared side by side. The
// map module is loaded on demand (loadMap.ts) and created once per mount, StrictMode double mounts
// included.
import { focusForVisitor } from "../ui/modality.ts";
import "@fontsource-variable/inter-tight";
import "@fontsource-variable/geist-mono";
import "../../styles/tokens.css";
import "./case.css";

import { useEffect, useEffectEvent, useMemo, useRef, useState, type CSSProperties } from "react";

import { cubicBezier } from "../../lib/easing.ts";
import { classTable, riverLength, windowAt } from "../reaches/along.ts";
import { passStats, profile } from "../reaches/analysis.ts";
import type { ReachCase } from "../reaches/catalog.ts";
import { ndtiDomain } from "../reaches/colorize.ts";
import {
  defaultScene,
  defaultThermal,
  isOutside,
  isUngauged,
  mapFile,
  ndtiMedians,
  photoFile,
  sceneKey,
  turbidity,
} from "../reaches/scene.ts";
import type { ReachData } from "../reaches/types.ts";
import { FLIGHT, IMAGERY, MAP_LOOK, RETURN, TERRAIN } from "./config.ts";
import { CASE_COPY, formatDate, formatValue } from "./content.ts";
import { loadCaseMap } from "./loadMap.ts";
import type {
  CameraState,
  CaseMapHandle,
  CompareHandle,
  FinalFrame,
  HoverInfo,
  LayerMode,
  Overlays,
} from "./map.ts";
import { CaseFile } from "./panels/CaseFile.tsx";
import { GuidedTour } from "./panels/GuidedTour.tsx";
import { Legend } from "./panels/Legend.tsx";
import { Inspector, MapControls, ScaleBar } from "./panels/MapControls.tsx";
import { MapToolbar } from "./panels/MapToolbar.tsx";
import { RecordPanel } from "./panels/RecordPanel.tsx";
import { Timeline, type BottomTab } from "./panels/Timeline.tsx";
import { markFlight } from "./qa.ts";

/**
 * How the case view enters: `flight` starts the map at the handoff pose and flies in on `go`;
 * `direct` starts it on the final view with the river and the panels already shown.
 */
export type CaseEntrance = "flight" | "direct";

/**
 * How the case view leaves on "Back to your cases": `flight` slides the panels out, empties the
 * river and eases the map back to the top-down handoff pose; `fade` just waits to fade out
 * (reduced motion).
 */
export type CaseExit = "flight" | "fade";

/** Props of {@link CaseView}. */
export interface CaseViewProps {
  /** The case to show. */
  readonly reachCase: ReachCase;
  /** Its data. */
  readonly reach: ReachData;
  /** The pass to open on (its acquisition key; the latest with a value when absent). */
  readonly initialPass?: string | null;
  /** How the view enters. */
  readonly entrance: CaseEntrance;
  /** Zoom of the top-down handoff pose (`flight`). */
  readonly handoffZoom: number;
  /** Show the view: crossfade in and, for `flight`, start the map flight. */
  readonly go: boolean;
  /** Duration of the crossfade in, in milliseconds (0: at once). */
  readonly crossfadeMs: number;
  /** Jump straight to the landed state (Skip, Esc). */
  readonly skip: boolean;
  /** The map can be shown: its first `idle`, the ready timeout, or a failed map. */
  readonly onReady?: () => void;
  /** The crossfade in has finished, so whatever was underneath can go. */
  readonly onCrossfaded?: () => void;
  /** Landed: final pose, river and panels shown, focus on the site heading. */
  readonly onLanded?: () => void;
  /** Called by "Back to your cases". */
  readonly onBack: () => void;
  /** The way back has started (null: staying). */
  readonly exit?: CaseExit | null;
  /** Handoff zoom for the way back, matching the globe's top-down view for this viewport. */
  readonly exitZoom?: number;
  /** Fade out over `fadeOutMs`, revealing the globe underneath. */
  readonly fadeOut?: boolean;
  /** Duration of the fade out, in milliseconds. */
  readonly fadeOutMs?: number;
  /** The exit is done: the map is back at the handoff pose (or there was nothing to move). */
  readonly onExitReady?: () => void;
  /** The fade out has finished; the view can be unmounted. */
  readonly onFadedOut?: () => void;
}

interface CaseQAWindow extends Window {
  __caseQA?: {
    readonly stats: () => Record<string, unknown>;
    readonly project: CaseMapHandle["project"];
  };
}

type MapStatus = "loading" | "ready" | "failed";

const flyEase = cubicBezier(...FLIGHT.flyEase);
const zoomOutEase = cubicBezier(...RETURN.zoomOutEase);
// The time-lapse's pace, per pass.
const PLAY_STEP_MS = 1100;

// The least free room the reach keeps between the panels, and the gap kept around panels.
const MIN_FREE = { width: 160, height: 140 };
const PANEL_GAP = 12;

// Shrinks two opposite insets proportionally so at least `min` px stay free between them.
function keepFree(a: number, b: number, size: number, min: number): [number, number] {
  const excess = a + b + min - size;
  if (excess <= 0 || a + b === 0) {
    return [a, b];
  }
  const keep = Math.max(0, 1 - excess / (a + b));
  return [a * keep, b * keep];
}

/**
 * Fits the final view around the panels. A panel in the left or right column insets that side;
 * a panel across the middle insets the top or the bottom, by the half it sits in. The map fits the
 * reach's corridor into what is left. Layout boxes are used, so the panels' hidden offset does not
 * count.
 *
 * @param root - The case view element (null before mount: no padding).
 * @returns Map padding in CSS pixels and a zoom offset.
 */
function finalFrame(root: HTMLElement | null): FinalFrame {
  const width = root?.clientWidth ?? window.innerWidth;
  const height = root?.clientHeight ?? window.innerHeight;
  let top = 0;
  let bottom = 0;
  let left = 0;
  let right = 0;
  for (const panel of root?.querySelectorAll<HTMLElement>(".case-panel[data-frame]") ?? []) {
    const panelLeft = panel.offsetLeft;
    const panelRight = panelLeft + panel.offsetWidth;
    const panelTop = panel.offsetTop;
    const panelBottom = panelTop + panel.offsetHeight;
    if (panelRight < width / 2) {
      left = Math.max(left, panelRight + PANEL_GAP);
    } else if (panelLeft > width / 2) {
      right = Math.max(right, width - panelLeft + PANEL_GAP);
    } else if (panelTop + panelBottom < height) {
      top = Math.max(top, panelBottom + PANEL_GAP);
    } else {
      bottom = Math.max(bottom, height - panelTop + PANEL_GAP);
    }
  }
  [left, right] = keepFree(left, right, width, MIN_FREE.width);
  [top, bottom] = keepFree(top, bottom, height, MIN_FREE.height);
  return { padding: { top, bottom, left, right }, zoomOffset: 0 };
}

// `?tiles=stub` (development only) draws generated tiles instead of fetching real ones.
function wantsStubTiles(): boolean {
  return import.meta.env.DEV && new URLSearchParams(window.location.search).get("tiles") === "stub";
}

// `?capture=thumb` (development only, with `?view=case`): the landed view without its motion,
// for web/scripts/capture-case-thumbnail.mjs.
function wantsThumbnailCapture(): boolean {
  return (
    import.meta.env.DEV && new URLSearchParams(window.location.search).get("capture") === "thumb"
  );
}

// The imagery's and the terrain's credits, as their licences ask.
function MapSources() {
  return (
    <>
      <a href={IMAGERY.homepage} target="_blank" rel="noopener noreferrer">
        {IMAGERY.attribution}
        <span className="case-visually-hidden"> {CASE_COPY.externalHint}</span>
      </a>
      {" · "}
      {TERRAIN.attribution}
    </>
  );
}

/**
 * Full-viewport case view: the map of the reach, the case file, legend, record and timeline
 * panels, the map's tools, the wallet corner and the map attribution. It stays inert until it has
 * landed.
 *
 * @returns The case view.
 */
export function CaseView({
  reachCase,
  reach,
  initialPass = null,
  entrance,
  handoffZoom,
  go,
  crossfadeMs,
  skip,
  onReady,
  onCrossfaded,
  onLanded,
  onBack,
  exit = null,
  exitZoom = handoffZoom,
  fadeOut = false,
  fadeOutMs = RETURN.crossfadeMs,
  onExitReady,
  onFadedOut,
}: CaseViewProps) {
  const rootRef = useRef<HTMLElement>(null);
  const mapRef = useRef<HTMLDivElement>(null);
  const compareRef = useRef<HTMLDivElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const handleRef = useRef<CaseMapHandle | null>(null);
  const [mapStatus, setMapStatus] = useState<MapStatus>("loading");
  const [crossfaded, setCrossfaded] = useState(false);
  const [panelsIn, setPanelsIn] = useState(false);
  const [flightLanded, setFlightLanded] = useState(false);
  const [selected, setSelected] = useState(() => {
    const index = reach.series.findIndex((row) => sceneKey(row) === initialPass);
    return index >= 0 ? index : defaultScene(reach.series);
  });
  // The river's turbidity class, stretch by stretch, where the reach has it; else its NDTI.
  const [mode, setMode] = useState<LayerMode>(() =>
    reach.along != null && reach.along.passes.length > 0 ? "class" : "ndti",
  );
  const [opacity, setOpacity] = useState(1);
  const [overlays, setOverlays] = useState<Overlays>({ outline: true, window: true });
  const [terrain3d, setTerrain3d] = useState(true);
  const [hover, setHover] = useState<HoverInfo | null>(null);
  const [camera, setCamera] = useState<CameraState>({
    bearing: reachCase.bearing,
    pitch: reachCase.pitch,
    metresPerPixel: 20,
  });
  const [scene, setScene] = useState<{ file: string; data: ImageData } | null>(null);
  const [playing, setPlaying] = useState(false);
  const [compareWith, setCompareWith] = useState<number | null>(null);
  const [split, setSplit] = useState(0.5);
  const [tab, setTab] = useState<BottomTab>("quality");
  const [touring, setTouring] = useState(false);
  const tourTab = useRef<BottomTab>("quality"); // the tab to show again when the tour ends
  const [thermalSelected, setThermalSelected] = useState(() =>
    defaultThermal(reach.thermal?.series ?? []),
  );
  const [probe, setProbe] = useState<number | null>(null);
  const domain = useMemo(() => ndtiDomain(ndtiMedians(reach.series)), [reach.series]);
  const row = reach.series[selected] ?? null;
  const thermalRow =
    thermalSelected === null ? null : (reach.thermal?.series[thermalSelected] ?? null);
  const file = row === null ? null : mapFile(reach, row);
  const photo = row === null ? null : photoFile(reach, row);

  // The selected pass's profile and statistics, once its map is decoded.
  const sceneData = scene !== null && scene.file === file ? scene.data : null;
  const analysed = useMemo(
    () =>
      sceneData === null || reach.maps === null
        ? null
        : {
            profile: profile(reach.maps, sceneData.data),
            stats: passStats(reach.maps, sceneData.data, domain),
          },
    [sceneData, reach.maps, domain],
  );

  const visible = (go || skip) && !fadeOut;
  const shownAtOnce = skip || entrance === "direct";
  const panels =
    exit !== null
      ? "out"
      : !visible
        ? "hidden"
        : shownAtOnce
          ? "shown"
          : panelsIn
            ? "in"
            : "hidden";
  const landed =
    skip || (entrance === "direct" ? visible && (crossfadeMs === 0 || crossfaded) : flightLanded);

  const startsOnFinal = useEffectEvent(() => entrance === "direct" || skip);
  const notifyReady = useEffectEvent(() => {
    markFlight("map-ready");
    onReady?.();
  });
  const notifyCrossfaded = useEffectEvent(() => {
    markFlight("crossfaded");
    onCrossfaded?.();
  });
  const notifyExitReady = useEffectEvent(() => {
    markFlight("map-at-handoff");
    onExitReady?.();
  });
  const notifyFadedOut = useEffectEvent(() => {
    markFlight("faded-out");
    onFadedOut?.();
  });
  const notifyLanded = useEffectEvent(() => {
    markFlight("landed");
    focusForVisitor(headingRef.current);
    onLanded?.();
  });

  // The map, created once per mount.
  useEffect(() => {
    const container = mapRef.current;
    if (container === null) {
      return undefined;
    }
    const mount = new AbortController();
    // A call, not a property read: TypeScript would keep a narrowed `aborted` across awaits.
    const live = () => !mount.signal.aborted;
    let handle: CaseMapHandle | null = null;

    loadCaseMap()
      .then(async ({ createCaseMap }) => {
        if (!live()) {
          return;
        }
        const created = await createCaseMap(container, {
          reachCase,
          reach,
          domain,
          start: startsOnFinal() ? "final" : "handoff",
          handoffZoom,
          stubTiles: wantsStubTiles(),
          onHover: setHover,
          onScene: (shown, data) => {
            setScene({ file: shown, data });
          },
          onCamera: setCamera,
        });
        if (!live()) {
          created.dispose();
          return;
        }
        handle = created;
        handleRef.current = created;
        if (import.meta.env.DEV) {
          (window as CaseQAWindow).__caseQA = { stats: created.stats, project: created.project };
        }
        // Skipped while the map was loading: it started at the handoff pose.
        if (startsOnFinal()) {
          created.jumpToFinal(finalFrame(rootRef.current));
          created.animateRiver(1, 0);
        }
        await created.ready;
        if (live()) {
          setMapStatus("ready");
          notifyReady();
        }
      })
      .catch((error: unknown) => {
        if (import.meta.env.DEV) {
          console.error("[case] The map could not be created.", error);
        }
        if (live()) {
          setMapStatus("failed");
          notifyReady();
        }
      });

    return () => {
      mount.abort();
      handle?.dispose();
      handleRef.current = null;
      if (import.meta.env.DEV) {
        delete (window as CaseQAWindow).__caseQA;
      }
    };
  }, [reachCase, reach, domain, handoffZoom]);

  // The selected pass: its maps and the gauge's label.
  useEffect(() => {
    const handle = handleRef.current;
    if (handle === null || row === null) {
      return;
    }
    handle.showScene(file, photo);
    const estimate = turbidity(row);
    // A reach with no gauge labels its window with the pass's class, never a value.
    const cls = estimate?.fnuClass ?? null;
    handle.setGauge({
      value:
        typeof estimate?.value === "number"
          ? `${formatValue(estimate.value)} ${estimate.unit}`
          : cls === null
            ? ""
            : CASE_COPY.ungauged.classes[cls],
      caption: isUngauged(reach)
        ? CASE_COPY.ungauged.mapCaption
        : reach.info.station.id.replace("USGS-", "USGS station "),
    });
  }, [reach, row, file, photo, mapStatus]);

  // Once landed, the map is the user's; the URL names the pass (a link opens it).
  useEffect(() => {
    handleRef.current?.setInteractive(landed && exit === null);
  }, [landed, exit, mapStatus]);
  useEffect(() => {
    if (!landed || row === null || wantsThumbnailCapture()) {
      return;
    }
    const url = new URL(window.location.href);
    url.searchParams.set("case", reachCase.id);
    url.searchParams.set("pass", sceneKey(row));
    window.history.replaceState(null, "", url);
  }, [landed, row, reachCase.id]);

  // The map's layers follow the toolbar; a pass with no classes along the river shows its NDTI.
  const shownMode: LayerMode =
    mode === "class" &&
    !(reach.along?.passes.some((p) => p.sceneId === reach.series[selected]?.sceneId) ?? false)
      ? "ndti"
      : mode;
  useEffect(() => {
    handleRef.current?.setLayer(shownMode, opacity);
  }, [shownMode, opacity, mapStatus]);
  // The selected pass's classes along the river, by place along the reach (the Turbidity layer).
  const length = useMemo(() => riverLength(reach), [reach]);
  const passOf = (index: number | null) =>
    index === null
      ? null
      : (reach.along?.passes.find((p) => p.sceneId === reach.series[index]?.sceneId) ?? null);
  const classes = useMemo(
    () => (reach.along == null ? null : classTable(reach.along, passOf(selected), length)),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- passOf reads only reach and selected
    [reach, selected, length],
  );
  useEffect(() => {
    handleRef.current?.setClasses(classes);
  }, [classes, mapStatus]);
  useEffect(() => {
    handleRef.current?.setOverlays(overlays);
  }, [overlays, mapStatus]);
  const firstTerrain = useRef(true);
  useEffect(() => {
    if (firstTerrain.current) {
      firstTerrain.current = false;
      return;
    }
    handleRef.current?.setTerrain3d(terrain3d);
  }, [terrain3d]);
  useEffect(() => {
    handleRef.current?.setProbe(probe);
  }, [probe]);

  // The time-lapse: the next pass every step, looping over the year.
  useEffect(() => {
    if (!playing) {
      return undefined;
    }
    const timer = window.setInterval(() => {
      setSelected((index) => (index + 1) % Math.max(1, reach.series.length));
    }, PLAY_STEP_MS);
    return () => {
      window.clearInterval(timer);
    };
  }, [playing, reach.series.length]);

  // Compare: a synchronised copy of the map, right of the split, showing the other pass. It closes
  // when the way back starts, so the flight out shows one map.
  const compareHandle = useRef<CompareHandle | null>(null);
  const comparing = compareWith !== null && mapStatus === "ready" && exit === null;
  useEffect(() => {
    const element = compareRef.current;
    const handle = handleRef.current;
    if (!comparing || element === null || handle === null) {
      return undefined;
    }
    const copy = handle.compare(element);
    compareHandle.current = copy;
    return () => {
      copy.dispose();
      compareHandle.current = null;
    };
  }, [comparing]);
  const other = compareWith === null ? null : (reach.series[compareWith] ?? null);
  useEffect(() => {
    if (other !== null) {
      compareHandle.current?.setScene(mapFile(reach, other), photoFile(reach, other));
    }
    compareHandle.current?.setLayer(shownMode, opacity);
    compareHandle.current?.setClasses(
      reach.along == null ? null : classTable(reach.along, passOf(compareWith), length),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps -- passOf reads only reach
  }, [comparing, other, reach, shownMode, opacity, compareWith, length]);

  // Crossfade in; the caller removes what was underneath once it is done.
  useEffect(() => {
    if (!visible || skip || crossfadeMs <= 0) {
      return undefined;
    }
    markFlight("crossfade");
    // A small margin past the CSS transition, so the globe never leaves before it is covered.
    const timer = window.setTimeout(() => {
      setCrossfaded(true);
      notifyCrossfaded();
    }, crossfadeMs + FLIGHT.crossfadeMarginMs);
    return () => {
      window.clearTimeout(timer);
    };
  }, [visible, skip, crossfadeMs]);

  // The flight: tilt and zoom onto the reach, the river at `riverAt`, the panels at `panelsAt`.
  useEffect(() => {
    if (entrance !== "flight" || !go || skip) {
      return undefined;
    }
    const handle = handleRef.current;
    let cancelled = false;
    let frame = 0;
    let flightDone = handle === null;
    let timelineDone = false;
    let riverStarted = false;
    let panelsStarted = false;
    const land = () => {
      if (!cancelled && flightDone && timelineDone) {
        setFlightLanded(true);
      }
    };
    void handle?.flyToFinal(FLIGHT.flyMs, flyEase, finalFrame(rootRef.current)).then(() => {
      flightDone = true;
      land();
    });
    const start = performance.now();
    const step = (now: number) => {
      const t = (now - start) / FLIGHT.flyMs;
      if (!riverStarted && t >= FLIGHT.riverAt) {
        riverStarted = true;
        markFlight("river");
        handle?.animateRiver(1, MAP_LOOK.corridor.revealMs);
      }
      if (!panelsStarted && t >= FLIGHT.panelsAt) {
        panelsStarted = true;
        markFlight("panels");
        setPanelsIn(true);
      }
      if (t >= 1) {
        timelineDone = true;
        land();
        return;
      }
      frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
    };
  }, [entrance, go, skip]);

  // Skip: straight to the final pose with the whole river.
  useEffect(() => {
    if (skip) {
      handleRef.current?.jumpToFinal(finalFrame(rootRef.current));
      handleRef.current?.animateRiver(1, 0);
    }
  }, [skip]);

  useEffect(() => {
    if (landed) {
      notifyLanded();
    }
  }, [landed]);

  // The way back: the panels slide out (CSS), the river empties upstream and the map eases back
  // to the top-down handoff pose, where the globe will take over.
  useEffect(() => {
    if (exit === null) {
      return undefined;
    }
    const handle = handleRef.current;
    let cancelled = false;
    let timer = 0;
    if (exit === "flight" && handle !== null) {
      handle.animateRiver(0, RETURN.riverOutMs);
      void handle.flyToHandoff(RETURN.zoomOutMs, zoomOutEase, exitZoom).then(() => {
        if (!cancelled) {
          notifyExitReady();
        }
      });
    } else {
      // Nothing to fly: let the panels clear first when they animate.
      timer = window.setTimeout(notifyExitReady, exit === "flight" ? RETURN.panelsOutMs : 0);
    }
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [exit, exitZoom]);

  // Fade out over the globe; the caller unmounts the view once it is gone.
  useEffect(() => {
    if (!fadeOut) {
      return undefined;
    }
    markFlight("fade-out");
    const timer = window.setTimeout(notifyFadedOut, fadeOutMs + FLIGHT.crossfadeMarginMs);
    return () => {
      window.clearTimeout(timer);
    };
  }, [fadeOut, fadeOutMs]);

  const style = {
    "--crossfade": `${String(fadeOut ? fadeOutMs : crossfadeMs)}ms`,
    "--split": `${(split * 100).toFixed(2)}%`,
  } as CSSProperties;
  const select = (index: number) => {
    setPlaying(false);
    setSelected(index);
  };
  return (
    <section
      ref={rootRef}
      className="case-view"
      aria-labelledby="case-site-title"
      style={style}
      data-map={mapStatus}
      data-visible={visible}
      data-instant={(skip || crossfadeMs === 0) && exit === null}
      data-haze={entrance === "flight" && go && !skip}
      data-haze-out={fadeOut && exit === "flight"}
      data-panels={panels}
      data-landed={landed && exit === null}
      data-capture={wantsThumbnailCapture() ? "thumb" : undefined}
      inert={!landed || exit !== null}
    >
      <div className="case-view__map" ref={mapRef} aria-hidden="true" />
      {comparing ? (
        <>
          <div className="case-view__compare" ref={compareRef} aria-hidden="true" />
          <div
            className="case-split"
            role="slider"
            tabIndex={0}
            aria-label={CASE_COPY.tools.compareHint}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(split * 100)}
            onPointerDown={(event) => {
              // No text selection (its labels turned blue) and no drag of selected text, which
              // takes the pointer from the slider and left it stuck.
              event.preventDefault();
              window.getSelection()?.removeAllRanges();
              event.currentTarget.setPointerCapture(event.pointerId);
            }}
            onDragStart={(event) => {
              event.preventDefault();
            }}
            onPointerMove={(event) => {
              if (event.currentTarget.hasPointerCapture(event.pointerId)) {
                setSplit(Math.min(0.95, Math.max(0.05, event.clientX / window.innerWidth)));
              }
            }}
            onKeyDown={(event) => {
              const step =
                event.key === "ArrowRight" ? 0.02 : event.key === "ArrowLeft" ? -0.02 : 0;
              if (step !== 0) {
                setSplit((s) => Math.min(0.95, Math.max(0.05, s + step)));
              }
            }}
          >
            <span className="case-split__label case-split__label--left">
              {CASE_COPY.compare.left} · {row === null ? "" : formatDate(row.date, true)}
            </span>
            <span className="case-split__grip" aria-hidden="true" />
            <span className="case-split__label case-split__label--right">
              {CASE_COPY.compare.right} · {other === null ? "" : formatDate(other.date, true)}
            </span>
          </div>
        </>
      ) : null}
      <div className="case-view__shade case-view__shade--top" aria-hidden="true" />
      <div className="case-view__shade case-view__shade--bottom" aria-hidden="true" />
      <div className="case-view__haze" aria-hidden="true" />
      {mapStatus === "failed" ? (
        <p className="case-view__note">{CASE_COPY.mapUnavailable}</p>
      ) : null}
      <Inspector
        hover={hover}
        reach={reach}
        stretchClass={
          shownMode !== "class" || hover?.reading == null || reach.along == null
            ? undefined
            : (passOf(selected)?.classes[
                windowAt(reach.along, hover.reading.place, length) ?? -1
              ] ?? null)
        }
      />
      {/* Under the guided tour (a modal dialog) the panels are inert: seen, not reachable. */}
      <div className="case-view__panels" inert={touring}>
        <CaseFile
          reachCase={reachCase}
          reach={reach}
          row={row}
          thermal={thermalRow}
          headingRef={headingRef}
          onBack={onBack}
          onTour={() => {
            tourTab.current = tab;
            setTouring(true);
          }}
          selected={selected}
          onSelect={select}
        />
        <MapToolbar
          reach={reach}
          mode={mode}
          onMode={setMode}
          photoAvailable={photo !== null}
          classAvailable={reach.along != null && passOf(selected) !== null}
          opacity={opacity}
          onOpacity={setOpacity}
          overlays={overlays}
          onOverlays={setOverlays}
          terrain3d={terrain3d}
          onTerrain3d={setTerrain3d}
          compareWith={compareWith}
          onCompare={setCompareWith}
          selected={selected}
        />
        <div className="case-side">
          <Legend mode={shownMode} ungauged={isUngauged(reach)} />
          <RecordPanel reach={reach} row={row} thermal={tab === "thermal" ? thermalRow : null} />
        </div>
        <MapControls
          bearing={camera.bearing}
          terrain3d={terrain3d}
          onZoom={(delta) => {
            handleRef.current?.zoomBy(delta);
          }}
          onNorth={() => {
            handleRef.current?.resetNorth();
          }}
          onTerrain3d={setTerrain3d}
        />
        <ScaleBar metresPerPixel={camera.metresPerPixel} hover={hover} />
        <Timeline
          reach={reach}
          selected={selected}
          compared={compareWith}
          onSelect={select}
          thermalSelected={thermalSelected}
          onThermalSelect={setThermalSelected}
          tab={tab}
          onTab={setTab}
          playing={playing}
          onPlaying={setPlaying}
          profile={analysed?.profile ?? null}
          stats={analysed?.stats ?? null}
          domain={domain}
          onProbe={setProbe}
        />
      </div>
      <GuidedTour
        open={touring && landed && exit === null}
        ungauged={isUngauged(reach)}
        outside={isOutside(reach)}
        onTab={setTab}
        onClose={() => {
          setTouring(false);
          setTab(tourTab.current);
        }}
      />
      {/* The map's sources: one line on a wide screen; a "Map sources" pill that opens them on a
          phone, where the whole line would take five rows. Only one of the two is ever shown. */}
      <p className="case-view__attribution">
        <MapSources />
      </p>
      <details className="case-view__sources">
        <summary>{CASE_COPY.mapSources}</summary>
        <p className="case-view__sources-text case-glass">
          <MapSources />
        </p>
      </details>
    </section>
  );
}
