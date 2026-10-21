import { Columns2, Download, Layers, X } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";

import { csvOfSeries } from "../../reaches/export.ts";
import { isUngauged } from "../../reaches/scene.ts";
import type { ReachData } from "../../reaches/types.ts";
import { CASE_COPY } from "../content.ts";
import type { LayerMode, Overlays } from "../map.ts";
import { PassPicker } from "./PassPicker.tsx";

/** Props of {@link MapToolbar}. */
export interface MapToolbarProps {
  readonly reach: ReachData;
  /** What the river shows. */
  readonly mode: LayerMode;
  readonly onMode: (mode: LayerMode) => void;
  /** Whether the selected pass has a true-color image. */
  readonly photoAvailable: boolean;
  readonly opacity: number;
  readonly onOpacity: (opacity: number) => void;
  readonly overlays: Overlays;
  readonly onOverlays: (overlays: Overlays) => void;
  readonly terrain3d: boolean;
  readonly onTerrain3d: (on: boolean) => void;
  /** The pass compared with the selected one (null: compare is off). */
  readonly compareWith: number | null;
  readonly onCompare: (index: number | null) => void;
  /** Index of the selected pass. */
  readonly selected: number;
}

const MODES: readonly { readonly id: LayerMode; readonly label: string }[] = [
  { id: "ndti", label: CASE_COPY.tools.ndti },
  { id: "photo", label: CASE_COPY.tools.photo },
  { id: "none", label: CASE_COPY.tools.none },
];

// A popover anchored under its button, closed by a click outside or Escape. With `onOff`, the
// button of an active tool turns it off instead of opening the popover again.
function Popover({
  label,
  icon,
  active = false,
  onOff,
  offLabel,
  children,
}: {
  readonly label: string;
  readonly icon: ReactNode;
  readonly active?: boolean;
  readonly onOff?: () => void;
  readonly offLabel?: string;
  readonly children: ReactNode | ((close: () => void) => ReactNode);
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const onDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("pointerdown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);
  const turnsOff = active && onOff !== undefined;
  return (
    <div className="case-tools__group" ref={rootRef}>
      <button
        type="button"
        className="case-tools__btn"
        data-active={active || open}
        aria-expanded={open}
        aria-controls={id}
        aria-label={turnsOff ? offLabel : undefined}
        onClick={() => {
          if (turnsOff) {
            setOpen(false);
            onOff();
            return;
          }
          setOpen(!open);
        }}
      >
        {icon}
        <span>{label}</span>
        {turnsOff ? <X size={13} strokeWidth={2} aria-hidden="true" /> : null}
      </button>
      {open ? (
        <div className="case-tools__popover case-glass" id={id}>
          {typeof children === "function"
            ? children(() => {
                setOpen(false);
              })
            : children}
        </div>
      ) : null}
    </div>
  );
}

/**
 * The map's toolbar, top centre: what the river shows (NDTI, true color or nothing) and its
 * opacity, the overlays and 3D terrain, comparing two passes, and the downloads (the series as
 * CSV, the reach's geometry, its ledger).
 *
 * @param props - The toolbar's state and its handlers.
 * @returns The toolbar.
 */
export function MapToolbar(props: MapToolbarProps) {
  const { reach, mode, overlays, compareWith, selected } = props;
  const { tools } = CASE_COPY;
  const opacityId = useId();
  const noteId = useId();
  // Each overlay: its key, its name and what it is.
  const overlayItems: readonly (readonly [keyof Overlays, string, string])[] = [
    ["outline", tools.outline, tools.outlineNote],
    isUngauged(reach)
      ? ["window", tools.windowUngauged, tools.windowUngaugedNote]
      : ["window", tools.window, tools.windowNote],
  ];
  const download = () => {
    const blob = new Blob([csvOfSeries(reach)], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${reach.info.site}-2026.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };
  const toggle = (key: keyof Overlays) => {
    props.onOverlays({ ...overlays, [key]: !overlays[key] });
  };
  return (
    <div className="case-panel case-tools case-glass" role="toolbar" aria-label={tools.label}>
      <div
        className="case-tools__segmented"
        role="radiogroup"
        aria-label={tools.layer}
        data-tour="layers"
      >
        {MODES.map((m) => (
          <button
            key={m.id}
            type="button"
            role="radio"
            aria-checked={mode === m.id}
            className="case-tools__segment"
            disabled={m.id === "photo" && !props.photoAvailable}
            onClick={() => {
              props.onMode(m.id);
            }}
          >
            {m.label}
          </button>
        ))}
      </div>
      <label className="case-tools__opacity" htmlFor={opacityId}>
        <span className="case-visually-hidden">{tools.opacity}</span>
        <input
          id={opacityId}
          type="range"
          min={0.2}
          max={1}
          step={0.05}
          value={props.opacity}
          disabled={mode === "none"}
          onChange={(event) => {
            props.onOpacity(Number(event.target.value));
          }}
        />
      </label>
      <Popover
        label={tools.layers}
        icon={<Layers size={15} strokeWidth={1.8} aria-hidden="true" />}
      >
        <p className="case-tools__heading">{tools.overlays}</p>
        {overlayItems.map(([key, label, note]) => (
          <label key={key} className="case-tools__check">
            <input
              type="checkbox"
              checked={overlays[key]}
              aria-describedby={`${noteId}-${key}`}
              onChange={() => {
                toggle(key);
              }}
            />
            <span className="case-tools__check-text">
              {label}
              <span className="case-tools__check-note" id={`${noteId}-${key}`}>
                {note}
              </span>
            </span>
          </label>
        ))}
        <label className="case-tools__check">
          <input
            type="checkbox"
            checked={props.terrain3d}
            aria-describedby={`${noteId}-terrain`}
            onChange={(event) => {
              props.onTerrain3d(event.target.checked);
            }}
          />
          <span className="case-tools__check-text">
            {tools.terrain}
            <span className="case-tools__check-note" id={`${noteId}-terrain`}>
              {tools.terrainNote}
            </span>
          </span>
        </label>
      </Popover>
      <Popover
        label={tools.compare}
        active={compareWith !== null}
        onOff={() => {
          props.onCompare(null);
        }}
        offLabel={tools.compareStop}
        icon={<Columns2 size={15} strokeWidth={1.8} aria-hidden="true" />}
      >
        {(close) => (
          <>
            <p className="case-tools__heading">{tools.compareWith}</p>
            <PassPicker
              reach={reach}
              selected={compareWith}
              disabled={selected}
              label={tools.compareWith}
              autoFocus
              onPick={(index, done) => {
                props.onCompare(index);
                if (done) {
                  close();
                }
              }}
            />
            <p className="case-tools__note">{tools.compareHint}</p>
          </>
        )}
      </Popover>
      <Popover
        label={tools.export}
        icon={<Download size={15} strokeWidth={1.8} aria-hidden="true" />}
      >
        <button type="button" className="case-tools__item" onClick={download}>
          {tools.exportCsv}
        </button>
        <a className="case-tools__item" href={`${reach.base}geometry.geojson`} download>
          {tools.exportGeometry}
        </a>
        <a className="case-tools__item" href={`${reach.base}ledger.jsonl`} download>
          {tools.exportLedger}
        </a>
        <a className="case-tools__item" href={`${reach.base}cards/turbidity.json`} download>
          {tools.exportCard}
        </a>
      </Popover>
    </div>
  );
}
