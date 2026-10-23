import { Compass, Minus, Plus } from "lucide-react";

import type { ReachData } from "../../reaches/types.ts";
import { CASE_COPY } from "../content.ts";
import type { HoverInfo } from "../map.ts";
import { primaryText, secondaryText, type TurbidityShown } from "../turbidity.ts";

/** Props of {@link MapControls}. */
export interface MapControlsProps {
  readonly bearing: number;
  readonly terrain3d: boolean;
  readonly onZoom: (delta: number) => void;
  readonly onNorth: () => void;
  readonly onTerrain3d: (on: boolean) => void;
}

/**
 * The map's controls, on its right edge: zoom, a compass that turns with the map (back to the
 * landed view), and 2D / 3D.
 *
 * @returns The controls.
 */
export function MapControls({
  bearing,
  terrain3d,
  onZoom,
  onNorth,
  onTerrain3d,
}: MapControlsProps) {
  const { controls } = CASE_COPY;
  return (
    <div
      className="case-panel case-controls case-glass"
      role="group"
      aria-label={CASE_COPY.tools.label}
    >
      <button
        type="button"
        className="case-controls__btn"
        onClick={() => {
          onZoom(0.7);
        }}
      >
        <Plus size={16} strokeWidth={1.9} aria-hidden="true" />
        <span className="case-visually-hidden">{controls.zoomIn}</span>
      </button>
      <button
        type="button"
        className="case-controls__btn"
        onClick={() => {
          onZoom(-0.7);
        }}
      >
        <Minus size={16} strokeWidth={1.9} aria-hidden="true" />
        <span className="case-visually-hidden">{controls.zoomOut}</span>
      </button>
      <button type="button" className="case-controls__btn" onClick={onNorth} title={controls.north}>
        <Compass
          size={17}
          strokeWidth={1.7}
          aria-hidden="true"
          style={{ transform: `rotate(${String(-bearing)}deg)` }}
        />
        <span className="case-visually-hidden">{controls.north}</span>
      </button>
      <button
        type="button"
        className="case-controls__btn case-controls__btn--text"
        aria-pressed={terrain3d}
        onClick={() => {
          onTerrain3d(!terrain3d);
        }}
      >
        {terrain3d ? controls.view2d : controls.view3d}
      </button>
    </div>
  );
}

/** Props of {@link Inspector}. */
export interface InspectorProps {
  readonly hover: HoverInfo | null;
  readonly reach: ReachData;
  /**
   * On the Turbidity layer: the stretch under the cursor, its value and its error or range (null:
   * no reading; absent: other layers).
   */
  readonly stretch?: TurbidityShown | null;
}

/**
 * The pixel under the cursor: its NDTI (relative), where it lies along the reach and whether the
 * pass left it usable. Only over the corridor.
 *
 * @returns The tooltip, or nothing.
 */
export function Inspector({ hover, reach, stretch }: InspectorProps) {
  if (hover?.reading == null) {
    return null;
  }
  const { reading } = hover;
  const { inspector } = CASE_COPY;
  const river = reach.geometry?.features.find((f) => f.properties.kind === "river");
  const lengthKm = (river?.properties.lengthM ?? 0) / 1000;
  return (
    <div
      className="case-inspector"
      style={{ left: `${String(hover.x + 16)}px`, top: `${String(hover.y + 16)}px` }}
      aria-hidden="true"
    >
      {stretch === undefined ? null : (
        <>
          <p className="case-inspector__value">
            {stretch === null ? inspector.noClass : primaryText(stretch)}
          </p>
          {secondaryText(stretch) === null ? null : (
            <p className="case-inspector__detail">{secondaryText(stretch)}</p>
          )}
        </>
      )}
      {stretch !== undefined ? null : reading.ndti === null ? (
        <p className="case-inspector__value case-inspector__value--off">{inspector.unusable}</p>
      ) : (
        <p className="case-inspector__value">
          {inspector.ndti} {reading.ndti >= 0 ? "+" : "−"}
          {Math.abs(reading.ndti).toFixed(3)}
          <span> {inspector.relative}</span>
        </p>
      )}
      <p className="case-inspector__place">
        {inspector.km} {(reading.place * lengthKm).toFixed(1)} {inspector.of} {lengthKm.toFixed(1)}
      </p>
      <p className="case-inspector__coords">
        {hover.lat.toFixed(5)}, {hover.lng.toFixed(5)}
      </p>
    </div>
  );
}

/** Props of {@link ScaleBar}. */
export interface ScaleBarProps {
  /** Metres per CSS pixel at the map's centre. */
  readonly metresPerPixel: number;
  /** The cursor's position, if over the map. */
  readonly hover: HoverInfo | null;
}

const NICE = [50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000];

/**
 * The cursor's coordinates and a scale bar, bottom centre over the map.
 *
 * @returns The bar.
 */
export function ScaleBar({ metresPerPixel, hover }: ScaleBarProps) {
  const target = metresPerPixel * 90;
  const metres = NICE.reduce((best, n) =>
    Math.abs(n - target) < Math.abs(best - target) ? n : best,
  );
  const width = metres / metresPerPixel;
  return (
    <div className="case-scale" aria-hidden="true">
      <span className="case-scale__coords">
        {hover === null ? "" : `${hover.lat.toFixed(4)}°, ${hover.lng.toFixed(4)}°`}
      </span>
      <span className="case-scale__bar" style={{ width: `${width.toFixed(0)}px` }} />
      <span className="case-scale__label">
        {metres >= 1000 ? `${String(metres / 1000)} km` : `${String(metres)} m`}
      </span>
    </div>
  );
}
