import "./follow.css";

import { Crosshair } from "lucide-react";
import { useContext, useId } from "react";

import { HeroControlsContext } from "../../controls.ts";
import { FOLLOW_COPY } from "./content.ts";

/**
 * "Follow satellite": a toggle button (off by default) beside the status chip. On, the camera
 * tracks the point under the satellite; any drag of the globe turns it off. Disabled, with a hint,
 * under reduced motion; absent without a 3D scene.
 *
 * @returns The toggle, or nothing without a scene.
 */
export function FollowToggle() {
  const controls = useContext(HeroControlsContext);
  const hintId = useId();
  if (!controls?.available) {
    return null;
  }
  const { follow, reducedMotion, setFollow } = controls;
  return (
    <>
      <button
        type="button"
        className="hero-follow"
        aria-pressed={follow && !reducedMotion}
        disabled={reducedMotion}
        aria-describedby={reducedMotion ? hintId : undefined}
        title={reducedMotion ? FOLLOW_COPY.reducedMotion : undefined}
        onClick={() => {
          setFollow(!follow);
        }}
      >
        <Crosshair size={14} strokeWidth={1.75} nonScalingStroke aria-hidden="true" />
        {FOLLOW_COPY.label}
      </button>
      {reducedMotion ? (
        <span id={hintId} className="hero-ui__visually-hidden">
          {FOLLOW_COPY.reducedMotion}
        </span>
      ) : null}
    </>
  );
}
