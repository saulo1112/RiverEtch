import { useCallback, useEffect, useRef, useState } from "react";

import { CaseView, type CaseEntrance } from "./features/case/CaseView.tsx";
import { FLIGHT, RETURN } from "./features/case/config.ts";
import { CASE_COPY } from "./features/case/content.ts";
import { loadCaseMap } from "./features/case/loadMap.ts";
import { markFlight } from "./features/case/qa.ts";
import { SkipButton } from "./features/case/SkipButton.tsx";
import { CAMERA, DIVE } from "./features/hero/config.ts";
import type { AscentHandle, DiveHandle } from "./features/hero/globe.ts";
import { handoffFrame } from "./features/hero/handoff.ts";
import { Hero, type HeroApi } from "./features/hero/Hero.tsx";
import { REACH_CASES, reachCase, type ReachCase } from "./features/reaches/catalog.ts";
import { loadReach } from "./features/reaches/data.ts";
import type { ReachData } from "./features/reaches/types.ts";

/**
 * What is on screen: the hero, the flythrough into the case, the landed case view, or the way
 * back to the globe.
 */
type View = "hero" | "flying" | "case" | "returning";

/** One trip into the case view; each one mounts a fresh case view. */
interface Flight {
  readonly id: number;
  /** The case it flies to. */
  readonly caseId: string;
  readonly entrance: CaseEntrance;
  readonly handoffZoom: number;
  readonly crossfadeMs: number;
}

/** One trip back to the globe. */
interface ReturnTrip {
  readonly id: number;
  /** False with reduced motion: no zoom-out and no rise, a short crossfade. */
  readonly motion: boolean;
  /** The map's zoom at the handoff, matching the globe's top-down view for this viewport. */
  readonly exitZoom: number;
}

// The globe's target for a case: its centre and handoff zoom.
function siteTarget(site: ReachCase): { lat: number; lng: number; zoom: number } {
  return { lat: site.center[1], lng: site.center[0], zoom: site.handoffZoom };
}

// A link to a pass (`?case=<id>&pass=<key>`, the case view writes it) opens that case directly;
// in development `?view=case` opens the featured one (`&reach=<id>` another).
const query = new URLSearchParams(window.location.search);
const linkedCase = query.get("case");
const openCaseView = linkedCase !== null || (import.meta.env.DEV && query.get("view") === "case");
const firstCase = reachCase(linkedCase ?? query.get("reach") ?? REACH_CASES[0]?.id ?? "");
const linkedPass = query.get("pass");
const initialFlight: Flight | null = openCaseView
  ? {
      id: 0,
      caseId: firstCase.id,
      entrance: "direct",
      handoffZoom: firstCase.handoffZoom,
      crossfadeMs: 0,
    }
  : null;

function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

// Fetches the map chunk early (pointer or focus on "Explore your cases" or "Open case"); a failure
// retries later.
function warmUp(): void {
  loadCaseMap().catch(() => undefined);
}

/**
 * Application root. "Open case" (on the hero's cases screen) flies from the hero globe into the
 * case view: the hero UI fades, the globe dives to the site while the map loads hidden, the map
 * crossfades in at the handoff (the hero and its WebGL scene go), tilts onto the reach, and the
 * panels slide in. Skip or Esc jumps to the end; reduced motion, or a hero without its 3D scene,
 * gets a short crossfade instead of the dive. The way back lands on the cases screen.
 *
 * @returns The root UI of the dApp.
 */
