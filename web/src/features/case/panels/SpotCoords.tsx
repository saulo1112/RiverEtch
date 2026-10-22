import { X } from "lucide-react";
import { useEffect, useId, useRef, useState, type ClipboardEvent } from "react";

import { metres, nearestWindow, stretchKm } from "../../reaches/along.ts";
import type { AlongData } from "../../reaches/types.ts";
import { focusForVisitor } from "../../ui/modality.ts";
import { formatLatLon, parseCoordinate, parsePair, type LatLon } from "../coords.ts";
import { CASE_COPY } from "../content.ts";

/** Props of {@link SpotCoords}. */
export interface SpotCoordsProps {
  /** The panel is open. */
  readonly open: boolean;
  /** The reach's windows along the river. */
  readonly along: AlongData;
  /** The reading spot's window now (its centre fills the fields). */
  readonly current: number | null;
  /** Moves the reading spot to a window. */
  readonly onMove: (index: number) => void;
  readonly onClose: () => void;
}

// How far a typed point may be from the nearest window's centre (as a drop on the map).
const WITHIN_M = 1500;

/**
 * "Go to coordinates": opened by one click on the orange reading spot (or its button in the case
 * file), it takes a latitude and a longitude in WGS 84 (EPSG:4326), decimal degrees, as GPS and
 * Google Maps give them (a pair pasted at once fills both), and moves the reading spot to the
 * nearest stretch, saying how far its centre is from the point; a point too far from the reach
 * moves nothing and says how far it is.
 *
 * @param props - The panel's props.
 * @param props.open - The panel is open.
 * @param props.along - The reach's windows along the river.
 * @param props.current - The reading spot's window now.
 * @param props.onMove - Moves the reading spot to a window.
 * @param props.onClose - Closes the panel.
 * @returns The panel (nothing while closed).
 */
export function SpotCoords({ open, along, current, onMove, onClose }: SpotCoordsProps) {
  const copy = CASE_COPY.spot;
  const titleId = useId();
  const latId = useId();
  const lonId = useId();
  const latRef = useRef<HTMLInputElement>(null);
  const window = current === null ? undefined : along.plan.windows[current];
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [filled, setFilled] = useState(false);

  // The fields start at the spot's centre each time the panel opens (a move keeps what was typed).
  if (open && !filled && window !== undefined) {
    setFilled(true);
    setLat(window.lat.toFixed(5));
    setLon(window.lon.toFixed(5));
  }
  if (!open && filled) {
    setFilled(false);
    setStatus(null);
  }

  useEffect(() => {
    if (open) {
      focusForVisitor(latRef.current);
      latRef.current?.select();
    }
  }, [open]);

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    globalThis.addEventListener("keydown", onKey);
    return () => {
      globalThis.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  if (!open) {
    return null;
  }
  const go = (event: { preventDefault: () => void }) => {
    event.preventDefault();
    const point: LatLon | null = (() => {
      const a = parseCoordinate(lat, "lat");
      const b = parseCoordinate(lon, "lon");
      return a === null || b === null ? null : { lat: a, lon: b };
    })();
    if (point === null) {
      setStatus({ ok: false, text: copy.coordsInvalid });
      return;
    }
    const index = nearestWindow(along, point.lon, point.lat);
    const target = index === null ? undefined : along.plan.windows[index];
    if (index === null || target === undefined) {
      setStatus({ ok: false, text: copy.coordsInvalid });
      return;
    }
    const distance = metres(point.lon, point.lat, target.lon, target.lat);
    if (distance > WITHIN_M) {
      setStatus({ ok: false, text: copy.coordsTooFar((distance / 1000).toFixed(1)) });
      return;
    }
    onMove(index);
    const km = stretchKm(along, index);
    setStatus({
      ok: true,
      text: copy.coordsMoved(km === null ? "" : copy.stretch(km[0], km[1]), Math.round(distance)),
    });
  };
  const onPaste = (event: ClipboardEvent<HTMLInputElement>) => {
    const pair = parsePair(event.clipboardData.getData("text"));
    if (pair !== null) {
      event.preventDefault();
      setLat(pair.lat.toFixed(5));
      setLon(pair.lon.toFixed(5));
    }
  };
  return (
    <div className="case-coords case-glass" role="dialog" aria-labelledby={titleId}>
      <div className="case-coords__head">
        <h2 className="case-coords__title" id={titleId}>
          {copy.coordsTitle}
        </h2>
        <button
          type="button"
          className="case-proof__close"
          aria-label={copy.coordsClose}
          onClick={onClose}
        >
          <X size={16} strokeWidth={1.75} aria-hidden="true" />
        </button>
      </div>
      <p className="case-coords__system">{copy.coordsSystem}</p>
      <form className="case-coords__form" onSubmit={go}>
        <label htmlFor={latId}>{copy.coordsLat}</label>
        <input
          id={latId}
          ref={latRef}
          inputMode="decimal"
          autoComplete="off"
          spellCheck={false}
          value={lat}
          onPaste={onPaste}
          onChange={(event) => {
            setLat(event.target.value);
          }}
        />
        <label htmlFor={lonId}>{copy.coordsLon}</label>
        <input
          id={lonId}
          inputMode="decimal"
          autoComplete="off"
          spellCheck={false}
          value={lon}
          onPaste={onPaste}
          onChange={(event) => {
            setLon(event.target.value);
          }}
        />
        <button type="submit" className="case-btn case-btn--solid case-coords__go">
          {copy.coordsGo}
        </button>
      </form>
      {window === undefined ? null : (
        <p className="case-coords__now">{copy.coordsNow(formatLatLon(window))}</p>
      )}
      <p className="case-coords__note">{copy.coordsNote}</p>
      <p className="case-coords__status" aria-live="polite" data-ok={status?.ok}>
        {status?.text}
      </p>
    </div>
  );
}
