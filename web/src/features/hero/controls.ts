// What the hero shares with its overlay's scene controls ("Follow satellite"), through context, so
// the overlay's layout files need not pass it down.
import { createContext } from "react";

/** The scene controls' state and actions. */
export interface HeroControls {
  /** A 3D scene is showing, so the controls can act on it. */
  readonly available: boolean;
  /** Reduced motion: following, which moves the camera on its own, is off. */
  readonly reducedMotion: boolean;
  /** "Follow satellite" is on. */
  readonly follow: boolean;
  /** Turns "Follow satellite" on or off. */
  readonly setFollow: (on: boolean) => void;
}

/** The scene controls, or null outside a hero. */
export const HeroControlsContext = createContext<HeroControls | null>(null);
