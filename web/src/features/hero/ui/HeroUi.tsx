// The hero's UI layer: static placeholders (navigation, headline, calls to action, step strip and
// status chip) laid over the scene. Nothing here is wired to data, the wallet or the scan state.
import "@fontsource-variable/inter-tight";
import "@fontsource-variable/geist-mono";
import "../../../styles/tokens.css";
import "./ui.css";

import { Copy } from "./Copy.tsx";
import { Footer } from "./Footer.tsx";
import { Nav } from "./Nav.tsx";

/** Props of {@link HeroUi}. */
export interface HeroUiProps {
  /** Id for the headline, which labels the hero section (`aria-labelledby`). */
  readonly titleId: string;
  /** The flythrough has started: the overlay is fading out and takes no input. */
  readonly leaving?: boolean;
  /** "Explore the case": starts the flythrough. */
  readonly onExplore?: () => void;
  /** The pointer or the focus reached "Explore the case". */
  readonly onWarmUp?: () => void;
  /** Focus "Explore the case" on mount. */
  readonly focusExplore?: boolean;
}

/**
 * Overlay on top of the hero scene. A direct child of the hero section, so it fills it.
 *
 * @returns The overlay.
 */
export function HeroUi({
  titleId,
  leaving = false,
  onExplore,
  onWarmUp,
  focusExplore = false,
}: HeroUiProps) {
  return (
    <div className="hero-ui" inert={leaving}>
      <Nav />
      <main className="hero-ui__main">
        <Copy
          titleId={titleId}
          onExplore={onExplore}
          onWarmUp={onWarmUp}
          focusExplore={focusExplore}
        />
        <Footer />
      </main>
    </div>
  );
}
