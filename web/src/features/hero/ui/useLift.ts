// Pointer "lift" for the hero's calls to action (iPadOS-style): the hook only tracks the pointer;
// every visual (scale, bloom, specular highlight) lives in ui.css under `.hero-btn--lift`, gated on
// a fine hovering pointer and on motion being allowed.
import { useCallback, type RefCallback } from "react";

/** Largest shift towards the pointer, in CSS pixels. */
const MAX_PULL_PX = 2;

const clamp = (value: number) => Math.min(1, Math.max(-1, value));

/**
 * Tracks a hovering mouse over an element and writes, at most once per animation frame:
 * `--mx`/`--my`, the pointer position as percentages of the element's box (scale-invariant, for
 * the highlight), and `--lift-x`/`--lift-y`, a pull towards the pointer of at most 2 px. Touch and
 * pen input are ignored. Give the element the `hero-btn--lift` class to show the effect.
 *
 * @returns A stable ref callback for the element; it removes its listeners on detach.
 */
export function useLift<T extends HTMLElement>(): RefCallback<T> {
  return useCallback((element: T | null) => {
    if (element === null) {
      return undefined;
    }
    let frame = 0;
    let clientX = 0;
    let clientY = 0;

    const write = () => {
      frame = 0;
      const rect = element.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) {
        return;
      }
      const u = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
      const v = Math.min(1, Math.max(0, (clientY - rect.top) / rect.height));
      const { style } = element;
      style.setProperty("--mx", `${(u * 100).toFixed(2)}%`);
      style.setProperty("--my", `${(v * 100).toFixed(2)}%`);
      style.setProperty("--lift-x", `${(clamp(u * 2 - 1) * MAX_PULL_PX).toFixed(2)}px`);
      style.setProperty("--lift-y", `${(clamp(v * 2 - 1) * MAX_PULL_PX).toFixed(2)}px`);
    };

    const onPointer = (event: PointerEvent) => {
      if (event.pointerType !== "mouse") {
        return;
      }
      clientX = event.clientX;
      clientY = event.clientY;
      if (frame === 0) {
        frame = requestAnimationFrame(write);
      }
    };

    // The pull eases back with the lift; the highlight keeps its last position while it fades.
    const onLeave = () => {
      cancelAnimationFrame(frame);
      frame = 0;
      element.style.setProperty("--lift-x", "0px");
      element.style.setProperty("--lift-y", "0px");
    };

    element.addEventListener("pointerenter", onPointer, { passive: true });
    element.addEventListener("pointermove", onPointer, { passive: true });
    element.addEventListener("pointerleave", onLeave, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      element.removeEventListener("pointerenter", onPointer);
      element.removeEventListener("pointermove", onPointer);
      element.removeEventListener("pointerleave", onLeave);
    };
  }, []);
}
