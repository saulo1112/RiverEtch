// The case view: a MapLibre map of the reach under night shades, with the case file, legend,
// record and timeline panels and the optional wallet in the corner. In a flythrough it mounts
// hidden at the top-down handoff pose, crossfades in over the globe on `go`, tilts onto the reach,
// fills the river and slides the panels in. The map module is loaded on demand (loadMap.ts) and
// created once per mount, StrictMode double mounts included. Selecting a pass on the timeline
// redraws its NDTI map and updates the case file and the record.
import "@fontsource-variable/inter-tight";
import "@fontsource-variable/geist-mono";
import "../../styles/tokens.css";
import "./case.css";

import { useEffect, useEffectEvent, useMemo, useRef, useState, type CSSProperties } from "react";

import { cubicBezier } from "../../lib/easing.ts";
import type { ReachCase } from "../reaches/catalog.ts";
import { ndtiDomain } from "../reaches/colorize.ts";
import { defaultScene, mapFile, ndtiMedians, turbidity } from "../reaches/scene.ts";
import type { ReachData } from "../reaches/types.ts";
import { WalletControl } from "../wallet/WalletControl.tsx";
import { FLIGHT, IMAGERY, MAP_LOOK, RETURN, TERRAIN } from "./config.ts";
import { CASE_COPY, formatValue } from "./content.ts";
import { loadCaseMap } from "./loadMap.ts";
import type { CaseMapHandle, FinalFrame } from "./map.ts";
import { CaseFile } from "./panels/CaseFile.tsx";
import { Legend } from "./panels/Legend.tsx";
import { RecordPanel } from "./panels/RecordPanel.tsx";
import { Timeline } from "./panels/Timeline.tsx";
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
  for (const panel of root?.querySelectorAll<HTMLElement>(".case-panel") ?? []) {
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

/**
 * Full-viewport case view: the map of the reach, the case file, legend, record and timeline
 * panels, the wallet corner and the map attribution. It stays inert until it has landed.
 *
 * @returns The case view.
 */
export function CaseView({
  reachCase,
  reach,
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
  const headingRef = useRef<HTMLHeadingElement>(null);
  const handleRef = useRef<CaseMapHandle | null>(null);
  const [mapStatus, setMapStatus] = useState<MapStatus>("loading");
  const [crossfaded, setCrossfaded] = useState(false);
  const [panelsIn, setPanelsIn] = useState(false);
  const [flightLanded, setFlightLanded] = useState(false);
  const [selected, setSelected] = useState(() => defaultScene(reach.series));
  const domain = useMemo(() => ndtiDomain(ndtiMedians(reach.series)), [reach.series]);
  const row = reach.series[selected] ?? null;

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
    headingRef.current?.focus({ preventScroll: true });
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

  // The selected pass: its NDTI map and the gauge's label.
  useEffect(() => {
    const handle = handleRef.current;
    if (handle === null || row === null) {
      return;
    }
    handle.showScene(mapFile(reach, row));
    const estimate = turbidity(row);
    const caption = reach.info.station.id.replace("USGS-", "USGS ");
    handle.setGauge({
      value:
        typeof estimate?.value === "number"
          ? `${formatValue(estimate.value)} ${estimate.unit}`
          : "",
      caption,
    });
  }, [reach, row, mapStatus]);

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
  } as CSSProperties;
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
      data-capture={wantsThumbnailCapture() ? "thumb" : undefined}
      inert={!landed || exit !== null}
    >
      <div className="case-view__map" ref={mapRef} aria-hidden="true" />
      <div className="case-view__shade case-view__shade--top" aria-hidden="true" />
      <div className="case-view__shade case-view__shade--bottom" aria-hidden="true" />
      <div className="case-view__haze" aria-hidden="true" />
      {mapStatus === "failed" ? (
        <p className="case-view__note">{CASE_COPY.mapUnavailable}</p>
      ) : null}
      <div className="case-view__panels">
        <CaseFile
          reachCase={reachCase}
          reach={reach}
          row={row}
          headingRef={headingRef}
          onBack={onBack}
        />
        <div className="case-side">
          {/* Outside the panels' frame (finalFrame): on phones it sits on the Back row. */}
          <div className="case-corner">
            <WalletControl variant="corner" />
          </div>
          <Legend />
          <RecordPanel reach={reach} row={row} />
        </div>
        <Timeline reach={reach} selected={selected} onSelect={setSelected} />
      </div>
      <p className="case-view__attribution">
        <a href={IMAGERY.homepage} target="_blank" rel="noopener noreferrer">
          {IMAGERY.attribution}
          <span className="case-visually-hidden"> {CASE_COPY.externalHint}</span>
        </a>
        {" · "}
        {TERRAIN.attribution}
      </p>
    </section>
  );
}
