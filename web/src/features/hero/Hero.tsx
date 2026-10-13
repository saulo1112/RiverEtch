import "./hero.css";
import "./drag.css";

import {
  useEffect,
  useEffectEvent,
  useId,
  useImperativeHandle,
  useRef,
  useState,
  useSyncExternalStore,
  type Ref,
} from "react";

import { REACH_CASES } from "../reaches/catalog.ts";
import { parseHeroUrlOptions, type HeroUrlOptions } from "./config.ts";
import type {
  AscentHandle,
  AscentOptions,
  DiveHandle,
  DiveOptions,
  DiveTarget,
  HeroHandle,
} from "./globe.ts";
import { HeroUi, type HeroScreen } from "./ui/HeroUi.tsx";

/** What the hero exposes to its parent (through `ref`). */
export interface HeroApi {
  /**
   * Starts the camera dive to a site (see `HeroHandle.dive` in globe.ts).
   *
   * @param target - Site and handoff zoom.
   * @param options - Duration and progress callback.
   * @returns The running dive, or null when no 3D scene is showing (still loading, the CSS
   *   fallback, or the satellite lab), in which case the caller crossfades instead.
   */
  readonly dive: (target: DiveTarget, options?: DiveOptions) => DiveHandle | null;
  /**
   * Lifts the camera parked by `arriveFrom` back to the hero framing (see `HeroHandle.ascend`).
   *
   * @param options - Duration and progress callback.
   * @returns The running rise, or null when no 3D scene is showing.
   */
  readonly ascend: (options?: AscentOptions) => AscentHandle | null;
}

/** Props of {@link Hero}. */
export interface HeroProps {
  /** Receives the {@link HeroApi}. */
  readonly ref?: Ref<HeroApi>;
  /** The flythrough has started: the UI fades out and takes no input; the scene keeps rendering. */
  readonly leaving?: boolean;
  /** "Open case": starts the flythrough to that case. */
  readonly onExplore?: (caseId: string) => void;
  /** The pointer or the focus reached a control leading to the case: warm up the case view. */
  readonly onWarmUp?: () => void;
  /** Focus "Open case" (back from the case view, once the UI shows again). */
  readonly focusExplore?: boolean;
  /** The UI's first screen (read on mount only): the cases after the way back. */
  readonly initialScreen?: HeroScreen;
  /**
   * Mount parked at the top-down view of this site (the way back from the case view): no intro,
   * the camera held until `HeroApi.ascend`. Read on mount only.
   */
  readonly arriveFrom?: DiveTarget | null;
  /** On the way back: the UI and the vignette stay hidden (and the UI inert) until this clears. */
  readonly returning?: boolean;
  /** The scene can be shown: its first frame rendered, or the CSS fallback in place. */
  readonly onSceneReady?: () => void;
}

// "loading" shows the CSS poster, "ready" fades the WebGL stage in, "fallback" keeps the poster.
type HeroStatus = "loading" | "ready" | "fallback";

interface HeroEnvironment {
  readonly url: HeroUrlOptions;
  readonly webgl2: boolean;
}

// Probes WebGL2 once and releases the probe context right away.
function supportsWebGL2(): boolean {
  try {
    const context = document.createElement("canvas").getContext("webgl2");
    if (context === null) {
      return false;
    }
    context.getExtension("WEBGL_lose_context")?.loseContext();
    return true;
  } catch {
    return false;
  }
}

function detectEnvironment(): HeroEnvironment {
  return { url: parseHeroUrlOptions(window.location.search), webgl2: supportsWebGL2() };
}

const reducedMotionQuery = "(prefers-reduced-motion: reduce)";

function subscribeReducedMotion(onChange: () => void): () => void {
  const query = window.matchMedia(reducedMotionQuery);
  query.addEventListener("change", onChange);
  return () => {
    query.removeEventListener("change", onChange);
  };
}

function getReducedMotion(): boolean {
  return window.matchMedia(reducedMotionQuery).matches;
}

// The featured case: the satellite's dish tracks it. Nothing marks it.
const FEATURED = REACH_CASES[0]?.center ?? [0, 0];
const REACH_SITE = { lat: FEATURED[1], lng: FEATURED[0] };

/**
 * Full-viewport hero: a lit 3D Earth, slowly turning, with a satellite on its orbit, over a
 * starfield, with the UI overlay on top. A mouse drag turns the globe. Falls back to a CSS planet
 * when WebGL2 is unavailable. Its scene can dive to a site for the flythrough into the case view.
 *
 * @returns The hero section.
 */
