import "./hero.css";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import { parseHeroUrlOptions, type HeroUrlOptions } from "./config.ts";

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
 * Full-viewport hero: a lit 3D Earth with a satellite scanning Colombia, over a starfield. Falls
 * back to a CSS planet when WebGL2 is unavailable.
 *
 * @returns The hero section.
 */
export function Hero() {
  const sectionRef = useRef<HTMLElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const [environment] = useState(detectEnvironment);
  const reducedMotion = useSyncExternalStore(subscribeReducedMotion, getReducedMotion);
  const { quality, frozenTime, lab, disabledEffects } = environment.url;
  // "Ready" belongs to one mount: a re-mount (e.g. a reduced-motion change) shows the poster again
  // until the new scene has rendered.
  const mountKey = `${quality}|${String(frozenTime)}|${String(reducedMotion)}|${String(lab)}`;
  const [readyKey, setReadyKey] = useState<string | null>(null);
  const [failed, setFailed] = useState(!environment.webgl2);
  const status: HeroStatus = failed ? "fallback" : readyKey === mountKey ? "ready" : "loading";

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
            dispose = mountHero(stage, {
              quality,
              reducedMotion,
              frozenTime,
              disabledEffects,
              cssTarget: section,
              onReady,
              onError: fail,
            }).dispose;
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
    };
  }, [environment.webgl2, quality, frozenTime, reducedMotion, lab, disabledEffects]);

  return (
    <section
      ref={sectionRef}
      className="hero"
      data-hero-state={status}
      role="img"
      aria-label="Animated globe: a satellite orbits the Earth and scans Colombia's rivers."
    >
      <div className="hero__sky" />
      <div className="hero__poster" aria-hidden="true">
        <div className="hero__planet">
          <span className="hero__marker" />
        </div>
      </div>
      <div className="hero__stage" ref={stageRef} />
      <div className="hero__vignette" />
    </section>
  );
}