export function App() {
  const [view, setView] = useState<View>(openCaseView ? "case" : "hero");
  const [flight, setFlight] = useState<Flight | null>(initialFlight);
  const [heroGone, setHeroGone] = useState(openCaseView);
  // The dive is close enough to its top-down pose for the map to take over.
  const [atHandoff, setAtHandoff] = useState(false);
  const [mapReady, setMapReady] = useState(false);
  // `?view=case` starts landed, like a skipped flight.
  const [skipped, setSkipped] = useState(openCaseView);
  const [showSkip, setShowSkip] = useState(false);
  const [returned, setReturned] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  // The way back: the trip, the map at its handoff pose, the hero ready under it (or the wait
  // for it over).
  const [returnTrip, setReturnTrip] = useState<ReturnTrip | null>(null);
  const [exitReady, setExitReady] = useState(false);
  const [heroReady, setHeroReady] = useState(false);
  const [heroWaitOver, setHeroWaitOver] = useState(false);
  // The case of the current (or last) trip, and its data once loaded.
  const [caseId, setCaseId] = useState(firstCase.id);
  const [reach, setReach] = useState<ReachData | null>(null);
  const [reachFailed, setReachFailed] = useState(false);
  const site = reachCase(caseId);
  const heroRef = useRef<HeroApi>(null);
  const diveRef = useRef<DiveHandle | null>(null);
  const ascentRef = useRef<AscentHandle | null>(null);
  // Flags read by callbacks during the way back (no render depends on them).
  const tripRef = useRef({
    id: 0,
    heroReady: false,
    fadedOut: false,
    ascending: false,
    skip: false,
  });
  const flightCount = useRef(initialFlight === null ? 0 : 1);

  const explore = (openedId: string) => {
    if (view !== "hero") {
      return;
    }
    const opened = reachCase(openedId);
    setCaseId(opened.id);
    setReachFailed(false);
    flightCount.current += 1;
    const id = flightCount.current;
    markFlight("explore");
    const reduced = prefersReducedMotion();
    const target = siteTarget(opened);
    // Once per flight, and only for the current one (a newer flight or Back replaces it).
    let handedOver = false;
    const reachHandoff = () => {
      if (!handedOver && flightCount.current === id) {
        handedOver = true;
        markFlight("dive-handoff");
        setAtHandoff(true);
      }
    };
    const dive = reduced
      ? null
      : (heroRef.current?.dive(target, {
          onProgress: (progress) => {
            if (progress >= DIVE.handoffAt) {
              reachHandoff();
            }
          },
        }) ?? null);
    diveRef.current = dive;
    setFlight({
      id,
      caseId: opened.id,
      entrance: reduced ? "direct" : "flight",
      handoffZoom: dive?.handoffZoom ?? opened.handoffZoom,
      crossfadeMs: reduced
        ? FLIGHT.reducedCrossfadeMs
        : dive === null
          ? FLIGHT.quickCrossfadeMs
          : FLIGHT.crossfadeMs,
    });
    setAtHandoff(dive === null);
    setMapReady(false);
    setSkipped(false);
    setShowSkip(false);
    setAnnouncement("");
    setView("flying");
    // Also settles a dive that was cancelled or could not render.
    void dive?.done.then(reachHandoff);
  };

  // The globe rises once the map has faded out and the hero is ready; the UI comes back part-way.
  const startAscent = () => {
    const trip = tripRef.current;
    if (!trip.heroReady || !trip.fadedOut || trip.ascending) {
      return;
    }
    trip.ascending = true;
    const { id } = trip;
    let shown = false;
    const showUi = () => {
      if (shown || tripRef.current.id !== id) {
        return;
      }
      shown = true;
      markFlight("ui-in");
      setView("hero");
      setAnnouncement(CASE_COPY.announceBack);
    };
    markFlight("ascent");
    const ascent =
      heroRef.current?.ascend({
        onProgress: (progress) => {
          if (progress >= RETURN.uiInAt) {
            showUi();
          }
        },
      }) ?? null;
    ascentRef.current = ascent;
    if (ascent === null) {
      showUi();
      return;
    }
    if (trip.skip) {
      ascent.finish();
    }
    void ascent.done.then(() => {
      markFlight("back-done");
      showUi();
    });
  };

  const skipFlight = useCallback(() => {
    markFlight("skip");
    diveRef.current?.cancel();
    setSkipped(true);
    setHeroGone(true);
  }, []);

  // Skip on the way back: the map goes, the globe jumps to its framing (now, or when ready).
  const skipReturn = useCallback(() => {
    markFlight("skip");
    const trip = tripRef.current;
    trip.skip = true;
    trip.fadedOut = true;
    setFlight(null);
    setView("hero");
    setAnnouncement(CASE_COPY.announceBack);
    if (ascentRef.current === null) {
      startAscent();
    } else {
      ascentRef.current.finish();
    }
    // startAscent only reads refs and calls state setters, so the first render's copy is current.
  }, []);

  const back = () => {
    if (view !== "case") {
      return;
    }
    diveRef.current = null;
    ascentRef.current = null;
    flightCount.current += 1;
    tripRef.current = {
      id: flightCount.current,
      heroReady: false,
      fadedOut: false,
      ascending: false,
      skip: false,
    };
    markFlight("back");
    // The pass's link no longer applies.
    window.history.replaceState(null, "", window.location.pathname);
    const exitZoom = handoffFrame(
      site.handoffZoom,
      site.center[1],
      window.innerWidth,
      window.innerHeight,
      CAMERA.fovDeg,
    ).zoom;
    setReturnTrip({ id: flightCount.current, motion: !prefersReducedMotion(), exitZoom });
    setExitReady(false);
    setHeroReady(false);
    setHeroWaitOver(false);
    setShowSkip(false);
    setAnnouncement("");
    // The hero mounts again, under the map, parked over the site.
    setHeroGone(false);
    setReturned(true);
    setView("returning");
  };

  const onSceneReady = () => {
    // Only the way back waits for the scene (StrictMode may report it twice). A skip, or a hero
    // that was too slow, may already have shown the hero UI: the scene still has to rise from its
    // parked pose, so the current trip's first ready counts whatever the view.
    const trip = tripRef.current;
    if (!returned || trip.heroReady || trip.id !== flightCount.current) {
      return;
    }
    markFlight("hero-ready");
    trip.heroReady = true;
    setHeroReady(true);
    startAscent();
  };

  const onFadedOut = () => {
    // The globe is fully visible: drop the case view, which disposes the map.
    const trip = tripRef.current;
    trip.fadedOut = true;
    setFlight(null);
    if (!trip.heroReady) {
      // The hero was too slow (its wait ran out): the CSS globe shows and the UI comes back now;
      // when the scene is ready, onSceneReady finishes its ascent at once (trip.skip).
      markFlight("hero-late");
      trip.skip = true;
      setView("hero");
      setAnnouncement(CASE_COPY.announceBack);
      return;
    }
    startAscent();
  };

  const skip = view === "returning" ? skipReturn : skipFlight;

  // On the way back, the crossfade waits for the hero only so long.
  useEffect(() => {
    if (view !== "returning") {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      setHeroWaitOver(true);
    }, RETURN.heroReadyTimeoutMs);
    return () => {
      window.clearTimeout(timer);
    };
  }, [view]);

  // While flying either way: the Skip button after a short delay, and Esc.
  useEffect(() => {
    if (view !== "flying" && view !== "returning") {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      setShowSkip(true);
    }, FLIGHT.skipDelayMs);
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        skip();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("keydown", onKey);
    };
  }, [view, skip]);

  useEffect(() => {
    if (heroGone) {
      markFlight("hero-unmounted");
    }
  }, [heroGone]);

  // The case's files, fetched as its flight starts (the dive gives them time).
  const flyingTo = flight?.caseId ?? null;
  useEffect(() => {
    if (flyingTo === null) {
      return undefined;
    }
    let live = true;
    loadReach(flyingTo)
      .then((data) => {
        if (live) {
          setReach(data);
        }
      })
      .catch(() => {
        if (live) {
          setReachFailed(true);
        }
      });
    return () => {
      live = false;
    };
  }, [flyingTo]);

  return (
    <>
      {heroGone ? null : (
        <Hero
          ref={heroRef}
          leaving={view === "flying"}
          onExplore={explore}
          onWarmUp={warmUp}
          focusExplore={view === "hero" && returned}
          initialScreen={returned ? "cases" : "entry"}
          arriveFrom={view === "returning" && returnTrip?.motion === true ? siteTarget(site) : null}
          returning={view === "returning"}
          onSceneReady={onSceneReady}
        />
      )}
      {flight === null || reach?.info.site !== flight.caseId ? null : (
        <CaseView
          key={flight.id}
          reachCase={reachCase(flight.caseId)}
          reach={reach}
          initialPass={flight.id === 0 ? linkedPass : null}
          entrance={flight.entrance}
          handoffZoom={flight.handoffZoom}
          go={atHandoff && mapReady}
          crossfadeMs={flight.crossfadeMs}
          skip={skipped}
          onReady={() => {
            setMapReady(true);
          }}
          onCrossfaded={() => {
            // The globe is fully covered: unmount the hero, which disposes its WebGL scene.
            setHeroGone(true);
          }}
          onLanded={() => {
            setView("case");
            setAnnouncement(`${CASE_COPY.announceCase} ${reachCase(flight.caseId).title}.`);
          }}
          onBack={back}
          exit={
            view === "returning" && returnTrip !== null
              ? returnTrip.motion
                ? "flight"
                : "fade"
              : null
          }
          exitZoom={returnTrip?.exitZoom}
          fadeOut={view === "returning" && exitReady && (heroReady || heroWaitOver)}
          fadeOutMs={returnTrip?.motion === false ? RETURN.reducedCrossfadeMs : RETURN.crossfadeMs}
          onExitReady={() => {
            setExitReady(true);
          }}
          onFadedOut={onFadedOut}
        />
      )}
      {(view === "flying" || view === "returning") && showSkip ? (
        <SkipButton onSkip={skip} />
      ) : null}
      {flight !== null && reachFailed ? (
        <p className="case-load-failed" role="alert">
          {CASE_COPY.loadFailed}
        </p>
      ) : null}
      <p className="case-visually-hidden" aria-live="polite">
        {announcement}
      </p>
    </>
  );
}
