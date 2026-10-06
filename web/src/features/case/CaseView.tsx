// The case view: a MapLibre map of the study site under night shades. The map module is loaded on
// demand (loadMap.ts) and created once per mount, StrictMode double mounts included.
import "@fontsource-variable/inter-tight";
import "@fontsource-variable/geist-mono";
import "../../styles/tokens.css";
import "./case.css";

import { useEffect, useRef, useState } from "react";

import { IMAGERY, TERRAIN } from "./config.ts";
import { loadCaseMap } from "./loadMap.ts";
import type { CaseMapHandle } from "./map.ts";
import type { CaseData } from "./types.ts";

/** Props of {@link CaseView}. */
export interface CaseViewProps {
  /** The case to show. */
  readonly data: CaseData;
}

interface CaseQAWindow extends Window {
  __caseQA?: {
    readonly stats: () => Record<string, unknown>;
    readonly project: CaseMapHandle["project"];
  };
}

type MapStatus = "loading" | "ready" | "failed";

// `?tiles=stub` (development only) draws generated tiles instead of fetching real ones.
function wantsStubTiles(): boolean {
  return import.meta.env.DEV && new URLSearchParams(window.location.search).get("tiles") === "stub";
}

/**
 * Full-viewport case view: the map of the site and its attribution.
 *
 * @returns The case view.
 */
export function CaseView({ data }: CaseViewProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  const [mapStatus, setMapStatus] = useState<MapStatus>("loading");

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
          start: "final",
          handoffZoom: data.site.handoffZoom,
          stubTiles: wantsStubTiles(),
        });
        if (!live()) {
          created.dispose();
          return;
        }
        handle = created;
        if (import.meta.env.DEV) {
          (window as CaseQAWindow).__caseQA = { stats: created.stats, project: created.project };
        }
        await created.ready;
        if (live()) {
          setMapStatus("ready");
        }
      })
      .catch((error: unknown) => {
        if (import.meta.env.DEV) {
          console.error("[case] The map could not be created.", error);
        }
        if (live()) {
          setMapStatus("failed");
        }
      });

    return () => {
      mount.abort();
      handle?.dispose();
      handle = null;
      if (import.meta.env.DEV) {
        delete (window as CaseQAWindow).__caseQA;
      }
    };
  }, [data]);

  return (
    <section className="case-view" data-map={mapStatus} aria-label={data.site.name}>
      <div className="case-view__map" ref={mapRef} aria-hidden="true" />
      <div className="case-view__shade case-view__shade--top" aria-hidden="true" />
      <div className="case-view__shade case-view__shade--bottom" aria-hidden="true" />
      <p className="case-view__attribution">
        <a href={IMAGERY.homepage} target="_blank" rel="noopener noreferrer">
          {IMAGERY.attribution}
        </a>
        {" · "}
        {TERRAIN.attribution}
      </p>
    </section>
  );
}
