import "./hero.css";

import {
  useEffect,
  useId,
  useImperativeHandle,
  useRef,
  useState,
  useSyncExternalStore,
  type Ref,
} from "react";

import { parseHeroUrlOptions, type HeroUrlOptions } from "./config.ts";
import type { DiveHandle, DiveOptions, DiveTarget, HeroHandle } from "./globe.ts";
import { HeroUi } from "./ui/HeroUi.tsx";

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
}

/** Props of {@link Hero}. */
export interface HeroProps {
  /** Receives the {@link HeroApi}. */
  readonly ref?: Ref<HeroApi>;
  /** The flythrough has started: the UI fades out and takes no input; the scene keeps rendering. */
  readonly leaving?: boolean;
  /** "Explore the case": starts the flythrough. */
  readonly onExplore?: () => void;
  /** The pointer or the focus reached "Explore the case": warm up the case view. */
  readonly onWarmUp?: () => void;
  /** Focus "Explore the case" on mount (back from the case view). */
  readonly focusExplore?: boolean;
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

/**
 * Full-viewport hero: a lit 3D Earth with a satellite scanning Colombia, over a starfield, with the
 * UI overlay on top. Falls back to a CSS planet when WebGL2 is unavailable. Its scene can dive to
 * a site for the flythrough into the case view.
 *
 * @returns The hero section.
 */
export function Hero({ ref, leaving = false, onExplore, onWarmUp, focusExplore }: HeroProps) {
  const sectionRef = useRef<HTMLElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<HeroHandle | null>(null);
  const titleId = useId();
  const [environment] = useState(detectEnvironment);
  const reducedMotion = useSyncExternalStore(subscribeReducedMotion, getReducedMotion);
  const { quality, frozenTime, lab, disabledEffects } = environment.url;
  // "Ready" belongs to one mount: a re-mount (e.g. a reduced-motion change) shows the poster again
  // until the new scene has rendered.
  const mountKey = `${quality}|${String(frozenTime)}|${String(reducedMotion)}|${String(lab)}`;
  const [readyKey, setReadyKey] = useState<string | null>(null);
  const [failed, setFailed] = useState(!environment.webgl2);
  const status: HeroStatus = failed ? "fallback" : readyKey === mountKey ? "ready" : "loading";

  useImperativeHandle(
    ref,
    () => ({
      dive: (target, options) =>
        status === "ready" ? (sceneRef.current?.dive(target, options) ?? null) : null,
    }),
    [status],
  );

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
  }, [environment.webgl2, quality, frozenTime, reducedMotion, lab, disabledEffects]);

  return (
    <section
      ref={sectionRef}
      className="hero"
      data-hero-state={status}
      data-hero-quality={quality}
      data-hero-leaving={leaving}
      aria-labelledby={titleId}
    >
      {/* Decorative layers: the scene and its CSS stand-ins carry no information. */}
      <div className="hero__sky" aria-hidden="true" />
      <div className="hero__poster" aria-hidden="true">
        <div className="hero__planet">
          <span className="hero__marker" />
        </div>
      </div>
      <div className="hero__stage" ref={stageRef} aria-hidden="true" />
      <div className="hero__vignette" aria-hidden="true" />
      <HeroUi
        titleId={titleId}
        leaving={leaving}
        onExplore={onExplore}
        onWarmUp={onWarmUp}
        focusExplore={focusExplore}
      />
    </section>
  );
}