export function Hero({
  ref,
  leaving = false,
  onExplore,
  onWarmUp,
  focusExplore,
  initialScreen,
  arriveFrom = null,
  returning = false,
  onSceneReady,
}: HeroProps) {
  const sectionRef = useRef<HTMLElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<HeroHandle | null>(null);
  const titleId = useId();
  const [environment] = useState(detectEnvironment);
  const [arrival] = useState(arriveFrom);
  const reducedMotion = useSyncExternalStore(subscribeReducedMotion, getReducedMotion);
  const { quality, frozenTime, lab, disabledEffects } = environment.url;
  // "Ready" belongs to one mount: a re-mount (e.g. a reduced-motion change) shows the poster again
  // until the new scene has rendered.
  const mountKey = `${quality}|${String(frozenTime)}|${String(reducedMotion)}|${String(lab)}`;
  const [readyKey, setReadyKey] = useState<string | null>(null);
  const [failed, setFailed] = useState(!environment.webgl2);
  const status: HeroStatus = failed ? "fallback" : readyKey === mountKey ? "ready" : "loading";
  const sceneShown = status === "ready" && !lab;

  useImperativeHandle(
    ref,
    () => ({
      dive: (target, options) =>
        status === "ready" ? (sceneRef.current?.dive(target, options) ?? null) : null,
      ascend: (options) =>
        status === "ready" ? (sceneRef.current?.ascend(options) ?? null) : null,
    }),
    [status],
  );

  const notifySceneReady = useEffectEvent(() => {
    onSceneReady?.();
  });

  // The globe can be dragged only while it shows and no flight is on. Re-applied once a
  // (re-)mounted scene is ready.
  useEffect(() => {
    sceneRef.current?.setInteractive(sceneShown && !leaving && !returning);
  }, [sceneShown, leaving, returning]);
  useEffect(() => {
    if (status !== "loading") {
      notifySceneReady();
    }
  }, [status]);

  useEffect(() => {
    const section = sectionRef.current;
    const stage = stageRef.current;
    if (section === null || stage === null || !environment.webgl2) {
      return undefined;
    }

    let cancelled = false;
    let dispose: (() => void) | null = null;
    const fail = (error: unknown) => {
      if (import.meta.env.DEV) {
        console.error("[hero] WebGL scene failed; showing the CSS fallback.", error);
      }
      dispose?.();
      dispose = null;
      sceneRef.current = null;
      setFailed(true);
    };

    const key = `${quality}|${String(frozenTime)}|${String(reducedMotion)}|${String(lab)}`;
    const onReady = () => {
      setReadyKey(key);
    };
    // The scene lives in its own chunk (globe.gl and three), loaded only when it can render.
    const mount: Promise<void> = lab
      ? import("./lab.ts").then(({ mountSatelliteLab }) => {
          if (!cancelled) {
            dispose = mountSatelliteLab(stage, { quality, onReady });
          }
        })
      : import("./globe.ts").then(({ mountHero }) => {
          if (!cancelled) {
            const scene = mountHero(stage, {
              quality,
              reducedMotion,
              frozenTime,
              disabledEffects,
              cssTarget: section,
              onReady,
              onError: fail,
              arriveFrom: arrival,
              site: REACH_SITE,
            });
            sceneRef.current = scene;
            dispose = scene.dispose;
          }
        });
    mount.catch((error: unknown) => {
      if (!cancelled) {
        fail(error);
      }
    });

    return () => {
      cancelled = true;
      dispose?.();
      dispose = null;
      sceneRef.current = null;
    };
  }, [environment.webgl2, quality, frozenTime, reducedMotion, lab, disabledEffects, arrival]);

  return (
    <section
      ref={sectionRef}
      className="hero"
      data-hero-state={status}
      data-hero-quality={quality}
      data-hero-leaving={leaving}
      data-hero-returning={returning}
      aria-labelledby={titleId}
    >
      {/* Decorative layers: the scene and its CSS stand-ins carry no information. */}
      <div className="hero__sky" aria-hidden="true" />
      <div className="hero__poster" aria-hidden="true">
        <div className="hero__planet" />
      </div>
      <div className="hero__stage" ref={stageRef} aria-hidden="true" />
      <div className="hero__vignette" aria-hidden="true" />
      <HeroUi
        titleId={titleId}
        leaving={leaving || returning}
        onExplore={onExplore}
        onWarmUp={onWarmUp}
        focusExplore={focusExplore}
        initialScreen={initialScreen}
      />
    </section>
  );
}
