// The case view: a MapLibre map of the study site under night shades, with the alert, legend and
// timeline panels. In a flythrough it mounts hidden at the top-down handoff pose, crossfades in over
// the globe on `go`, tilts onto the reach, draws the river and slides the panels in. The map module
// is loaded on demand (loadMap.ts) and created once per mount, StrictMode double mounts included.
import "@fontsource-variable/inter-tight";
import "@fontsource-variable/geist-mono";
import "../../styles/tokens.css";
import "./case.css";

import { useEffect, useEffectEvent, useRef, useState, type CSSProperties } from "react";

import { cubicBezier } from "../../lib/easing.ts";
import { FLIGHT, IMAGERY, MAP_LOOK, TERRAIN } from "./config.ts";
import { CASE_COPY } from "./content.ts";
import { loadCaseMap } from "./loadMap.ts";
import type { CaseMapHandle } from "./map.ts";
import { AlertCard } from "./panels/AlertCard.tsx";
import { Legend } from "./panels/Legend.tsx";
import { Timeline } from "./panels/Timeline.tsx";
import { markFlight } from "./qa.ts";
import type { CaseData } from "./types.ts";

/**
 * How the case view enters: `flight` starts the map at the handoff pose and flies in on `go`;
 * `direct` starts it on the final view with the river and the panels already shown.
 */
export type CaseEntrance = "flight" | "direct";

/** Props of {@link CaseView}. */
export interface CaseViewProps {
  /** The case to show. */
  readonly data: CaseData;
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
  /** Called by "Back to the globe". */
  readonly onBack: () => void;
}

interface CaseQAWindow extends Window {
  __caseQA?: {
    readonly stats: () => Record<string, unknown>;
    readonly project: CaseMapHandle["project"];
  };
}

type MapStatus = "loading" | "ready" | "failed";

const flyEase = cubicBezier(...FLIGHT.flyEase);

// `?tiles=stub` (development only) draws generated tiles instead of fetching real ones.
function wantsStubTiles(): boolean {
  return import.meta.env.DEV && new URLSearchParams(window.location.search).get("tiles") === "stub";
}

/**
 * Full-viewport case view: the map of the site, the alert, legend and timeline panels and the map
 * attribution. It stays inert until it has landed.
 *
 * @returns The case view.
 */
export function CaseView({
  data,
  entrance,
  handoffZoom,
  go,
  crossfadeMs,
  skip,
  onReady,
  onCrossfaded,
  onLanded,
  onBack,
}: CaseViewProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const handleRef = useRef<CaseMapHandle | null>(null);
  const [mapStatus, setMapStatus] = useState<MapStatus>("loading");
  const [crossfaded, setCrossfaded] = useState(false);
  const [panelsIn, setPanelsIn] = useState(false);
  const [flightLanded, setFlightLanded] = useState(false);

  const visible = go || skip;
  const shownAtOnce = skip || entrance === "direct";
  const panels = !visible ? "hidden" : shownAtOnce ? "shown" : panelsIn ? "in" : "hidden";
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
          data,
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
          created.jumpToFinal();
          created.revealRiver(0);
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
  }, [data, handoffZoom]);

  // Crossfade in; the caller removes what was underneath once it is done.
  useEffect(() => {
    if (!visible || skip || crossfadeMs <= 0) {
      return undefined;
    }
    markFlight("crossfade");
    const timer = window.setTimeout(() => {
      setCrossfaded(true);
      notifyCrossfaded();
    }, crossfadeMs);
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
    void handle?.flyToFinal(FLIGHT.flyMs, flyEase).then(() => {
      flightDone = true;
      land();
    });
    const start = performance.now();
    const step = (now: number) => {
      const t = (now - start) / FLIGHT.flyMs;
      if (!riverStarted && t >= FLIGHT.riverAt) {
        riverStarted = true;
        markFlight("river");
        handle?.revealRiver(MAP_LOOK.river.revealMs);
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
      handleRef.current?.jumpToFinal();
      handleRef.current?.revealRiver(0);
    }
  }, [skip]);

  useEffect(() => {
    if (landed) {
      notifyLanded();
    }
  }, [landed]);

  const style = { "--crossfade": `${String(crossfadeMs)}ms` } as CSSProperties;
  return (
    <section
      className="case-view"
      aria-labelledby="case-site-title"
      style={style}
      data-map={mapStatus}
      data-visible={visible}
      data-instant={skip || crossfadeMs === 0}
      data-haze={entrance === "flight" && go && !skip}
      data-panels={panels}
      inert={!landed}
    >
      <div className="case-view__map" ref={mapRef} aria-hidden="true" />
      <div className="case-view__shade case-view__shade--top" aria-hidden="true" />
      <div className="case-view__shade case-view__shade--bottom" aria-hidden="true" />
      <div className="case-view__haze" aria-hidden="true" />
      <div className="case-view__panels">
        <AlertCard data={data} headingRef={headingRef} onBack={onBack} />
        <Legend />
        <Timeline data={data} />
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
