import { useCallback, useEffect, useRef, useState } from "react";

import { CaseView, type CaseEntrance } from "./features/case/CaseView.tsx";
import { FLIGHT } from "./features/case/config.ts";
import { CASE_COPY } from "./features/case/content.ts";
import { loadCaseMap } from "./features/case/loadMap.ts";
import { markFlight } from "./features/case/qa.ts";
import { ILLUSTRATIVE_CASE } from "./features/case/sample.ts";
import { SkipButton } from "./features/case/SkipButton.tsx";
import { DIVE } from "./features/hero/config.ts";
import type { DiveHandle } from "./features/hero/globe.ts";
import { Hero, type HeroApi } from "./features/hero/Hero.tsx";

/** What is on screen: the hero, the flythrough into the case, or the landed case view. */
type View = "hero" | "flying" | "case";

/** One trip into the case view; each one mounts a fresh case view. */
interface Flight {
  readonly id: number;
  readonly entrance: CaseEntrance;
  readonly handoffZoom: number;
  readonly crossfadeMs: number;
}

const data = ILLUSTRATIVE_CASE;
const { site } = data;

// Development shortcut: `?view=case` opens the case view directly.
const openCaseView =
  import.meta.env.DEV && new URLSearchParams(window.location.search).get("view") === "case";
const initialFlight: Flight | null = openCaseView
  ? { id: 0, entrance: "direct", handoffZoom: site.handoffZoom, crossfadeMs: 0 }
  : null;

function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

// Fetches the map chunk early (pointer or focus on "Explore the case"); a failure retries later.
function warmUp(): void {
  loadCaseMap().catch(() => undefined);
}

/**
 * Application root. "Explore the case" flies from the hero globe into the case view: the hero UI
 * fades, the globe dives to the site while the map loads hidden, the map crossfades in at the
 * handoff (the hero and its WebGL scene go), tilts onto the reach, and the panels slide in. Skip
 * or Esc jumps to the end; reduced motion, or a hero without its 3D scene, gets a short
 * crossfade instead of the dive.
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
  const heroRef = useRef<HeroApi>(null);
  const diveRef = useRef<DiveHandle | null>(null);
  const flightCount = useRef(initialFlight === null ? 0 : 1);

  const explore = () => {
    if (view !== "hero") {
      return;
    }
    flightCount.current += 1;
    const id = flightCount.current;
    markFlight("explore");
    const reduced = prefersReducedMotion();
    const target = { lat: site.center[1], lng: site.center[0], zoom: site.handoffZoom };
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
      entrance: reduced ? "direct" : "flight",
      handoffZoom: dive?.handoffZoom ?? site.handoffZoom,
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

  const skip = useCallback(() => {
    markFlight("skip");
    diveRef.current?.cancel();
    setSkipped(true);
    setHeroGone(true);
  }, []);

  const back = () => {
    diveRef.current = null;
    flightCount.current += 1;
    setFlight(null);
    setHeroGone(false);
    setReturned(true);
    setView("hero");
    setAnnouncement(CASE_COPY.announceBack);
  };

  // While flying: the Skip button after a short delay, and Esc.
  useEffect(() => {
    if (view !== "flying") {
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

  return (
    <>
      {heroGone ? null : (
        <Hero
          ref={heroRef}
          leaving={view === "flying"}
          onExplore={explore}
          onWarmUp={warmUp}
          focusExplore={returned}
        />
      )}
      {flight === null ? null : (
        <CaseView
          key={flight.id}
          data={data}
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
            setAnnouncement(
              `${CASE_COPY.announceCase} ${site.name}. ${CASE_COPY.illustrativeLabel}.`,
            );
          }}
          onBack={back}
        />
      )}
      {view === "flying" && showSkip ? <SkipButton onSkip={skip} /> : null}
      <p className="case-visually-hidden" aria-live="polite">
        {announcement}
      </p>
    </>
  );
}
